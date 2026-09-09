"""Interfaccia a riga di comando."""

from __future__ import annotations

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load
from .models import Change, Item
from .monitor import Monitor
from .notify import Dispatcher

log = logging.getLogger(__name__)


def _stampa(testo: str, errore: bool = False) -> None:
    """print sicuro: avviati con pythonw gli stream non esistono affatto."""
    flusso = sys.stderr if errore else sys.stdout
    if flusso is None:
        (log.error if errore else log.info)(testo)
        return
    print(testo, file=flusso)


def _setup_logging(verbose: bool, config_path: str = "config.yaml") -> None:
    if sys.platform == "win32":
        # Evita UnicodeEncodeError sulla console legacy di Windows.
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure:
                reconfigure(encoding="utf-8", errors="replace")

    formato = logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(message)s", datefmt="%d/%m %H:%M:%S"
    )
    radice = logging.getLogger()
    radice.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Avviato con pythonw (avvio automatico) non esiste nessuno stream: senza il
    # file non resterebbe traccia di niente.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formato)
        radice.addHandler(console)

    try:
        # Accanto alla configurazione usata, non alla cartella del programma:
        # altrimenti le prove con una config temporanea scriverebbero nel
        # registro di quella vera, mescolando righe finte a quelle reali.
        percorso = Path(config_path).resolve().parent / "monitor.log"
        # Rotazione: due file da 1 MB bastano per giorni e non crescono mai oltre.
        su_file = RotatingFileHandler(
            percorso, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
        su_file.setFormatter(formato)
        radice.addHandler(su_file)
    except OSError as exc:
        if sys.stderr is not None:
            print(f"Registro su file non disponibile: {exc}", file=sys.stderr)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="restock",
        description=(
            "Monitor di disponibilita' su endpoint pubblici. "
            "Notifica i restock; l'acquisto resta manuale."
        ),
    )
    parser.add_argument(
        "-c", "--config", default="config.yaml", help="File YAML di configurazione."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Esegue un solo giro su ogni target e termina (verifica della config).",
    )
    parser.add_argument(
        "--test-notify",
        action="store_true",
        help="Invia una notifica di prova su tutti i canali abilitati.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Cancella lo stato salvato prima di partire.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log di debug.")
    parser.add_argument("--version", action="version", version=f"restock {__version__}")
    return parser


async def _test_notify(settings) -> int:
    dispatcher = Dispatcher(settings.notifiers)
    if not dispatcher.enabled:
        _stampa("Nessun canale di notifica abilitato in config.yaml.")
        return 1

    _stampa(f"Invio di prova su: {', '.join(dispatcher.enabled)}")
    change = Change(
        target="Test",
        item=Item(
            key="test",
            title="Notifica di prova",
            available=True,
            url="https://example.com",
            price="99.00",
        ),
        kind="restock",
    )
    await dispatcher.dispatch(change, dispatcher.enabled)
    _stampa("Fatto. Se non hai visto nulla, controlla le credenziali dei canali.")
    return 0


async def _amain(args: argparse.Namespace) -> int:
    try:
        settings = load(args.config)
    except ConfigError as exc:
        _stampa(f"Configurazione non valida: {exc}", errore=True)
        return 2

    if args.test_notify:
        return await _test_notify(settings)

    if args.reset_state and Path(settings.state_file).exists():
        Path(settings.state_file).unlink()
        _stampa(f"Stato azzerato: {settings.state_file}")

    monitor = Monitor(settings)
    try:
        if args.once:
            _stampa(f"Verifica di {len(settings.targets)} target...")
            return await monitor.run_once()
        await monitor.run()
    except KeyboardInterrupt:
        pass
    finally:
        await monitor.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _setup_logging(args.verbose, args.config)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        _stampa("Interrotto.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
