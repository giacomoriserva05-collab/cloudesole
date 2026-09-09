"""Aspetto dell'interfaccia, ispirato alle impostazioni di macOS.

San Francisco non esiste su Windows, ma Segoe UI Variable e' il carattere
moderno di Windows 11 e ha la stessa impostazione ottica: molto piu' vicino a
SF Pro del vecchio Segoe UI. Cascadia Mono fa le veci di SF Mono.

Il tema di base e' 'clam' e non 'vista': vista disegna i controlli con le
primitive native e ignora quasi tutte le personalizzazioni, clam invece si
lascia ridipingere completamente.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .imaging import png_rgba, riduci


class Palette:
    """Colori di sistema di macOS, chiari."""

    # Superfici
    finestra = "#ECECEE"
    barra = "#E8E8EB"        # barra laterale
    contenuto = "#FFFFFF"    # riquadri dei contenuti
    campo = "#FFFFFF"
    evidenziato = "#F5F5F7"

    # Testo
    testo = "#1D1D1F"
    secondario = "#6E6E73"
    terziario = "#8E8E93"
    su_accento = "#FFFFFF"

    # Linee
    separatore = "#D8D8DC"
    bordo = "#C9C9CE"

    # Colori di sistema
    accento = "#007AFF"
    accento_scuro = "#0062CC"
    verde = "#28A745"
    arancio = "#B26A00"
    rosso = "#D7263D"


def _famiglia(disponibili: set[str], *preferenze: str) -> str:
    for nome in preferenze:
        if nome in disponibili:
            return nome
    return "Segoe UI"


class Caratteri:
    def __init__(self, disponibili: set[str]) -> None:
        display = _famiglia(disponibili, "Segoe UI Variable Display", "Segoe UI", "Arial")
        testo = _famiglia(disponibili, "Segoe UI Variable Text", "Segoe UI", "Arial")
        piccolo = _famiglia(disponibili, "Segoe UI Variable Small", "Segoe UI", "Arial")
        mono = _famiglia(disponibili, "Cascadia Mono", "Consolas", "Courier New")

        self.titolo = (display, 17)
        self.sezione = (display, 13)
        self.corpo = (testo, 10)
        self.corpo_forte = (testo, 10, "bold")
        self.minuto = (piccolo, 9)
        self.mono = (mono, 9)


LATO = 15          # lato dell'indicatore in pixel
SUPER = 6          # fattore di sovracampionamento per l'antialiasing


def _rgb(colore: str) -> tuple[int, int, int]:
    return tuple(int(colore[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _dentro_tondo(px: float, py: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if not (x0 <= px <= x1 and y0 <= py <= y1):
        return False
    qx = max(x0 + r - px, px - (x1 - r), 0.0)
    qy = max(y0 + r - py, py - (y1 - r), 0.0)
    return qx * qx + qy * qy <= r * r


def _vicino_al_segmento(px, py, ax, ay, bx, by, spessore) -> bool:
    dx, dy = bx - ax, by - ay
    lunghezza = dx * dx + dy * dy
    t = 0.0 if lunghezza == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / lunghezza))
    cx, cy = ax + t * dx, ay + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2 <= (spessore / 2) ** 2


def _disegna_indicatore(p: Palette, spuntato: bool, tondo: bool) -> bytes:
    """Casella o pallino di macOS: bianco col bordo, oppure blu con il segno."""
    grande = LATO * SUPER
    pixels = bytearray(grande * grande * 4)

    bordo = _rgb(p.bordo)
    accento = _rgb(p.accento)
    campo = _rgb(p.campo)
    segno = _rgb(p.su_accento)

    raggio = grande / 2 if tondo else grande * 0.28
    spessore = SUPER * 1.3

    for riga in range(grande):
        py = riga + 0.5
        for colonna in range(grande):
            px = colonna + 0.5
            colore = None

            dentro = _dentro_tondo(px, py, 0.6 * SUPER, 0.6 * SUPER, grande - 0.6 * SUPER, grande - 0.6 * SUPER, raggio)
            if dentro:
                colore = accento if spuntato else campo
                # Bordo: la cornice esterna di un paio di pixel.
                if not _dentro_tondo(
                    px, py, 1.7 * SUPER, 1.7 * SUPER, grande - 1.7 * SUPER, grande - 1.7 * SUPER, max(0.0, raggio - SUPER)
                ) and not spuntato:
                    colore = bordo

            if spuntato and dentro:
                if tondo:
                    centro = grande / 2
                    if (px - centro) ** 2 + (py - centro) ** 2 <= (grande * 0.17) ** 2:
                        colore = segno
                else:
                    # Il baffo: due segmenti, come il segno di spunta di Apple.
                    u = grande / LATO
                    if _vicino_al_segmento(px, py, 4.0 * u, 7.8 * u, 6.4 * u, 10.3 * u, spessore) or _vicino_al_segmento(
                        px, py, 6.4 * u, 10.3 * u, 11.0 * u, 4.8 * u, spessore
                    ):
                        colore = segno

            if colore is not None:
                i = (riga * grande + colonna) * 4
                pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3] = *colore, 255

    return png_rgba(riduci(pixels, grande, LATO), LATO)


def _indicatori_a_immagine(root, style: ttk.Style, p: Palette) -> None:
    """Sostituisce la X del tema clam con una vera casella spuntata.

    clam disegna il segno di spunta come una X: e' il dettaglio che piu' di
    tutti tradisce l'origine dell'interfaccia. Non si cambia con le opzioni di
    stile, serve un elemento a immagine.
    """
    immagini = {
        nome: tk.PhotoImage(master=root, data=_disegna_indicatore(p, spuntato, tondo))
        for nome, spuntato, tondo in (
            ("check_off", False, False),
            ("check_on", True, False),
            ("radio_off", False, True),
            ("radio_on", True, True),
        )
    }
    # Tk non tiene un riferimento alle immagini: senza questo spariscono.
    root._indicatori = immagini  # type: ignore[attr-defined]

    for prefisso, widget in (("check", "TCheckbutton"), ("radio", "TRadiobutton")):
        elemento = f"Mac.{widget}.indicator"
        style.element_create(
            elemento,
            "image",
            immagini[f"{prefisso}_off"],
            ("selected", immagini[f"{prefisso}_on"]),
            sticky="",
            # Respiro fra il riquadro e la sua etichetta.
            padding=(0, 0, 7, 0),
        )
        style.layout(
            widget,
            [
                (
                    f"{widget}.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            (elemento, {"side": "left", "sticky": ""}),
                            (
                                f"{widget}.focus",
                                {
                                    "side": "left",
                                    "sticky": "w",
                                    "children": [(f"{widget}.label", {"sticky": "nswe"})],
                                },
                            ),
                        ],
                    },
                )
            ],
        )


def applica(root) -> tuple[Palette, Caratteri]:
    """Ridipinge i widget ttk e restituisce palette e caratteri da riusare."""
    p = Palette()
    c = Caratteri(set(tkfont.families(root)))

    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(background=p.finestra)

    # --- superfici ---------------------------------------------------------
    style.configure("TFrame", background=p.finestra)
    style.configure("Barra.TFrame", background=p.barra)
    style.configure("Contenuto.TFrame", background=p.contenuto)
    style.configure(
        "Riquadro.TFrame",
        background=p.contenuto,
        relief="solid",
        borderwidth=1,
        bordercolor=p.separatore,
    )

    # --- testo -------------------------------------------------------------
    style.configure("TLabel", background=p.finestra, foreground=p.testo, font=c.corpo)
    style.configure("Titolo.TLabel", font=c.titolo, foreground=p.testo)
    style.configure("Sezione.TLabel", font=c.sezione, foreground=p.testo)
    style.configure("Secondario.TLabel", foreground=p.secondario, font=c.minuto)
    style.configure("Barra.TLabel", background=p.barra, foreground=p.testo, font=c.corpo)
    style.configure(
        "BarraTitolo.TLabel", background=p.barra, foreground=p.terziario, font=c.minuto
    )
    style.configure("Contenuto.TLabel", background=p.contenuto, foreground=p.testo, font=c.corpo)
    style.configure(
        "ContenutoSecondario.TLabel",
        background=p.contenuto,
        foreground=p.secondario,
        font=c.minuto,
    )

    # --- pulsanti ----------------------------------------------------------
    # Piatti, con molto respiro interno: e' il respiro, non il bordo, a dare
    # l'aria dei controlli di macOS.
    style.configure(
        "TButton",
        background=p.contenuto,
        foreground=p.testo,
        font=c.corpo,
        relief="flat",
        borderwidth=1,
        bordercolor=p.bordo,
        focuscolor=p.contenuto,
        padding=(12, 6),
    )
    style.map(
        "TButton",
        background=[("pressed", p.evidenziato), ("active", p.evidenziato), ("disabled", p.finestra)],
        foreground=[("disabled", p.terziario)],
        bordercolor=[("disabled", p.separatore)],
    )

    style.configure(
        "Accento.TButton",
        background=p.accento,
        foreground=p.su_accento,
        bordercolor=p.accento,
        font=c.corpo_forte,
        padding=(16, 6),
    )
    style.map(
        "Accento.TButton",
        background=[("pressed", p.accento_scuro), ("active", p.accento_scuro), ("disabled", "#B9DBFF")],
        bordercolor=[("disabled", "#B9DBFF")],
        foreground=[("disabled", "#F0F6FF")],
    )

    # Voci della barra laterale: nessun bordo, testo allineato a sinistra.
    style.configure(
        "Nav.TButton",
        background=p.barra,
        foreground=p.testo,
        font=c.corpo,
        relief="flat",
        borderwidth=0,
        anchor="w",
        padding=(14, 8),
    )
    style.map("Nav.TButton", background=[("active", "#DEDEE2")])
    style.configure(
        "NavAttiva.TButton",
        background=p.accento,
        foreground=p.su_accento,
        font=c.corpo_forte,
        relief="flat",
        borderwidth=0,
        anchor="w",
        padding=(14, 8),
    )
    style.map("NavAttiva.TButton", background=[("active", p.accento)])

    # --- elenchi -----------------------------------------------------------
    style.configure(
        "Treeview",
        background=p.contenuto,
        fieldbackground=p.contenuto,
        foreground=p.testo,
        font=c.corpo,
        rowheight=30,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", p.accento)],
        foreground=[("selected", p.su_accento)],
    )
    style.configure(
        "Treeview.Heading",
        background=p.contenuto,
        foreground=p.secondario,
        font=c.minuto,
        relief="flat",
        borderwidth=0,
        padding=(8, 8),
    )
    style.map("Treeview.Heading", background=[("active", p.evidenziato)])

    # --- campi -------------------------------------------------------------
    for nome in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(
            nome,
            fieldbackground=p.campo,
            background=p.campo,
            foreground=p.testo,
            bordercolor=p.bordo,
            lightcolor=p.bordo,
            darkcolor=p.bordo,
            borderwidth=1,
            relief="flat",
            arrowcolor=p.secondario,
            padding=(6, 5),
        )
        style.map(nome, bordercolor=[("focus", p.accento)], lightcolor=[("focus", p.accento)])

    # Le finestre di dialogo hanno lo sfondo grigio della finestra, con i
    # gruppi come riquadri: caselle e radio devono intonarsi a quello, non al
    # bianco dei contenuti, altrimenti restano dei rettangoli chiari attorno.
    for nome in ("TCheckbutton", "TRadiobutton"):
        style.configure(
            nome,
            background=p.finestra,
            foreground=p.testo,
            font=c.corpo,
            focuscolor=p.finestra,
            # Le opzioni giuste per clam sono queste due: 'indicatorcolor' viene
            # accettato senza errori ma non ha alcun effetto.
            indicatorbackground=p.campo,
            indicatorforeground=p.su_accento,
            indicatormargin=(0, 0, 8, 0),
            upperbordercolor=p.bordo,
            lowerbordercolor=p.bordo,
            padding=(2, 4),
        )
        style.map(
            nome,
            background=[("active", p.finestra)],
            # Spuntata: riquadro pieno di blu con il segno bianco.
            indicatorbackground=[
                ("selected", p.accento),
                ("active", "#F0F0F2"),
                ("disabled", p.finestra),
            ],
            upperbordercolor=[("selected", p.accento), ("focus", p.accento)],
            lowerbordercolor=[("selected", p.accento), ("focus", p.accento)],
        )

    style.configure("TLabelframe", background=p.finestra, bordercolor=p.separatore, borderwidth=1)
    style.configure(
        "TLabelframe.Label", background=p.finestra, foreground=p.secondario, font=c.minuto
    )

    # Se la creazione degli elementi a immagine fallisce (Tk troppo vecchio,
    # nome gia' registrato), restano validi gli stili impostati sopra.
    try:
        _indicatori_a_immagine(root, style, p)
    except tk.TclError:
        pass

    style.configure("TSeparator", background=p.separatore)
    style.configure("TPanedwindow", background=p.finestra)

    # --- schede (usate solo per i registri per target) ---------------------
    style.configure("TNotebook", background=p.contenuto, borderwidth=0, tabmargins=(6, 4, 6, 0))
    style.configure(
        "TNotebook.Tab",
        background=p.contenuto,
        foreground=p.secondario,
        font=c.minuto,
        padding=(12, 6),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", p.evidenziato)],
        foreground=[("selected", p.testo)],
    )

    # --- barre di scorrimento: sottili, senza frecce -----------------------
    for orientamento in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            orientamento,
            background="#C7C7CC",
            troughcolor=p.contenuto,
            bordercolor=p.contenuto,
            arrowcolor=p.contenuto,
            borderwidth=0,
            relief="flat",
            width=11,
        )
        style.map(orientamento, background=[("active", "#A9A9AE")])

    return p, c


def campo_testo(widget, palette: Palette, caratteri: Caratteri, mono: bool = False) -> None:
    """Intona un widget tk.Text al tema: tk non conosce gli stili di ttk."""
    widget.configure(
        background=palette.campo,
        foreground=palette.testo,
        insertbackground=palette.testo,
        selectbackground=palette.accento,
        selectforeground=palette.su_accento,
        font=caratteri.mono if mono else caratteri.corpo,
        relief="solid",
        borderwidth=1,
        highlightthickness=0,
        padx=8,
        pady=6,
    )
