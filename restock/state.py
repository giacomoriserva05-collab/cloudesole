"""Stato persistente: ricorda la disponibilita' vista per non riavvisare due volte."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from .models import Change, Item

log = logging.getLogger(__name__)


class State:
    """Mappa (target, item.key) -> ultima disponibilita' osservata.

    Il primo poll di un target e' silenzioso: serve solo a fotografare la
    situazione di partenza, altrimenti all'avvio arriverebbe una notifica per
    ogni articolo gia' disponibile.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        self._seeded: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Stato illeggibile (%s): riparto da zero.", exc)
            return
        self._data = raw.get("items") or {}
        self._seeded = set(raw.get("seeded") or [])

    def save(self) -> None:
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "seeded": sorted(self._seeded),
            "items": self._data,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Scrittura atomica: un Ctrl-C a meta' salvataggio non corrompe lo stato.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def is_seeded(self, target_name: str) -> bool:
        return target_name in self._seeded

    def known(self, target_name: str, key: str) -> dict | None:
        """Ultimo stato salvato per un articolo, o None se mai visto."""
        return self._data.get(f"{target_name}::{key}")

    def diff(self, target_name: str, items: list[Item]) -> list[Change]:
        """Confronta gli item appena letti con lo stato salvato e restituisce le novita'."""
        first_run = not self.is_seeded(target_name)
        changes: list[Change] = []

        for item in items:
            key = f"{target_name}::{item.key}"
            previous = self._data.get(key)

            if not first_run:
                if previous is None:
                    # Un articolo mai visto merita un avviso anche se e' gia'
                    # esaurito, purche' lo stock sia stato accertato: sapere che
                    # e' uscito qualcosa conta, e l'avviso dira' che e' esaurito.
                    if item.available or item.verified:
                        changes.append(Change(target_name, item, "new"))
                elif item.available and not previous.get("available"):
                    changes.append(Change(target_name, item, "restock"))

            salvato = {
                "available": item.available,
                "verified": item.verified,
                "title": item.title,
                "price": item.price,
                "url": item.url,
                "seen_at": time.time(),
            }
            # Il nome letto dalla pagina del prodotto va conservato: si ricava
            # solo aprendo quella pagina, e non la si riapre a ogni giro.
            if item.extra.get("nome_pagina"):
                salvato["nome_pagina"] = item.extra["nome_pagina"]
            if item.extra.get("taglie"):
                salvato["taglie"] = item.extra["taglie"]
            self._data[key] = salvato

        self._seeded.add(target_name)
        return changes
