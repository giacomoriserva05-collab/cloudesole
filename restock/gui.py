"""Interfaccia grafica: gestione dei target e monitoraggio dal vivo.

Il monitor gira in un thread separato con il proprio event loop asyncio; la
comunicazione verso Tk avviene solo tramite una coda, letta periodicamente dal
thread dell'interfaccia. Tk non e' thread-safe: nessun widget viene mai toccato
dal thread del monitor.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import re
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from . import config, discover, presets, theme
from .config import MIN_INTERVAL_SECONDS, ConfigError
from .httpclient import PoliteClient
from .models import Change, Item
from .monitor import Monitor, Observer
from .notify import Dispatcher

log = logging.getLogger(__name__)

LOG_LINES_MAX = 500


def _secondi(valore) -> str:
    """30.0 -> '30s'. Un intervallo con la virgola non si legge, e non serve."""
    try:
        numero = float(valore)
    except (TypeError, ValueError):
        return "-"
    return f"{numero:g}s"

TYPE_LABELS = {
    "shopify_product": "Prodotto Shopify",
    "shopify_collection": "Collezione Shopify",
    "json": "API JSON",
    "html": "Pagina HTML",
    "links": "Elenco di link",
}
LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}

TYPE_HELP = {
    "shopify_product": (
        "Incolla l'URL normale del prodotto. Il monitor usa da solo l'endpoint\n"
        "pubblico .js e legge la disponibilita' di ogni taglia."
    ),
    "shopify_collection": (
        "URL di una collezione. Utile per intercettare anche i prodotti nuovi\n"
        "che compaiono senza annuncio, non solo i restock."
    ),
    "json": (
        "Per siti con API pubblica. I percorsi sono puntati: data.variants,\n"
        "stock.status, price.amount..."
    ),
    "html": (
        "Per siti senza API. Apri la pagina da esaurita, trova una frase presente\n"
        "solo in quel caso e mettila fra i marcatori di esaurito."
    ),
    "links": (
        "Sorveglia un elenco (pagina o sitemap) e avvisa quando compare una voce\n"
        "nuova. Per i siti dove la disponibilita' non e' leggibile ma il catalogo si'."
    ),
}

CHANNELS = ["console", "desktop", "telegram", "discord"]


# --------------------------------------------------------------------------- #
# Ponte fra il thread del monitor e l'interfaccia
# --------------------------------------------------------------------------- #

class QueueLogHandler(logging.Handler):
    """Inoltra i record alla coda, estraendo il target a cui appartengono.

    Il monitor logga nella forma "[Nome target] messaggio": il prefisso serve a
    smistare la riga nella scheda giusta, e li' viene tolto perche' ridondante.
    """

    PREFIX = re.compile(r"^\[([^\]]{1,120})\]\s*(.*)$", re.S)

    def __init__(self, sink: queue.Queue) -> None:
        super().__init__()
        self.sink = sink
        self.setFormatter(logging.Formatter("%(asctime)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stamp = self.format(record)
            message = record.getMessage()
            match = self.PREFIX.match(message)
            if match:
                target, body = match.group(1), match.group(2)
            else:
                target, body = None, message
            self.sink.put(("log", record.levelno, f"{stamp}  {body}", target))
        except Exception:
            pass


class QueueObserver(Observer):
    def __init__(self, sink: queue.Queue) -> None:
        self.sink = sink

    def on_poll(self, target: str, ok: bool, total: int = 0, available: int = 0, detail: str = "") -> None:
        self.sink.put(("poll", target, ok, total, available, detail))

    def on_change(self, change: Change) -> None:
        self.sink.put(
            (
                "change",
                change.target,
                change.kind,
                change.item.title,
                change.item.price or "",
                change.item.url,
            )
        )

    def on_target_disabled(self, target: str, reason: str) -> None:
        self.sink.put(("disabled", target, reason))

    def on_gia_in_esecuzione(self, motivo: str) -> None:
        self.sink.put(("doppione", motivo))


class MonitorThread(threading.Thread):
    """Esegue Monitor.run() in un loop asyncio dedicato, interrompibile."""

    def __init__(self, settings, observer: Observer, sink: queue.Queue) -> None:
        super().__init__(daemon=True)
        self.settings = settings
        self.observer = observer
        self.sink = sink
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._ready = threading.Event()

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        monitor = Monitor(self.settings, observer=self.observer)
        self._task = loop.create_task(monitor.run())
        self._ready.set()
        try:
            loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.sink.put(("log", logging.ERROR, f"Monitor interrotto da un errore: {exc}"))
        finally:
            try:
                loop.run_until_complete(monitor.close())
            except Exception:
                pass
            loop.close()
            self.sink.put(("stopped",))

    def stop(self) -> None:
        self._ready.wait(timeout=5)
        if self._loop and self._task and not self._task.done():
            self._loop.call_soon_threadsafe(self._task.cancel)


# --------------------------------------------------------------------------- #
# Finestra di modifica di un target
# --------------------------------------------------------------------------- #

class TargetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, target: dict[str, Any] | None, existing_names: set[str]) -> None:
        super().__init__(parent)
        self.result: dict[str, Any] | None = None
        self.existing_names = existing_names
        self.original_name = (target or {}).get("name")

        self.title("Modifica target" if target else "Nuovo target")
        self.transient(parent)
        self.palette, self.caratteri = parent.palette, parent.caratteri
        self.resizable(False, False)

        data = dict(target or {})
        match = dict(data.get("match") or {})
        options = dict(data.get("options") or {})

        self.var_name = tk.StringVar(value=data.get("name", ""))
        self.var_type = tk.StringVar(value=TYPE_LABELS.get(data.get("type", "shopify_product"), TYPE_LABELS["shopify_product"]))
        self.var_url = tk.StringVar(value=data.get("url", ""))
        self.var_interval = tk.StringVar(value=f'{float(data.get("interval", 20)):g}')
        self.var_variants = tk.StringVar(value=", ".join(str(v) for v in (match.get("variants") or [])))
        self.var_keyword = tk.StringVar(value=match.get("keyword", ""))
        self.var_channels = {c: tk.BooleanVar(value=c in (data.get("notify") or ["console", "desktop"])) for c in CHANNELS}
        self.var_enabled = tk.BooleanVar(value=bool(data.get("enabled", True)))

        self.json_vars = {
            key: tk.StringVar(value=str(options.get(key, "")))
            for key in ("items_path", "key_path", "title_path", "available_path", "available_when", "price_path", "url_path")
        }
        if isinstance(options.get("available_when"), list):
            self.json_vars["available_when"].set(", ".join(str(v) for v in options["available_when"]))
        self.links_vars = {
            "pattern": tk.StringVar(value=str(options.get("pattern", ""))),
            "base": tk.StringVar(value=str(options.get("base", ""))),
            "include": tk.StringVar(value=", ".join(str(v) for v in (options.get("include") or []))),
            "exclude": tk.StringVar(value=", ".join(str(v) for v in (options.get("exclude") or []))),
            "limit": tk.StringVar(value=str(options.get("limit", "")) if options.get("limit") else ""),
        }
        self.var_regex = tk.BooleanVar(value=bool(options.get("regex", False)))
        self._html_in = options.get("in_stock_when") or []
        self._html_out = options.get("out_of_stock_when") or []

        detail = dict(data.get("detail") or {})
        self.var_detail_on = tk.BooleanVar(value=bool(detail))
        self.var_detail_regex = tk.BooleanVar(value=bool(detail.get("regex", True)))
        self.var_detail_max = tk.StringVar(value=str(detail.get("max_checks", 5)))
        self.var_detail_recheck = tk.BooleanVar(value=bool(detail.get("recheck_sold_out", True)))
        self._detail_in = detail.get("in_stock_when") or []
        self._detail_out = detail.get("out_of_stock_when") or []

        self._build()
        self._on_type_change()

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_visibility()
        centra_su(self, parent)
        self.focus()

    # -- costruzione ------------------------------------------------------- #

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        form = ttk.Frame(outer)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Nome").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.var_name, width=52).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Tipo").grid(row=1, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(
            form,
            textvariable=self.var_type,
            values=list(TYPE_LABELS.values()),
            state="readonly",
            width=50,
        )
        combo.grid(row=1, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_type_change())

        self.help_label = ttk.Label(form, text="", foreground=self.palette.secondario, justify="left")
        self.help_label.grid(row=2, column=1, sticky="w", pady=(0, 6))

        ttk.Label(form, text="URL").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.var_url, width=52).grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Ogni").grid(row=4, column=0, sticky="w", pady=4)
        row = ttk.Frame(form)
        row.grid(row=4, column=1, sticky="w", pady=4)
        ttk.Spinbox(row, from_=MIN_INTERVAL_SECONDS, to=3600, increment=5, textvariable=self.var_interval, width=8).pack(side="left")
        ttk.Label(row, text=f"secondi   (minimo {MIN_INTERVAL_SECONDS:.0f}; 15-30 e' il valore consigliato)").pack(side="left", padx=6)

        # Riquadro che cambia in base al tipo scelto.
        self.dynamic = ttk.LabelFrame(outer, text="Opzioni", padding=10)
        self.dynamic.pack(fill="x", pady=(12, 0))

        channels = ttk.LabelFrame(outer, text="Canali di notifica", padding=10)
        channels.pack(fill="x", pady=(12, 0))
        for channel in CHANNELS:
            ttk.Checkbutton(channels, text=channel.capitalize(), variable=self.var_channels[channel]).pack(side="left", padx=(0, 14))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(16, 0))
        ttk.Checkbutton(
            buttons,
            text="Target attivo (se spento resta in elenco ma non viene interrogato)",
            variable=self.var_enabled,
        ).pack(side="left")
        ttk.Button(buttons, text="Annulla", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Salva", command=self._save).pack(side="right", padx=6)

    def _on_type_change(self) -> None:
        ttype = LABEL_TO_TYPE[self.var_type.get()]
        self.help_label.configure(text=TYPE_HELP[ttype])

        for child in self.dynamic.winfo_children():
            child.destroy()
        self.dynamic.columnconfigure(1, weight=1)

        if ttype in ("shopify_product", "shopify_collection"):
            ttk.Label(self.dynamic, text="Solo queste taglie").grid(row=0, column=0, sticky="w", pady=4)
            ttk.Entry(self.dynamic, textvariable=self.var_variants).grid(row=0, column=1, sticky="ew", pady=4)
            ttk.Label(
                self.dynamic,
                text="Separate da virgola, es. 42, 42.5, 43. Vuoto = tutte.",
                foreground=self.palette.secondario,
            ).grid(row=1, column=1, sticky="w")

            if ttype == "shopify_collection":
                ttk.Label(self.dynamic, text="Parola chiave").grid(row=2, column=0, sticky="w", pady=(10, 4))
                ttk.Entry(self.dynamic, textvariable=self.var_keyword).grid(row=2, column=1, sticky="ew", pady=(10, 4))
                ttk.Label(
                    self.dynamic,
                    text="Filtra i prodotti per titolo, es. jordan. Vuoto = tutti.",
                    foreground=self.palette.secondario,
                ).grid(row=3, column=1, sticky="w")

        elif ttype == "json":
            labels = [
                ("items_path", "Lista articoli", "es. data.variants - vuoto se la radice e' gia' la lista"),
                ("available_path", "Campo disponibilita'", "obbligatorio, es. stock.status"),
                ("available_when", "Vale disponibile se", "es. in_stock, available - vuoto = qualsiasi valore non nullo"),
                ("title_path", "Campo titolo", "es. size"),
                ("key_path", "Campo identificativo", "es. sku"),
                ("price_path", "Campo prezzo", "facoltativo"),
                ("url_path", "Campo link", "facoltativo"),
            ]
            for index, (key, label, hint) in enumerate(labels):
                ttk.Label(self.dynamic, text=label).grid(row=index * 2, column=0, sticky="w", pady=(6, 0))
                ttk.Entry(self.dynamic, textvariable=self.json_vars[key]).grid(row=index * 2, column=1, sticky="ew", pady=(6, 0))
                ttk.Label(self.dynamic, text=hint, foreground=self.palette.secondario).grid(row=index * 2 + 1, column=1, sticky="w")

        elif ttype == "links":
            fields = [
                ("pattern", "Schema di ricerca", "espressione regolare, il gruppo fra parentesi e' la voce"),
                ("base", "Prefisso del link", "anteposto alla voce se non e' gia' un URL completo"),
                ("include", "Tieni solo se contiene", "parole separate da virgola - vuoto = tutto"),
                ("exclude", "Scarta se contiene", "parole separate da virgola - facoltativo"),
                ("limit", "Massimo voci", "tetto di sicurezza, predefinito 5000"),
            ]
            for index, (key, label, hint) in enumerate(fields):
                ttk.Label(self.dynamic, text=label).grid(row=index * 2, column=0, sticky="w", pady=(6, 0))
                ttk.Entry(self.dynamic, textvariable=self.links_vars[key]).grid(row=index * 2, column=1, sticky="ew", pady=(6, 0))
                ttk.Label(self.dynamic, text=hint, foreground=self.palette.secondario).grid(row=index * 2 + 1, column=1, sticky="w")

            self._build_detail(len(fields) * 2)

        else:  # html
            ttk.Label(self.dynamic, text="Esaurito se la pagina contiene").grid(row=0, column=0, sticky="nw", pady=4)
            self.text_out = tk.Text(self.dynamic, height=4, width=44)
            theme.campo_testo(self.text_out, self.palette, self.caratteri, mono=True)
            self.text_out.grid(row=0, column=1, sticky="ew", pady=4)
            self.text_out.insert("1.0", "\n".join(str(v) for v in self._html_out))

            ttk.Label(self.dynamic, text="Disponibile se contiene").grid(row=1, column=0, sticky="nw", pady=4)
            self.text_in = tk.Text(self.dynamic, height=4, width=44)
            theme.campo_testo(self.text_in, self.palette, self.caratteri, mono=True)
            self.text_in.grid(row=1, column=1, sticky="ew", pady=4)
            self.text_in.insert("1.0", "\n".join(str(v) for v in self._html_in))

            ttk.Label(
                self.dynamic,
                text="Una frase per riga. L'esaurito ha la precedenza sul disponibile.",
                foreground=self.palette.secondario,
            ).grid(row=2, column=1, sticky="w")
            ttk.Checkbutton(
                self.dynamic, text="Interpreta le righe come espressioni regolari", variable=self.var_regex
            ).grid(row=3, column=1, sticky="w", pady=(6, 0))

    def _build_detail(self, riga: int) -> None:
        """Riquadro dell'accertamento: apre le schede per distinguere esaurito e disponibile."""
        box = ttk.LabelFrame(self.dynamic, text="Disponibilita'", padding=8)
        box.grid(row=riga, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        box.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            box,
            text="Apri la scheda di ogni prodotto per capire se e' disponibile o esaurito",
            variable=self.var_detail_on,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(
            box,
            text=(
                "Senza questa opzione l'elenco sa solo che un prodotto e' comparso.\n"
                "Con l'opzione attiva, il monitor apre la scheda e ti dice anche se e'\n"
                "acquistabile - e ti avvisa quando un esaurito torna disponibile."
            ),
            foreground=self.palette.secondario,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))

        ttk.Label(box, text="Disponibile se la scheda contiene").grid(row=2, column=0, sticky="nw", pady=3)
        self.text_detail_in = tk.Text(box, height=3, width=42)
        theme.campo_testo(self.text_detail_in, self.palette, self.caratteri, mono=True)
        self.text_detail_in.grid(row=2, column=1, sticky="ew", pady=3)
        self.text_detail_in.insert("1.0", "\n".join(str(v) for v in self._detail_in))

        ttk.Label(box, text="Esaurito se contiene").grid(row=3, column=0, sticky="nw", pady=3)
        self.text_detail_out = tk.Text(box, height=3, width=42)
        theme.campo_testo(self.text_detail_out, self.palette, self.caratteri, mono=True)
        self.text_detail_out.grid(row=3, column=1, sticky="ew", pady=3)
        self.text_detail_out.insert("1.0", "\n".join(str(v) for v in self._detail_out))

        ttk.Checkbutton(
            box, text="Interpreta le righe come espressioni regolari", variable=self.var_detail_regex
        ).grid(row=4, column=1, sticky="w", pady=(4, 0))

        riga_max = ttk.Frame(box)
        riga_max.grid(row=5, column=1, sticky="w", pady=(6, 0))
        ttk.Label(riga_max, text="Schede da aprire per giro:").pack(side="left")
        ttk.Spinbox(riga_max, from_=1, to=50, textvariable=self.var_detail_max, width=5).pack(side="left", padx=6)
        ttk.Label(riga_max, text="(a rotazione, per non caricare il sito)", foreground=self.palette.secondario).pack(side="left")

        ttk.Checkbutton(
            box,
            text="Ricontrolla gli esauriti, per accorgersi dei restock",
            variable=self.var_detail_recheck,
        ).grid(row=6, column=1, sticky="w", pady=(4, 0))

    # -- salvataggio ------------------------------------------------------- #

    def _save(self) -> None:
        name = self.var_name.get().strip()
        url = self.var_url.get().strip()
        ttype = LABEL_TO_TYPE[self.var_type.get()]

        if not name:
            messagebox.showwarning("Campo mancante", "Dai un nome al target.", parent=self)
            return
        if name != self.original_name and name in self.existing_names:
            messagebox.showwarning("Nome gia' usato", f"Esiste gia' un target chiamato '{name}'.", parent=self)
            return
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("URL non valido", "L'URL deve iniziare con http:// o https://", parent=self)
            return

        try:
            interval = float(self.var_interval.get())
        except ValueError:
            messagebox.showwarning("Intervallo non valido", "L'intervallo deve essere un numero.", parent=self)
            return
        if interval < MIN_INTERVAL_SECONDS:
            messagebox.showwarning(
                "Intervallo troppo basso",
                f"Il minimo consentito e' {MIN_INTERVAL_SECONDS:.0f} secondi.",
                parent=self,
            )
            return

        channels = [c for c in CHANNELS if self.var_channels[c].get()]
        if not channels:
            messagebox.showwarning("Nessun canale", "Scegli almeno un canale di notifica.", parent=self)
            return

        target: dict[str, Any] = {
            "name": name,
            "type": ttype,
            "url": url,
            "interval": interval,
            "enabled": self.var_enabled.get(),
            "notify": channels,
        }

        match: dict[str, Any] = {}
        options: dict[str, Any] = {}

        if ttype in ("shopify_product", "shopify_collection"):
            variants = [v.strip() for v in self.var_variants.get().split(",") if v.strip()]
            if variants:
                match["variants"] = variants
            if ttype == "shopify_collection" and self.var_keyword.get().strip():
                match["keyword"] = self.var_keyword.get().strip()

        elif ttype == "json":
            if not self.json_vars["available_path"].get().strip():
                messagebox.showwarning(
                    "Campo mancante",
                    "Per un target JSON serve il campo disponibilita'.",
                    parent=self,
                )
                return
            for key, var in self.json_vars.items():
                value = var.get().strip()
                if not value:
                    continue
                if key == "available_when":
                    options[key] = [v.strip() for v in value.split(",") if v.strip()]
                else:
                    options[key] = value

        elif ttype == "links":
            pattern = self.links_vars["pattern"].get().strip()
            if not pattern:
                messagebox.showwarning(
                    "Campo mancante",
                    "Per un elenco di link serve lo schema di ricerca.",
                    parent=self,
                )
                return
            try:
                re.compile(pattern)
            except re.error as exc:
                messagebox.showwarning("Schema non valido", f"Espressione regolare errata:\n{exc}", parent=self)
                return
            options["pattern"] = pattern
            if self.links_vars["base"].get().strip():
                options["base"] = self.links_vars["base"].get().strip()
            for key in ("include", "exclude"):
                words = [w.strip() for w in self.links_vars[key].get().split(",") if w.strip()]
                if words:
                    options[key] = words
            if self.links_vars["limit"].get().strip():
                try:
                    options["limit"] = int(self.links_vars["limit"].get().strip())
                except ValueError:
                    messagebox.showwarning("Valore non valido", "Il massimo voci deve essere un numero intero.", parent=self)
                    return

            if self.var_detail_on.get():
                righe_in = [r.strip() for r in self.text_detail_in.get("1.0", "end").splitlines() if r.strip()]
                righe_out = [r.strip() for r in self.text_detail_out.get("1.0", "end").splitlines() if r.strip()]
                if not righe_in and not righe_out:
                    messagebox.showwarning(
                        "Marcatori mancanti",
                        "Per accertare la disponibilita' serve almeno una frase che\n"
                        "identifichi il disponibile o l'esaurito nella scheda prodotto.",
                        parent=self,
                    )
                    return
                if self.var_detail_regex.get():
                    for espressione in righe_in + righe_out:
                        try:
                            re.compile(espressione)
                        except re.error as exc:
                            messagebox.showwarning(
                                "Espressione non valida", f"{espressione}\n\n{exc}", parent=self
                            )
                            return
                try:
                    massimo = int(self.var_detail_max.get())
                    if massimo < 1:
                        raise ValueError
                except ValueError:
                    messagebox.showwarning(
                        "Valore non valido",
                        "Le schede da aprire per giro devono essere almeno 1.",
                        parent=self,
                    )
                    return

                detail: dict[str, Any] = {"max_checks": massimo}
                if righe_in:
                    detail["in_stock_when"] = righe_in
                if righe_out:
                    detail["out_of_stock_when"] = righe_out
                if self.var_detail_regex.get():
                    detail["regex"] = True
                detail["recheck_sold_out"] = self.var_detail_recheck.get()
                target["detail"] = detail

        else:
            out = [line.strip() for line in self.text_out.get("1.0", "end").splitlines() if line.strip()]
            inn = [line.strip() for line in self.text_in.get("1.0", "end").splitlines() if line.strip()]
            if not out and not inn:
                messagebox.showwarning(
                    "Marcatori mancanti",
                    "Indica almeno una frase che identifichi l'esaurito o il disponibile.",
                    parent=self,
                )
                return
            if out:
                options["out_of_stock_when"] = out
            if inn:
                options["in_stock_when"] = inn
            if self.var_regex.get():
                options["regex"] = True

        if match:
            target["match"] = match
        if options:
            target["options"] = options

        if not self._conferma_ritmo(target, interval):
            return

        self.result = target
        self.destroy()

    def _conferma_ritmo(self, target: dict[str, Any], interval: float) -> bool:
        """Sotto una certa soglia chiede conferma, spiegando il costo reale.

        Il minimo tecnico e' 3 secondi, ma tenerlo su un sito vero e' il modo
        piu' rapido per farsi bloccare l'IP proprio durante un drop.
        """
        if interval >= 15:
            return True

        per_giro = 1
        detail = target.get("detail") or {}
        if detail:
            per_giro += int(detail.get("max_checks", 5))

        al_minuto = round(60 / interval * per_giro)
        messaggio = (
            f"Intervallo impostato a {interval:.0f} secondi.\n\n"
            f"Sono circa {al_minuto} richieste al minuto verso lo stesso sito"
        )
        if per_giro > 1:
            messaggio += f" ({per_giro} per giro: l'elenco piu' le schede dei prodotti)"
        messaggio += (
            ".\n\nA questo ritmo il rischio concreto e' di farsi limitare o bloccare\n"
            "l'indirizzo IP, e succederebbe proprio quando serve il monitor.\n"
            "Fra 15 e 30 secondi il drop lo prendi comunque.\n\n"
            "Vuoi salvare lo stesso?"
        )
        return bool(messagebox.askyesno("Intervallo molto basso", messaggio, parent=self))


def centra_su(finestra: tk.Toplevel, genitore: tk.Misc) -> None:
    """Apre il dialogo davanti alla finestra principale, non dove capita."""
    finestra.update_idletasks()
    larghezza = finestra.winfo_width()
    altezza = finestra.winfo_height()
    x = genitore.winfo_rootx() + (genitore.winfo_width() - larghezza) // 2
    y = genitore.winfo_rooty() + max(20, (genitore.winfo_height() - altezza) // 3)
    finestra.geometry(f"+{max(0, x)}+{max(0, y)}")


def scorrimento_automatico(contenitore, widget, pady: int = 1) -> ttk.Scrollbar:
    """Barra di scorrimento che compare solo quando il contenuto eccede.

    Su macOS non esiste un binario grigio permanente accanto a un elenco di
    cinque righe: e' un dettaglio piccolo ma e' meta' della differenza fra
    un'interfaccia ordinata e una che sembra un pannello di controllo.
    """
    barra = ttk.Scrollbar(contenitore, orient="vertical", command=widget.yview)

    def aggiorna(primo: str, ultimo: str) -> None:
        barra.set(primo, ultimo)
        if float(primo) <= 0.0 and float(ultimo) >= 1.0:
            barra.pack_forget()
        else:
            barra.pack(side="right", fill="y", pady=pady)

    widget.configure(yscrollcommand=aggiorna)
    return barra


class LogPanel(ttk.Frame):
    """Un registro indipendente, con il proprio tetto di righe."""

    def __init__(self, parent: tk.Misc, palette, caratteri) -> None:
        super().__init__(parent, style="Contenuto.TFrame")
        self.text = tk.Text(
            self,
            height=9,
            wrap="none",
            state="disabled",
            font=caratteri.mono,
            background=palette.contenuto,
            foreground=palette.testo,
            insertbackground=palette.testo,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=12,
            pady=8,
            spacing1=1,
        )
        scorrimento_automatico(self, self.text, pady=0)
        self.text.pack(side="left", fill="both", expand=True)

        self.text.tag_configure("ERROR", foreground=palette.rosso)
        self.text.tag_configure("WARNING", foreground=palette.arancio)
        self.text.tag_configure("RESTOCK", foreground=palette.verde)
        self.lines = 0

    def append(self, line: str, tag: str | None = None) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", tag or ())
        # Tetto fisso per scheda: dopo ore di monitoraggio il registro di un
        # target non deve crescere senza limite.
        excess = int(self.text.index("end-1c").split(".")[0]) - LOG_LINES_MAX
        if excess > 0:
            self.text.delete("1.0", f"{excess + 1}.0")
        self.text.see("end")
        self.text.configure(state="disabled")
        self.lines += 1

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.lines = 0


class SiteWizard(tk.Toplevel):
    """Analizza un indirizzo e propone la configurazione adatta.

    L'analisi gira in un thread separato: la finestra resta reattiva e la coda
    porta l'esito al thread di Tk, come per il monitor.
    """

    def __init__(self, parent: tk.Misc, user_agent: str, respect_robots: bool) -> None:
        super().__init__(parent)
        self.result: dict[str, Any] | None = None
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self.esito = None
        self._coda: queue.Queue = queue.Queue()

        self.title("Aggiungi un sito o un prodotto")
        self.transient(parent)
        self.palette, self.caratteri = parent.palette, parent.caratteri
        self.resizable(False, False)

        self.var_ambito = tk.StringVar(value="sito")
        self.var_url = tk.StringVar()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_visibility()
        centra_su(self, parent)
        self.focus()
        self._pump()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        scelta = ttk.LabelFrame(outer, text="Cosa vuoi monitorare", padding=10)
        scelta.pack(fill="x")

        ttk.Radiobutton(
            scelta,
            text="Tutto un sito - avvisami di qualunque restock, su qualsiasi prodotto",
            value="sito",
            variable=self.var_ambito,
        ).pack(anchor="w")
        ttk.Radiobutton(
            scelta,
            text="Un solo prodotto - seguo solo questo",
            value="prodotto",
            variable=self.var_ambito,
        ).pack(anchor="w", pady=(4, 0))

        riga = ttk.Frame(outer)
        riga.pack(fill="x", pady=(12, 0))
        ttk.Label(riga, text="Indirizzo").pack(side="left")
        entry = ttk.Entry(riga, textvariable=self.var_url, width=58)
        entry.pack(side="left", padx=8, fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self._analizza())
        self.btn_analizza = ttk.Button(riga, text="Analizza", command=self._analizza)
        self.btn_analizza.pack(side="left")

        ttk.Label(
            outer,
            text=(
                "Per un sito basta il dominio (es. shop.esempio.com). Per un prodotto,\n"
                "l'indirizzo completo della sua pagina."
            ),
            foreground=self.palette.secondario,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        riquadro = ttk.LabelFrame(outer, text="Esito dell'analisi", padding=8)
        riquadro.pack(fill="both", expand=True, pady=(12, 0))

        self.rapporto = tk.Text(riquadro, height=15, width=86, wrap="word", state="disabled")
        theme.campo_testo(self.rapporto, self.palette, self.caratteri)
        self.rapporto.configure(relief="flat", borderwidth=0, padx=14, pady=10)
        scroll = ttk.Scrollbar(riquadro, orient="vertical", command=self.rapporto.yview)
        self.rapporto.configure(yscrollcommand=scroll.set)
        self.rapporto.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.rapporto.tag_configure("titolo", font=self.caratteri.sezione, spacing3=6)
        self.rapporto.tag_configure("buono", foreground=self.palette.verde)
        self.rapporto.tag_configure("parziale", foreground=self.palette.arancio)
        self.rapporto.tag_configure("problema", foreground=self.palette.rosso)
        self.rapporto.tag_configure("etichetta", font=self.caratteri.corpo_forte, spacing1=8)

        self._scrivi("Incolla un indirizzo e premi Analizza.\n\n"
                     "Il monitor controlla robots.txt, prova gli endpoint pubblici e apre una\n"
                     "scheda prodotto per vedere se la disponibilita' e' leggibile. Poi ti dice\n"
                     "cosa riesce a fare su quel sito, senza promettere quello che non puo'.")

        self.riga_scelta = ttk.Frame(outer)
        self.riga_scelta.pack(fill="x", pady=(8, 0))
        ttk.Label(self.riga_scelta, text="Monitora i link").pack(side="left")
        self.var_famiglia = tk.StringVar()
        self.combo_famiglia = ttk.Combobox(
            self.riga_scelta, textvariable=self.var_famiglia, state="readonly", width=64
        )
        self.combo_famiglia.pack(side="left", padx=8)
        self.riga_scelta.pack_forget()

        bottoni = ttk.Frame(outer)
        bottoni.pack(fill="x", pady=(12, 0))
        ttk.Button(bottoni, text="Annulla", command=self.destroy).pack(side="right")
        self.btn_crea = ttk.Button(bottoni, text="Crea il target", command=self._crea, state="disabled")
        self.btn_crea.pack(side="right", padx=6)

    def _scrivi(self, testo: str, tag: str | None = None) -> None:
        self.rapporto.configure(state="normal")
        self.rapporto.delete("1.0", "end")
        self.rapporto.insert("end", testo, tag or ())
        self.rapporto.configure(state="disabled")

    def _analizza(self) -> None:
        url = self.var_url.get().strip()
        if not url:
            messagebox.showwarning("Indirizzo mancante", "Incolla un indirizzo da analizzare.", parent=self)
            return

        ambito = self.var_ambito.get()
        self.btn_analizza.configure(state="disabled")
        self.btn_crea.configure(state="disabled")
        self._scrivi("Analisi in corso...\n\nQualche secondo: sto interrogando il sito.")

        user_agent, respect = self.user_agent, self.respect_robots

        def lavora() -> None:
            async def esegui():
                async with PoliteClient(user_agent, respect_robots=respect, timeout=25.0) as client:
                    if ambito == "sito":
                        return await discover.analizza_sito(client, url)
                    return await discover.analizza_prodotto(client, url)

            try:
                self._coda.put(("esito", asyncio.run(esegui())))
            except Exception as exc:
                self._coda.put(("errore", f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=lavora, daemon=True).start()

    def _pump(self) -> None:
        try:
            while True:
                genere, carico = self._coda.get_nowait()
                if genere == "esito":
                    self.esito = carico
                    self._mostra(carico)
                else:
                    self._scrivi(f"Analisi fallita.\n\n{carico}", "problema")
                self.btn_analizza.configure(state="normal")
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.after(150, self._pump)

    def _mostra(self, esito) -> None:
        self.rapporto.configure(state="normal")
        self.rapporto.delete("1.0", "end")

        self.rapporto.insert("end", esito.origine + "\n", "titolo")

        if esito.copertura == discover.COMPLETA:
            self.rapporto.insert("end", "Monitoraggio completo possibile\n", "buono")
        elif esito.copertura == discover.PARZIALE:
            self.rapporto.insert("end", "Monitoraggio solo parziale\n", "parziale")
        else:
            self.rapporto.insert("end", "Questo sito non e' monitorabile\n", "problema")

        if esito.piattaforma != "sconosciuta":
            self.rapporto.insert("end", f"Piattaforma: {esito.piattaforma}\n")
        if esito.metodo:
            self.rapporto.insert("end", f"Metodo: {esito.metodo}\n")

        if esito.note:
            self.rapporto.insert("end", "\nCosa riesce a fare\n", "etichetta")
            for nota in esito.note:
                self.rapporto.insert("end", f"  - {nota}\n")

        if esito.problemi:
            self.rapporto.insert("end", "\nLimiti\n", "etichetta")
            for problema in esito.problemi:
                self.rapporto.insert("end", f"  - {problema}\n", "problema")

        if len(esito.alternative) > 1:
            self.rapporto.insert("end", "\nFamiglie di link trovate\n", "etichetta")
            for alt in esito.alternative:
                stato = "con disponibilita'" if alt["disponibilita"] else "senza disponibilita'"
                nota = " - sembra un elenco, non una scheda" if alt["sembra_elenco"] else ""
                self.rapporto.insert(
                    "end", f"  {alt['quanti']:>5} link  {alt['etichetta']}  ({stato}){nota}\n"
                )
            self.rapporto.insert(
                "end",
                "  Se la scelta automatica non e' quella giusta, cambiala qui sotto.\n",
                "parziale",
            )

        if esito.proposta:
            self.rapporto.insert("end", "\nConfigurazione proposta\n", "etichetta")
            self.rapporto.insert("end", f"  nome:      {esito.proposta['name']}\n")
            self.rapporto.insert("end", f"  tipo:      {TYPE_LABELS.get(esito.proposta['type'])}\n")
            self.rapporto.insert("end", f"  indirizzo: {esito.proposta['url']}\n")
            self.rapporto.insert("end", f"  controllo: ogni {esito.proposta['interval']} secondi\n")
            if esito.proposta.get("detail"):
                self.rapporto.insert("end", "  accerta la disponibilita' aprendo le schede\n")
            if esito.proposta.get("enabled") is False:
                self.rapporto.insert(
                    "end", "\n  Nasce spento: va rifinito a mano prima di usarlo.\n", "parziale"
                )
            self.btn_crea.configure(state="normal")
        else:
            self.btn_crea.configure(state="disabled")

        self.rapporto.configure(state="disabled")

        if len(esito.alternative) > 1:
            voci = [
                f"{a['etichetta']}  -  {a['quanti']} link"
                + ("  (con disponibilita')" if a["disponibilita"] else "")
                for a in esito.alternative
            ]
            self.combo_famiglia.configure(values=voci)
            self.var_famiglia.set(voci[0])
            self.riga_scelta.pack(fill="x", pady=(8, 0), before=self.btn_crea.master)
        else:
            self.riga_scelta.pack_forget()

    def _crea(self) -> None:
        if not (self.esito and self.esito.proposta):
            return

        proposta = dict(self.esito.proposta)
        alternative = self.esito.alternative

        # Se hai scelto una famiglia diversa da quella proposta, la si applica.
        if len(alternative) > 1 and self.var_famiglia.get():
            indice = self.combo_famiglia.current()
            if indice > 0:
                scelta = alternative[indice]
                opzioni = dict(proposta.get("options") or {})
                opzioni["pattern"] = scelta["pattern"]
                opzioni["base"] = scelta["base"]
                proposta["options"] = opzioni
                if not scelta["disponibilita"]:
                    proposta.pop("detail", None)

        self.result = proposta
        self.destroy()


# --------------------------------------------------------------------------- #
# Finestra dei preset
# --------------------------------------------------------------------------- #

class PresetDialog(tk.Toplevel):
    """Elenco dei siti gia' configurati, con la scheda di ciascuno."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.result: list[str] = []

        self.title("Siti predefiniti")
        self.transient(parent)
        self.palette, self.caratteri = parent.palette, parent.caratteri
        self.geometry("880x560")
        self.minsize(760, 480)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_visibility()
        centra_su(self, parent)
        self.focus()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Scegli un preset per vedere cosa fa. Ogni configurazione e' stata provata sul sito reale.",
            foreground=self.palette.secondario,
        ).pack(anchor="w", pady=(0, 8))

        panes = ttk.PanedWindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        panes.add(left, weight=1)

        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for site, group in presets.by_site().items():
            parent_id = self.tree.insert("", "end", text=site, open=True)
            for preset in group:
                self.tree.insert(parent_id, "end", iid=preset.key, text=preset.summary.split(".")[0])

        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_detail())

        right = ttk.Frame(panes)
        panes.add(right, weight=2)

        self.detail = tk.Text(right, wrap="word", state="disabled")
        theme.campo_testo(self.detail, self.palette, self.caratteri)
        self.detail.configure(relief="flat", borderwidth=0, padx=14, pady=10)
        detail_scroll = ttk.Scrollbar(right, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        self.detail.tag_configure("titolo", font=self.caratteri.sezione, spacing3=8)
        self.detail.tag_configure("sezione", font=self.caratteri.corpo_forte, spacing1=10, spacing3=4)
        self.detail.tag_configure("limite", foreground=self.palette.arancio)
        self.detail.tag_configure("azione", foreground=self.palette.rosso)
        self.detail.tag_configure("prova", foreground=self.palette.verde)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Chiudi", command=self.destroy).pack(side="right")
        self.btn_add = ttk.Button(buttons, text="Aggiungi il preset scelto", command=self._add, state="disabled")
        self.btn_add.pack(side="right", padx=6)
        ttk.Button(buttons, text="Aggiungi tutti", command=self._add_all).pack(side="left")

        self._write_detail("Seleziona un preset dall'elenco a sinistra.")

    def _selected_preset(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return presets.get(selection[0])

    def _write_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", text)
        self.detail.configure(state="disabled")

    def _show_detail(self) -> None:
        preset = self._selected_preset()
        self.btn_add.configure(state="normal" if preset else "disabled")
        if preset is None:
            self._write_detail("Seleziona un preset dall'elenco a sinistra.")
            return

        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", preset.name + "\n", "titolo")
        self.detail.insert("end", preset.detail + "\n")

        if preset.caveat:
            self.detail.insert("end", "\nCosa NON fa\n", "sezione")
            self.detail.insert("end", preset.caveat + "\n", "limite")

        if preset.needs_edit:
            self.detail.insert("end", "\nDa personalizzare\n", "sezione")
            self.detail.insert("end", preset.needs_edit + "\n", "azione")

        if preset.tested:
            self.detail.insert("end", "\nVerifica sul sito\n", "sezione")
            self.detail.insert("end", preset.tested + "\n", "prova")

        target = preset.target
        self.detail.insert("end", "\nConfigurazione\n", "sezione")
        self.detail.insert("end", f"  indirizzo:  {target['url']}\n")
        self.detail.insert("end", f"  tipo:       {TYPE_LABELS.get(target['type'], target['type'])}\n")
        self.detail.insert("end", f"  controllo:  ogni {target['interval']} secondi\n")
        self.detail.configure(state="disabled")

    def _add(self) -> None:
        preset = self._selected_preset()
        if preset:
            self.result = [preset.key]
            self.destroy()

    def _add_all(self) -> None:
        self.result = [p.key for p in presets.PRESETS]
        self.destroy()


# --------------------------------------------------------------------------- #
# Finestra impostazioni
# --------------------------------------------------------------------------- #

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, raw: dict[str, Any]) -> None:
        super().__init__(parent)
        self.result: dict[str, Any] | None = None

        self.title("Impostazioni")
        self.transient(parent)
        self.palette, self.caratteri = parent.palette, parent.caratteri
        self.resizable(False, False)

        defaults = dict(raw.get("defaults") or {})
        notifiers = dict(raw.get("notifiers") or {})

        def channel(name: str) -> dict:
            return dict(notifiers.get(name) or {})

        self.var_ua = tk.StringVar(value=defaults.get("user_agent", ""))
        self.var_robots = tk.BooleanVar(value=bool(defaults.get("respect_robots", True)))
        self.var_interval = tk.StringVar(value=f'{float(defaults.get("interval", 20)):g}')

        self.var_console = tk.BooleanVar(value=bool(channel("console").get("enabled", True)))
        self.var_desktop = tk.BooleanVar(value=bool(channel("desktop").get("enabled", True)))
        self.var_sound = tk.BooleanVar(value=bool(channel("desktop").get("sound", True)))
        self.var_tg = tk.BooleanVar(value=bool(channel("telegram").get("enabled", False)))
        self.var_tg_token = tk.StringVar(value=channel("telegram").get("bot_token", ""))
        self.var_tg_chat = tk.StringVar(value=channel("telegram").get("chat_id", ""))
        self.var_dc = tk.BooleanVar(value=bool(channel("discord").get("enabled", False)))
        self.var_dc_hook = tk.StringVar(value=channel("discord").get("webhook_url", ""))

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_visibility()
        centra_su(self, parent)
        self.focus()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        general = ttk.LabelFrame(outer, text="Generale", padding=10)
        general.pack(fill="x")
        general.columnconfigure(1, weight=1)

        ttk.Label(general, text="User-Agent").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(general, textvariable=self.var_ua, width=58).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(
            general,
            text="Mettici un contatto reale: se il tuo traffico da' problemi,\nil sito ha modo di scriverti invece di bloccarti e basta.",
            foreground=self.palette.secondario,
            justify="left",
        ).grid(row=1, column=1, sticky="w")

        ttk.Label(general, text="Intervallo predefinito").grid(row=2, column=0, sticky="w", pady=(10, 4))
        ttk.Spinbox(general, from_=MIN_INTERVAL_SECONDS, to=3600, increment=5, textvariable=self.var_interval, width=8).grid(
            row=2, column=1, sticky="w", pady=(10, 4)
        )

        ttk.Checkbutton(general, text="Rispetta robots.txt (consigliato)", variable=self.var_robots).grid(
            row=3, column=1, sticky="w", pady=(8, 0)
        )

        channels = ttk.LabelFrame(outer, text="Canali di notifica", padding=10)
        channels.pack(fill="x", pady=(12, 0))
        channels.columnconfigure(1, weight=1)

        ttk.Checkbutton(channels, text="Registro dell'applicazione", variable=self.var_console).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(channels, text="Notifica di Windows", variable=self.var_desktop).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(channels, text="con avviso sonoro", variable=self.var_sound).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=(20, 0)
        )

        ttk.Separator(channels).grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)

        ttk.Checkbutton(channels, text="Telegram", variable=self.var_tg).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(channels, text="Token del bot").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Entry(channels, textvariable=self.var_tg_token, width=48).grid(row=5, column=1, sticky="ew", pady=3)
        ttk.Label(channels, text="Chat ID").grid(row=6, column=0, sticky="w", pady=3)
        ttk.Entry(channels, textvariable=self.var_tg_chat, width=48).grid(row=6, column=1, sticky="ew", pady=3)
        ttk.Label(
            channels,
            text="Crea il bot con @BotFather, scrivigli, poi apri\napi.telegram.org/bot<TOKEN>/getUpdates per il chat ID.",
            foreground=self.palette.secondario,
            justify="left",
        ).grid(row=7, column=1, sticky="w")

        ttk.Separator(channels).grid(row=8, column=0, columnspan=2, sticky="ew", pady=10)

        ttk.Checkbutton(channels, text="Discord", variable=self.var_dc).grid(row=9, column=0, columnspan=2, sticky="w")
        ttk.Label(channels, text="URL webhook").grid(row=10, column=0, sticky="w", pady=3)
        ttk.Entry(channels, textvariable=self.var_dc_hook, width=48).grid(row=10, column=1, sticky="ew", pady=3)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Annulla", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Salva", command=self._save).pack(side="right", padx=6)

    def _save(self) -> None:
        try:
            interval = float(self.var_interval.get())
        except ValueError:
            messagebox.showwarning("Intervallo non valido", "Deve essere un numero.", parent=self)
            return
        if interval < MIN_INTERVAL_SECONDS:
            messagebox.showwarning(
                "Intervallo troppo basso",
                f"Il minimo consentito e' {MIN_INTERVAL_SECONDS:.0f} secondi.",
                parent=self,
            )
            return

        self.result = {
            "defaults": {
                "user_agent": self.var_ua.get().strip(),
                "respect_robots": self.var_robots.get(),
                "interval": interval,
            },
            "notifiers": {
                "console": {"enabled": self.var_console.get()},
                "desktop": {"enabled": self.var_desktop.get(), "sound": self.var_sound.get()},
                "telegram": {
                    "enabled": self.var_tg.get(),
                    "bot_token": self.var_tg_token.get().strip(),
                    "chat_id": self.var_tg_chat.get().strip(),
                },
                "discord": {"enabled": self.var_dc.get(), "webhook_url": self.var_dc_hook.get().strip()},
            },
        }
        self.destroy()


# --------------------------------------------------------------------------- #
# Finestra principale
# --------------------------------------------------------------------------- #

class App(tk.Tk):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = Path(config_path)
        self.events: queue.Queue = queue.Queue()
        self.thread: MonitorThread | None = None
        self.alert_urls: dict[str, str] = {}
        self.alert_count = 0

        self.title(f"Restock Monitor - {self.config_path.name}")
        self.geometry("1180x760")
        self.minsize(1000, 620)
        self._set_window_icon()

        self.palette, self.caratteri = theme.applica(self)

        try:
            self.raw = config.load_raw(self.config_path)
        except ConfigError as exc:
            messagebox.showerror("Configurazione illeggibile", str(exc))
            self.raw = {"defaults": {}, "notifiers": {}, "targets": []}

        self._build()
        self._attach_logging()
        self._refresh_targets()
        self._pump()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self) -> None:
        """Stessa icona del collegamento sul desktop, se e' stata generata."""
        icon = Path(__file__).resolve().parent.parent / "restock.ico"
        if not icon.is_file():
            return
        try:
            self.iconbitmap(default=str(icon))
        except tk.TclError as exc:
            log.debug("Icona della finestra non applicata: %s", exc)

    # -- costruzione ------------------------------------------------------- #

    def _build(self) -> None:
        self.edit_buttons = []
        p, c = self.palette, self.caratteri

        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)

        # --- barra laterale ------------------------------------------------
        barra = ttk.Frame(corpo, style="Barra.TFrame", width=200)
        barra.pack(side="left", fill="y")
        barra.pack_propagate(False)

        ttk.Label(barra, text="Restock Monitor", style="Barra.TLabel", font=c.sezione).pack(
            anchor="w", padx=18, pady=(22, 1)
        )
        ttk.Label(barra, text=self.config_path.name, style="BarraTitolo.TLabel").pack(
            anchor="w", padx=18, pady=(0, 18)
        )

        self.nav_buttons: dict[str, ttk.Button] = {}
        for chiave, etichetta in (("target", "Target"), ("avvisi", "Avvisi"), ("registro", "Registro")):
            bottone = ttk.Button(
                barra,
                text=etichetta,
                style="Nav.TButton",
                takefocus=False,
                command=lambda k=chiave: self._mostra_sezione(k),
            )
            bottone.pack(fill="x", padx=10, pady=1)
            self.nav_buttons[chiave] = bottone

        piede = ttk.Frame(barra, style="Barra.TFrame")
        piede.pack(side="bottom", fill="x", padx=18, pady=16)
        self.spia = tk.Canvas(piede, width=9, height=9, highlightthickness=0, background=p.barra)
        self.spia.create_oval(0, 0, 8, 8, fill=p.terziario, outline="", tags="punto")
        self.spia.pack(side="left", pady=(3, 0))
        self.status = tk.StringVar(value="Fermo")
        ttk.Label(piede, textvariable=self.status, style="BarraTitolo.TLabel", wraplength=150).pack(
            side="left", padx=8
        )

        # --- intestazione e sezioni ----------------------------------------
        principale = ttk.Frame(corpo)
        principale.pack(side="left", fill="both", expand=True)

        testata = ttk.Frame(principale)
        testata.pack(fill="x", padx=24, pady=(22, 14))

        self.titolo_sezione = tk.StringVar(value="Target")
        ttk.Label(testata, textvariable=self.titolo_sezione, style="Titolo.TLabel").pack(side="left")

        ttk.Button(testata, text="Impostazioni", command=self._open_settings, takefocus=False).pack(
            side="right"
        )
        self.btn_stop = ttk.Button(
            testata, text="Ferma", command=self._stop, state="disabled", takefocus=False
        )
        self.btn_stop.pack(side="right", padx=8)
        self.btn_start = ttk.Button(
            testata, text="Avvia", style="Accento.TButton", command=self._start, takefocus=False
        )
        self.btn_start.pack(side="right")

        self.sezioni: dict[str, ttk.Frame] = {}
        contenitore = ttk.Frame(principale)
        contenitore.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        for chiave in ("target", "avvisi", "registro"):
            telaio = ttk.Frame(contenitore)
            telaio.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.sezioni[chiave] = telaio

        self._build_sezione_target(self.sezioni["target"])
        self._build_sezione_avvisi(self.sezioni["avvisi"])
        self._build_sezione_registro(self.sezioni["registro"])
        self._mostra_sezione("target")

    # -- sezioni ------------------------------------------------------------ #

    def _riquadro(self, genitore: tk.Misc) -> ttk.Frame:
        """Contenitore bianco con bordo sottile: la 'scheda' delle impostazioni macOS."""
        telaio = ttk.Frame(genitore, style="Riquadro.TFrame")
        telaio.pack(fill="both", expand=True)
        return telaio

    def _build_sezione_target(self, genitore: ttk.Frame) -> None:
        # Sopra l'elenco: aggiungere. Sotto: agire su cio' che e' selezionato.
        # E' la divisione delle impostazioni di macOS, e soprattutto entra
        # nella larghezza della finestra senza tagliare i pulsanti.
        sopra = ttk.Frame(genitore)
        sopra.pack(fill="x", pady=(0, 10))
        for etichetta, comando in (
            ("Aggiungi sito", self._add_site),
            ("Preset", self._add_preset),
            ("A mano", self._add_target),
        ):
            bottone = ttk.Button(sopra, text=etichetta, command=comando, takefocus=False)
            bottone.pack(side="left", padx=(0, 6))
            self.edit_buttons.append(bottone)

        prova = ttk.Button(sopra, text="Prova adesso", command=self._probe_target, takefocus=False)
        prova.pack(side="right")
        self.edit_buttons.append(prova)

        riquadro = self._riquadro(genitore)

        colonne = ("attivo", "tipo", "ogni", "stato", "articoli", "disponibili", "ultimo")
        self.tree = ttk.Treeview(
            riquadro, columns=colonne, show="tree headings", selectmode="browse", height=12
        )
        self.tree.heading("#0", text="Nome", anchor="w")
        self.tree.column("#0", width=230, stretch=True)
        for chiave, etichetta, larghezza in (
            ("attivo", "Attivo", 56),
            ("tipo", "Tipo", 124),
            ("ogni", "Ogni", 52),
            ("stato", "Stato", 168),
            ("articoli", "Articoli", 62),
            ("disponibili", "Disponibili", 76),
            ("ultimo", "Controllo", 78),
        ):
            self.tree.heading(chiave, text=etichetta, anchor="w" if chiave == "stato" else "center")
            self.tree.column(
                chiave, width=larghezza, anchor="center" if chiave != "stato" else "w", stretch=False
            )

        self.tree.tag_configure("errore", foreground=self.palette.rosso)
        self.tree.tag_configure("attivo", foreground=self.palette.verde)
        self.tree.tag_configure("spento", foreground=self.palette.secondario)
        self.tree.tag_configure("disattivato", foreground=self.palette.terziario)
        self.tree.bind("<Double-1>", lambda _e: self._edit_target())
        self.tree.bind("<<TreeviewSelect>>", self._on_target_selected)

        scorrimento_automatico(riquadro, self.tree)
        self.tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)

        sotto = ttk.Frame(genitore)
        sotto.pack(fill="x", pady=(10, 0))
        for etichetta, comando in (
            ("Modifica", self._edit_target),
            ("Duplica", self._duplicate_target),
            ("Rimuovi", self._remove_target),
        ):
            bottone = ttk.Button(sotto, text=etichetta, command=comando, takefocus=False)
            bottone.pack(side="left", padx=(0, 6))
            self.edit_buttons.append(bottone)

        for etichetta, comando in (
            ("Attiva tutti", self._enable_all),
            ("Solo questo", self._only_this),
            ("Attiva / Disattiva", self._toggle_target),
        ):
            bottone = ttk.Button(sotto, text=etichetta, command=comando, takefocus=False)
            bottone.pack(side="right", padx=(6, 0))
            self.edit_buttons.append(bottone)

    def _build_sezione_avvisi(self, genitore: ttk.Frame) -> None:
        ttk.Label(
            genitore,
            text="Doppio clic su una riga per aprire la pagina del prodotto.",
            style="Secondario.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        riquadro = self._riquadro(genitore)

        self.alerts = ttk.Treeview(
            riquadro,
            columns=("ora", "target", "articolo", "prezzo", "link"),
            show="headings",
            selectmode="browse",
        )
        for chiave, etichetta, larghezza, allineamento in (
            ("ora", "Ora", 70, "center"),
            ("target", "Target", 190, "w"),
            ("articolo", "Articolo", 280, "w"),
            ("prezzo", "Prezzo", 80, "center"),
            ("link", "Link", 330, "w"),
        ):
            self.alerts.heading(chiave, text=etichetta, anchor=allineamento)
            self.alerts.column(chiave, width=larghezza, anchor=allineamento)
        self.alerts.bind("<Double-1>", self._open_alert)

        scorrimento_automatico(riquadro, self.alerts)
        self.alerts.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)

    def _build_sezione_registro(self, genitore: ttk.Frame) -> None:
        barra = ttk.Frame(genitore)
        barra.pack(fill="x", pady=(0, 12))
        ttk.Label(
            barra,
            text="Ogni target ha il suo registro. Selezionandone uno nell'elenco si apre il suo.",
            style="Secondario.TLabel",
        ).pack(side="left")
        ttk.Button(barra, text="Svuota", command=self._clear_log, takefocus=False).pack(side="right")

        riquadro = self._riquadro(genitore)
        self.log_notebook = ttk.Notebook(riquadro)
        self.log_notebook.pack(fill="both", expand=True, padx=1, pady=1)

        # La scheda generale raccoglie solo cio' che non appartiene a un target:
        # avvio, salvataggi, pause a livello di host.
        self.log_panels: dict[str, LogPanel] = {"": LogPanel(self.log_notebook, self.palette, self.caratteri)}
        self.log_notebook.add(self.log_panels[""], text="Generale")

    def _mostra_sezione(self, chiave: str) -> None:
        titoli = {"target": "Target", "avvisi": "Avvisi", "registro": "Registro"}
        self.sezione_attiva = chiave
        self.titolo_sezione.set(titoli[chiave])
        self.sezioni[chiave].tkraise()
        for nome, bottone in self.nav_buttons.items():
            bottone.configure(style="NavAttiva.TButton" if nome == chiave else "Nav.TButton")

    def _attach_logging(self) -> None:
        handler = QueueLogHandler(self.events)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    # -- gestione dei target ----------------------------------------------- #

    @property
    def targets(self) -> list[dict[str, Any]]:
        return self.raw.setdefault("targets", [])

    def _refresh_targets(self) -> None:
        # Le colonne di runtime (stato, conteggi, ora) vanno conservate: un
        # salvataggio non deve azzerare cio' che il monitor ha gia' rilevato.
        previous = {iid: self.tree.item(iid, "values") for iid in self.tree.get_children()}
        self.tree.delete(*self.tree.get_children())

        for target in self.targets:
            name = str(target.get("name", "?"))
            enabled = bool(target.get("enabled", True))

            runtime = previous.get(name, ())[3:]
            if len(runtime) != 4:
                runtime = ("in attesa", "-", "-", "-")

            values = (
                "Sì" if enabled else "No",
                TYPE_LABELS.get(target.get("type", ""), target.get("type", "?")),
                _secondi(target.get("interval")),
                *runtime,
            )
            self.tree.insert(
                "",
                "end",
                iid=name,
                text=name,
                values=values,
                tags=("spento" if enabled else "disattivato",),
            )

        self._sync_log_tabs()
        self._update_status()

    def _on_target_selected(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if selection:
            self._focus_log(selection[0])

    def _selected(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Nessuna selezione", "Seleziona prima un target dall'elenco.", parent=self)
            return None
        name = selection[0]
        for index, target in enumerate(self.targets):
            if str(target.get("name")) == name:
                return index
        return None

    def _names(self) -> set[str]:
        return {str(t.get("name")) for t in self.targets}

    def _toggle_target(self) -> None:
        index = self._selected()
        if index is None:
            return
        target = self.targets[index]
        was = bool(target.get("enabled", True))
        target["enabled"] = not was
        if self._persist():
            self._refresh_targets()
            self.tree.selection_set(str(target.get("name")))
            stato = "attivato" if not was else "disattivato"
            self._log_line(logging.INFO, f"Target {stato}.", target=str(target.get("name")))
        else:
            target["enabled"] = was

    def _only_this(self) -> None:
        """Lascia attivo solo il target selezionato, spegnendo tutti gli altri."""
        index = self._selected()
        if index is None:
            return
        name = str(self.targets[index].get("name"))
        previous = [bool(t.get("enabled", True)) for t in self.targets]

        for position, target in enumerate(self.targets):
            target["enabled"] = position == index

        if self._persist():
            self._refresh_targets()
            self.tree.selection_set(name)
            self._log_line(logging.INFO, f"Attivo solo: {name}")
        else:
            for target, was in zip(self.targets, previous):
                target["enabled"] = was

    def _enable_all(self) -> None:
        previous = [bool(t.get("enabled", True)) for t in self.targets]
        for target in self.targets:
            target["enabled"] = True
        if self._persist():
            self._refresh_targets()
            self._log_line(logging.INFO, f"Attivati tutti i target ({len(self.targets)}).")
        else:
            for target, was in zip(self.targets, previous):
                target["enabled"] = was

    def _add_site(self) -> None:
        """Analizza un sito o un prodotto e crea il target adatto."""
        defaults = self.raw.get("defaults") or {}
        dialog = SiteWizard(
            self,
            str(defaults.get("user_agent") or config.DEFAULT_USER_AGENT),
            bool(defaults.get("respect_robots", True)),
        )
        self.wait_window(dialog)
        if not dialog.result:
            return

        proposta = dialog.result
        base = str(proposta.get("name") or "Nuovo target")
        nome, contatore = base, 2
        while nome in self._names():
            nome = f"{base} {contatore}"
            contatore += 1
        proposta["name"] = nome

        self.targets.append(proposta)
        if not self._persist():
            self.targets.pop()
            return

        self._refresh_targets()
        self.tree.selection_set(nome)
        messaggio = f"Aggiunto: {nome}\n\nUsa 'Prova adesso' per vedere subito cosa legge."
        if proposta.get("enabled") is False:
            messaggio += "\n\nNasce spento: va rifinito a mano prima di attivarlo."
        messagebox.showinfo("Target creato", messaggio, parent=self)

    def _add_preset(self) -> None:
        dialog = PresetDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return

        added, to_edit = [], []
        for key in dialog.result:
            preset = presets.get(key)
            if preset is None:
                continue
            self.targets.append(presets.instantiate(preset, self._names()))
            added.append(preset.name)
            if preset.needs_edit:
                to_edit.append(f"- {preset.name}\n  {preset.needs_edit}")

        if not added:
            return
        if not self._persist():
            # Salvataggio rifiutato: non lasciare in memoria target non validi.
            del self.targets[-len(added):]
            return

        self._refresh_targets()
        message = f"Aggiunti {len(added)} target." if len(added) > 1 else f"Aggiunto: {added[0]}"
        if to_edit:
            message += "\n\nDa personalizzare prima di avviare:\n" + "\n".join(to_edit)
        message += "\n\nUsa 'Prova adesso' per verificare che il sito risponda."
        messagebox.showinfo("Preset aggiunti", message, parent=self)

    def _add_target(self) -> None:
        dialog = TargetDialog(self, None, self._names())
        self.wait_window(dialog)
        if dialog.result:
            self.targets.append(dialog.result)
            if self._persist():
                self._refresh_targets()

    def _edit_target(self) -> None:
        index = self._selected()
        if index is None:
            return
        dialog = TargetDialog(self, self.targets[index], self._names())
        self.wait_window(dialog)
        if dialog.result:
            self.targets[index] = dialog.result
            if self._persist():
                self._refresh_targets()

    def _duplicate_target(self) -> None:
        index = self._selected()
        if index is None:
            return
        clone = dict(self.targets[index])
        base = f"{clone.get('name')} (copia)"
        name, counter = base, 2
        while name in self._names():
            name = f"{base} {counter}"
            counter += 1
        clone["name"] = name
        self.targets.append(clone)
        if self._persist():
            self._refresh_targets()

    def _remove_target(self) -> None:
        index = self._selected()
        if index is None:
            return
        name = self.targets[index].get("name")
        if not messagebox.askyesno("Conferma", f"Rimuovere il target '{name}'?", parent=self):
            return
        del self.targets[index]
        if self._persist():
            self._refresh_targets()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, self.raw)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.raw.setdefault("defaults", {}).update(dialog.result["defaults"])
        self.raw["notifiers"] = dialog.result["notifiers"]
        self._persist()

    # -- persistenza -------------------------------------------------------- #

    def _persist(self) -> bool:
        """Valida su un file temporaneo, poi scrive. Non salva mai config non valide."""
        probe = self.config_path.with_suffix(".validate.tmp")
        try:
            config.save_raw(probe, self.raw)
            config.load(probe)
        except ConfigError as exc:
            messagebox.showerror("Configurazione non valida", str(exc), parent=self)
            return False
        finally:
            probe.unlink(missing_ok=True)

        config.save_raw(self.config_path, self.raw)
        self._log_line(logging.INFO, f"Configurazione salvata in {self.config_path.name}")
        return True

    def _settings_or_warn(self):
        try:
            return config.load(self.config_path)
        except ConfigError as exc:
            messagebox.showerror("Configurazione non valida", str(exc), parent=self)
            return None

    # -- esecuzione --------------------------------------------------------- #

    def _start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        if not self.targets:
            messagebox.showinfo("Nessun target", "Aggiungi almeno un target prima di avviare.", parent=self)
            return

        if not [t for t in self.targets if t.get("enabled", True)]:
            messagebox.showinfo(
                "Nessun target attivo",
                "Tutti i target sono disattivati.\n\n"
                "Selezionane uno e usa 'Attiva / Disattiva', oppure 'Attiva tutti'.",
                parent=self,
            )
            return

        settings = self._settings_or_warn()
        if settings is None:
            return

        self.thread = MonitorThread(settings, QueueObserver(self.events), self.events)
        self.thread.start()

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        for button in self.edit_buttons:
            button.configure(state="disabled")
        for iid in self.tree.get_children():
            self._set_cell(iid, "stato", "in attesa", "spento")
        self._update_status()

    def _stop(self) -> None:
        if self.thread:
            self._log_line(logging.INFO, "Arresto in corso...")
            self.thread.stop()
        self.btn_stop.configure(state="disabled")

    def _on_stopped(self) -> None:
        self.thread = None
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        for button in self.edit_buttons:
            button.configure(state="normal")
        for iid in self.tree.get_children():
            self._set_cell(iid, "stato", "fermo", "spento")
        self._update_status()

    def _probe_target(self) -> None:
        """Interroga una volta sola il target selezionato e mostra l'esito."""
        index = self._selected()
        if index is None:
            return
        settings = self._settings_or_warn()
        if settings is None:
            return

        name = str(self.targets[index].get("name"))
        target = next((t for t in settings.targets if t.name == name), None)
        if target is None:
            return

        self._log_line(logging.INFO, "Prova in corso...", target=name)
        self._focus_log(name)

        def work() -> None:
            async def run() -> None:
                monitor = Monitor(settings, observer=QueueObserver(self.events))
                try:
                    items = await monitor.poll_once(target)
                finally:
                    await monitor.close()

                if items is None:
                    self.events.put(("probe", name, False, "Nessuna risposta utilizzabile - controlla URL e tipo."))
                    return
                if target.checks_detail:
                    accertati = [i for i in items if i.verified]
                    available = [i for i in accertati if i.available]
                    lines = [
                        f"{len(items)} articoli letti.",
                        f"{len(available)} disponibili fra i {len(accertati)} accertati in questo giro.",
                    ]
                    if len(items) > len(accertati):
                        lines.append(
                            f"{len(items) - len(accertati)} non ancora accertati: le schede si "
                            f"aprono poche per giro, a rotazione."
                        )
                else:
                    available = [i for i in items if i.available]
                    lines = [f"{len(items)} articoli letti, {len(available)} disponibili."]

                if available:
                    lines.append("")
                    for item in available[:12]:
                        price = f"   {item.price}" if item.price else ""
                        lines.append(f"  {item.title}{price}")
                    if len(available) > 12:
                        lines.append(f"  ... e altri {len(available) - 12}")
                self.events.put(("probe", name, True, "\n".join(lines)))

            try:
                asyncio.run(run())
            except Exception as exc:
                self.events.put(("probe", name, False, f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _test_notify(self) -> None:
        settings = self._settings_or_warn()
        if settings is None:
            return

        def work() -> None:
            async def run() -> None:
                dispatcher = Dispatcher(settings.notifiers)
                if not dispatcher.enabled:
                    self.events.put(("log", logging.WARNING, "Nessun canale di notifica abilitato."))
                    return
                change = Change(
                    target="Prova",
                    item=Item(key="test", title="Notifica di prova", available=True, url="https://example.com", price="99.00"),
                    kind="restock",
                )
                await dispatcher.dispatch(change, dispatcher.enabled)
                self.events.put(("log", logging.INFO, f"Notifica di prova inviata su: {', '.join(dispatcher.enabled)}"))

            asyncio.run(run())

        threading.Thread(target=work, daemon=True).start()

    # -- coda degli eventi --------------------------------------------------- #

    def _pump(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.after(150, self._pump)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]

        if kind == "log":
            # Le voci senza target (avvio, errori di host) finiscono in Generale.
            self._log_line(event[1], event[2], target=event[3] if len(event) > 3 else None)

        elif kind == "poll":
            _, name, ok, total, available, detail = event
            stamp = datetime.now().strftime("%H:%M:%S")
            if ok:
                self._set_cell(name, "stato", "attivo", "attivo")
                self._set_cell(name, "articoli", str(total))
                self._set_cell(name, "disponibili", str(available))
            else:
                self._set_cell(name, "stato", detail or "errore", "errore")
            self._set_cell(name, "ultimo", stamp)

        elif kind == "change":
            _, target, change_kind, title, price, url = event
            self.alert_count += 1
            stamp = datetime.now().strftime("%H:%M:%S")
            iid = f"alert{self.alert_count}"
            self.alerts.insert("", 0, iid=iid, values=(stamp, target, title, price, url))
            self.alert_urls[iid] = url
            label = "RESTOCK" if change_kind == "restock" else "NUOVO"
            self._log_line(logging.INFO, f"{stamp}  *** {label}: {title}", tag="RESTOCK", target=target)
            self._update_status()

        elif kind == "disabled":
            _, name, reason = event
            self._set_cell(name, "stato", "disattivato da robots.txt", "errore")

        elif kind == "probe":
            _, name, ok, detail = event
            self._log_line(
                logging.INFO if ok else logging.WARNING,
                "Prova: " + detail.splitlines()[0],
                target=name,
            )
            if ok:
                messagebox.showinfo(f"Prova: {name}", detail, parent=self)
            else:
                messagebox.showerror(f"Prova: {name}", detail, parent=self)

        elif kind == "doppione":
            # Il monitor si e' rifiutato di partire: c'e' gia' un'istanza attiva,
            # quasi sempre quella avviata automaticamente all'accesso.
            self._log_line(logging.WARNING, event[1])
            messagebox.showinfo("Monitor gia' attivo", event[1], parent=self)

        elif kind == "stopped":
            self._on_stopped()

    def _set_cell(self, iid: str, column: str, value: str, tag: str | None = None) -> None:
        if not self.tree.exists(iid):
            return
        self.tree.set(iid, column, value)
        if tag:
            self.tree.item(iid, tags=(tag,))

    def _sync_log_tabs(self) -> None:
        """Allinea le schede del registro all'elenco dei target."""
        wanted = [str(t.get("name")) for t in self.targets]

        for name in list(self.log_panels):
            if name and name not in wanted:
                panel = self.log_panels.pop(name)
                self.log_notebook.forget(panel)
                panel.destroy()

        for name in wanted:
            if name not in self.log_panels:
                panel = LogPanel(self.log_notebook, self.palette, self.caratteri)
                self.log_panels[name] = panel
                label = name if len(name) <= 24 else name[:23] + "…"
                self.log_notebook.add(panel, text=label)

    def _focus_log(self, name: str) -> None:
        panel = self.log_panels.get(name)
        if panel is not None:
            self.log_notebook.select(panel)

    def _clear_log(self) -> None:
        """Svuota solo la scheda in primo piano."""
        current = self.log_notebook.select()
        for panel in self.log_panels.values():
            if str(panel) == current:
                panel.clear()
                return

    def _log_line(self, level: int, text: str, tag: str | None = None, target: str | None = None) -> None:
        if tag is None:
            tag = logging.getLevelName(level) if level >= logging.WARNING else ""
        panel = self.log_panels.get(target or "") or self.log_panels[""]
        panel.append(text, tag or None)

    def _open_alert(self, _event: tk.Event) -> None:
        selection = self.alerts.selection()
        if not selection:
            return
        url = self.alert_urls.get(selection[0])
        if url:
            webbrowser.open(url)

    def _update_status(self) -> None:
        running = bool(self.thread and self.thread.is_alive())
        active = sum(1 for t in self.targets if t.get("enabled", True))
        self.status.set(
            ("In esecuzione" if running else "Fermo")
            + f"\n{active} attivi su {len(self.targets)}"
        )
        self.spia.itemconfigure(
            "punto", fill=self.palette.verde if running else self.palette.terziario
        )
        if "avvisi" in self.nav_buttons:
            etichetta = "Avvisi" if not self.alert_count else f"Avvisi  ({self.alert_count})"
            self.nav_buttons["avvisi"].configure(text=etichetta)

    def _on_close(self) -> None:
        if self.thread and self.thread.is_alive():
            if not messagebox.askyesno("Monitoraggio attivo", "Il monitor e' in esecuzione. Uscire comunque?", parent=self):
                return
            self.thread.stop()
            self.thread.join(timeout=5)
        self.destroy()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    config_path = Path(argv[0]) if argv else Path("config.yaml")
    App(config_path).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
