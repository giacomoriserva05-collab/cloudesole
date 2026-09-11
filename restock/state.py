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

    @staticmethod
    def _calo_prezzo(previous: dict, item: Item) -> float | None:
        """Percentuale di calo rispetto al prezzo ricordato, None se non confrontabile."""
        prima = previous.get("prezzo_num")
        adesso = item.extra.get("prezzo_num")
        if not prima or adesso is None or adesso >= prima:
            return None
        return (1 - adesso / prima) * 100

    def known(self, target_name: str, key: str) -> dict | None:
        """Ultimo stato salvato per un articolo, o None se mai visto."""
        return self._data.get(f"{target_name}::{key}")

    def diff(
        self,
        target_name: str,
        items: list[Item],
        soglia_sconto: float | None = None,
    ) -> list[Change]:
        """Confronta gli item appena letti con lo stato salvato e restituisce le novita'.

        Con 'soglia_sconto' (in percento) segnala anche i cali di prezzo: un
        articolo che era a 100 e ora e' a 90 produce uno 'sconto' se la soglia e'
        al massimo del 10%. Senza soglia il prezzo viene solo ricordato.
        """
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
                elif soglia_sconto is not None and item.available:
                    calo = self._calo_prezzo(previous, item)
                    if calo is not None and calo >= soglia_sconto:
                        # Il prezzo di prima serve alla notifica: "era 649, ora 619".
                        item.extra["prezzo_precedente"] = previous.get("prezzo_num")
                        item.extra["calo_pct"] = round(calo, 1)
                        changes.append(Change(target_name, item, "sconto"))

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
            if item.extra.get("prezzo_num") is not None:
                salvato["prezzo_num"] = item.extra["prezzo_num"]
            elif previous and previous.get("prezzo_num") is not None and not item.available:
                # Un prodotto esaurito spesso perde il prezzo in pagina: si
                # conserva l'ultimo noto, altrimenti al ritorno non ci sarebbe
                # niente con cui confrontarlo.
                salvato["prezzo_num"] = previous["prezzo_num"]
            self._data[key] = salvato

        self._seeded.add(target_name)
        return changes
