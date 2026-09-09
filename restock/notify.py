"""Canali di notifica. Un canale che fallisce non deve mai fermare il monitor."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from typing import Any

import httpx

from .models import Change

log = logging.getLogger(__name__)


MAX_TAGLIE = 12

# Quante taglie per riga nella tastiera di Telegram: piu' di tre e i pulsanti
# diventano troppo stretti da centrare col pollice.
PER_RIGA = 3


def taglie_disponibili(change: Change) -> list[dict]:
    elenco = change.item.extra.get("taglie") or []
    return [t for t in elenco if t.get("disponibile")]


def link_taglia(change: Change, taglia: dict) -> str:
    """Indirizzo della pagina con quella taglia gia' selezionata."""
    if taglia.get("id"):
        separatore = "&" if "?" in change.item.url else "?"
        return f"{change.item.url}{separatore}variant={taglia['id']}"
    return change.item.url


def tastiera_taglie(change: Change) -> dict | None:
    """Pulsanti di Telegram: uno per taglia, che apre la pagina gia' impostata.

    E' la differenza fra leggere un indirizzo e premere la taglia che si vuole:
    dal messaggio si arriva al prodotto con la misura gia' scelta, in un tocco.
    """
    disponibili = taglie_disponibili(change)[:MAX_TAGLIE]
    if not disponibili:
        return None

    righe = []
    for inizio in range(0, len(disponibili), PER_RIGA):
        righe.append(
            [
                {"text": taglia["nome"], "url": link_taglia(change, taglia)}
                for taglia in disponibili[inizio : inizio + PER_RIGA]
            ]
        )
    righe.append([{"text": "Apri il prodotto", "url": change.item.url}])
    return {"inline_keyboard": righe}


def _riga_taglie(change: Change) -> str:
    """Elenco delle taglie acquistabili, con il link diretto a ciascuna.

    Il link con la variante gia' scelta porta alla pagina con quella taglia
    selezionata: e' il percorso piu' corto fra l'avviso e il carrello. Chi
    compra resti pero' tu: il monitor non aggiunge al carrello e non ordina.
    """
    elenco = change.item.extra.get("taglie") or []
    if not elenco:
        return ""

    disponibili = [t for t in elenco if t.get("disponibile")]
    if not disponibili:
        return f"\n\nNessuna taglia disponibile (su {len(elenco)})."

    righe = [f"\n\nTaglie disponibili ({len(disponibili)} su {len(elenco)}):"]
    for taglia in disponibili[:MAX_TAGLIE]:
        if taglia.get("id"):
            righe.append(f"  {taglia['nome']}  ->  {link_taglia(change, taglia)}")
        else:
            righe.append(f"  {taglia['nome']}")
    if len(disponibili) > MAX_TAGLIE:
        righe.append(f"  ... e altre {len(disponibili) - MAX_TAGLIE}")
    return "\n".join(righe)


def _line(change: Change) -> str:
    price = f" | {change.item.price}" if change.item.price else ""
    return f"{change.headline}{price}\n{change.item.url}{_riga_taglie(change)}"


class Notifier:
    name = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def send(self, change: Change) -> None:
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    name = "console"

    async def send(self, change: Change) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        price = f"  {change.item.price}" if change.item.price else ""
        if sys.stdout is None:
            # Avviati con pythonw (GUI) non esiste una console: il registro
            # dell'interfaccia grafica riceve comunque l'evento via logging.
            log.info("%s%s - %s", change.headline, price, change.item.url)
            return
        print(f"\n[{stamp}] *** {change.headline}{price}")
        print(f"          {change.item.url}")
        for taglia in taglie_disponibili(change):
            print(f"          taglia {taglia['nome']}: {link_taglia(change, taglia)}")
        print("", flush=True)


class DesktopNotifier(Notifier):
    """Toast di Windows tramite winotify, con beep opzionale."""

    name = "desktop"

    async def send(self, change: Change) -> None:
        await asyncio.to_thread(self._show, change)

    def _show(self, change: Change) -> None:
        if self.config.get("sound", True) and sys.platform == "win32":
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception as exc:  # pragma: no cover - dipende dall'ambiente
                log.debug("Beep non riuscito: %s", exc)

        try:
            from winotify import Notification
        except ImportError:
            log.warning("winotify non installato: notifica desktop saltata.")
            return

        price = f" - {change.item.price}" if change.item.price else ""
        disponibili = taglie_disponibili(change)
        # Il toast ha poche righe: le taglie in fila, senza i link.
        misure = (
            "Taglie: " + ", ".join(t["nome"] for t in disponibili[:8]) + "\n"
            if disponibili
            else ""
        )
        toast = Notification(
            app_id="Restock Monitor",
            title=change.headline,
            msg=f"{misure}{change.item.url}{price}",
            duration="long",
        )
        # Windows accetta al massimo cinque pulsanti per notifica: le prime
        # quattro taglie piu' il prodotto intero.
        for taglia in disponibili[:4]:
            toast.add_actions(label=taglia["nome"], launch=link_taglia(change, taglia))
        toast.add_actions(label="Apri pagina", launch=change.item.url)
        toast.show()


class TelegramNotifier(Notifier):
    name = "telegram"

    @staticmethod
    def diagnose(status: int, description: str) -> str:
        """Traduce l'errore di Telegram in cosa c'e' da sistemare."""
        lowered = description.lower()
        if status == 401 or "unauthorized" in lowered:
            return "il token del bot non e' valido: ricontrollalo su @BotFather."
        if "chat not found" in lowered:
            return (
                "chat_id non trovato. Apri una conversazione con il tuo bot e scrivigli "
                "almeno un messaggio: finche' non lo fai, il bot non puo' scriverti."
            )
        if "bot was blocked" in lowered:
            return "hai bloccato il bot su Telegram: sbloccalo dalla conversazione."
        if "not enough rights" in lowered or "kicked" in lowered:
            return "il bot non ha il permesso di scrivere in quella chat o gruppo."
        return description or f"errore HTTP {status}"

    async def send(self, change: Change) -> None:
        token = str(self.config.get("bot_token") or "").strip()
        chat_id = str(self.config.get("chat_id") or "").strip()
        if not token or not chat_id:
            log.warning("Telegram non configurato: servono il token del bot e il chat ID.")
            return

        tastiera = tastiera_taglie(change)
        if tastiera:
            # Con i pulsanti il corpo resta pulito: gli indirizzi lunghi
            # starebbero solo in mezzo.
            prezzo = f"\n{change.item.price}" if change.item.price else ""
            disponibili = taglie_disponibili(change)
            totali = len(change.item.extra.get("taglie") or [])
            testo = (
                f"{change.headline}{prezzo}\n"
                f"\nTaglie disponibili: {len(disponibili)} su {totali}."
                f"\nPremi la taglia per aprire il prodotto gia' impostato su quella misura."
            )
        else:
            testo = _line(change)

        corpo = {
            "chat_id": chat_id,
            "text": testo,
            "disable_web_page_preview": True,
        }
        if tastiera:
            corpo["reply_markup"] = tastiera

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage", json=corpo
            )

        if response.status_code == 200:
            return

        description = ""
        try:
            description = str(response.json().get("description", ""))
        except ValueError:
            description = response.text[:200]
        log.warning("Telegram: %s", self.diagnose(response.status_code, description))


class DiscordNotifier(Notifier):
    name = "discord"

    async def send(self, change: Change) -> None:
        webhook = self.config.get("webhook_url")
        if not webhook:
            log.warning("Discord non configurato: manca webhook_url.")
            return

        fields = [{"name": "Link", "value": change.item.url, "inline": False}]
        if change.item.price:
            fields.append({"name": "Prezzo", "value": change.item.price, "inline": True})

        disponibili = taglie_disponibili(change)
        if disponibili:
            # Discord non ha pulsanti nei webhook: i link vanno nel testo, ma
            # in Markdown, cosi' si preme il nome della taglia e non un indirizzo.
            fields.append(
                {
                    "name": f"Taglie disponibili ({len(disponibili)})",
                    "value": " · ".join(
                        f"[{t['nome']}]({link_taglia(change, t)})" for t in disponibili[:MAX_TAGLIE]
                    ),
                    "inline": False,
                }
            )

        payload = {
            "embeds": [
                {
                    "title": change.item.title[:250],
                    "description": f"**{change.target}**",
                    "url": change.item.url,
                    "color": 0x2ECC71 if change.kind == "restock" else 0x3498DB,
                    "fields": fields,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ]
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook, json=payload)
            if response.status_code >= 400:
                log.warning("Discord ha risposto %s: %s", response.status_code, response.text[:200])


_REGISTRY: dict[str, type[Notifier]] = {
    "console": ConsoleNotifier,
    "desktop": DesktopNotifier,
    "telegram": TelegramNotifier,
    "discord": DiscordNotifier,
}


class Dispatcher:
    """Instrada ogni Change verso i soli canali abilitati e richiesti dal target."""

    def __init__(self, configs: dict[str, dict[str, Any]]) -> None:
        self.channels: dict[str, Notifier] = {}
        for name, cls in _REGISTRY.items():
            cfg = configs.get(name) or {}
            if cfg.get("enabled", name == "console"):
                self.channels[name] = cls(cfg)

    @property
    def enabled(self) -> list[str]:
        return sorted(self.channels)

    async def dispatch(self, change: Change, wanted: list[str]) -> None:
        targets = [self.channels[n] for n in wanted if n in self.channels]
        if not targets:
            log.debug("Nessun canale attivo per %s", change.target)
            return

        results = await asyncio.gather(
            *(n.send(change) for n in targets), return_exceptions=True
        )
        for notifier, result in zip(targets, results):
            if isinstance(result, Exception):
                log.warning("Notifica %s fallita: %s", notifier.name, result)
