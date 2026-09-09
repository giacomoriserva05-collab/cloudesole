r"""Completa il collegamento di Telegram: trova il chat ID e manda una prova.

Legge il token del bot da config.yaml, resta in ascolto finche' non gli scrivi
dall'app, salva il chat ID trovato e invia una notifica di prova.

Il chat ID non e' ricavabile in altro modo: e' l'API del bot a comunicarlo, e lo
fa solo dopo che gli hai scritto almeno una volta. Finche' non lo fai, Telegram
vieta al bot di scriverti per primo.

Uso:  .venv\Scripts\python.exe telegramsetup.py
      .venv\Scripts\python.exe telegramsetup.py --attesa 600
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

from restock import config
from restock.models import Change, Item
from restock.notify import TelegramNotifier

CONFIG = Path(__file__).resolve().parent / "config.yaml"


def leggi_token() -> str:
    tg = config.load_raw(CONFIG)["notifiers"].get("telegram") or {}
    token = str(tg.get("bot_token") or "").strip()
    if not token:
        print("In config.yaml manca il token del bot.", file=sys.stderr)
        print("Prendilo da @BotFather (/mybots -> il tuo bot -> API Token) e mettilo", file=sys.stderr)
        print("nella GUI: Impostazioni -> Telegram -> Token del bot.", file=sys.stderr)
        raise SystemExit(2)
    return token


async def verifica(client: httpx.AsyncClient, api: str) -> str:
    data = (await client.get(api + "/getMe")).json()
    if not data.get("ok"):
        descrizione = str(data.get("description", ""))
        print("Token rifiutato da Telegram: " + descrizione, file=sys.stderr)
        print("  -> " + TelegramNotifier.diagnose(401, descrizione), file=sys.stderr)
        raise SystemExit(1)
    return str(data["result"].get("username"))


async def attendi(client: httpx.AsyncClient, api: str, secondi: int) -> tuple[int, str] | None:
    """Long polling: una sola connessione aperta, nessun martellamento."""
    offset: int | None = None
    scadenza = time.monotonic() + secondi

    while time.monotonic() < scadenza:
        params: dict[str, int] = {"timeout": 50}
        if offset is not None:
            params["offset"] = offset
        try:
            data = (await client.get(api + "/getUpdates", params=params)).json()
        except httpx.HTTPError as exc:
            print("  errore di rete (" + type(exc).__name__ + "), riprovo...")
            await asyncio.sleep(3)
            continue

        for update in data.get("result") or []:
            offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat") or {}
            if chat.get("type") == "private" and chat.get("id") is not None:
                return int(chat["id"]), str(chat.get("first_name") or chat.get("username") or "?")
    return None


async def esegui(secondi: int) -> int:
    token = leggi_token()
    api = "https://api.telegram.org/bot" + token

    async with httpx.AsyncClient(timeout=70.0) as client:
        username = await verifica(client, api)
        print("Bot valido: @" + username)
        print()
        print("Ora apri Telegram, cerca @" + username + " e mandagli un messaggio qualsiasi.")
        print("Resto in ascolto per " + str(secondi) + " secondi... (Ctrl-C per interrompere)")

        trovato = await attendi(client, api, secondi)

    if trovato is None:
        print()
        print("Nessun messaggio ricevuto. Rilancia lo script quando sei pronto.")
        return 1

    chat_id, nome = trovato
    print()
    print("Chat trovata: " + nome + " (id " + str(chat_id) + ")")

    raw = config.load_raw(CONFIG)
    tg = raw["notifiers"].setdefault("telegram", {})
    tg["chat_id"] = str(chat_id)
    tg["enabled"] = True
    config.save_raw(CONFIG, raw)
    print("Salvato in config.yaml e canale attivato.")

    await TelegramNotifier({"bot_token": token, "chat_id": str(chat_id)}).send(
        Change(
            target="Restock Monitor",
            item=Item(
                key="test",
                title="Notifica di prova - il canale Telegram funziona",
                available=True,
                url="https://www.nike.com/it/launch/in-stock",
                price="99.00",
            ),
            kind="restock",
        )
    )
    print("Notifica di prova inviata: controlla Telegram.")
    print()
    print("Ultimo passo: nella GUI seleziona i target che vuoi ricevere sul telefono,")
    print("Modifica -> spunta 'Telegram' fra i canali di notifica.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collega Telegram al Restock Monitor.")
    parser.add_argument(
        "--attesa",
        type=int,
        default=300,
        help="Secondi di attesa del tuo messaggio al bot (predefinito 300).",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(esegui(max(10, args.attesa)))
    except KeyboardInterrupt:
        print("\nInterrotto.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
