"""Strutture dati condivise fra adapter, stato e notificatori."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Item:
    """Un singolo articolo osservabile (di norma una variante/taglia)."""

    key: str
    """Identificatore stabile dell'articolo dentro al target (es. id variante)."""

    title: str
    """Nome leggibile, mostrato nelle notifiche."""

    available: bool
    url: str
    price: str | None = None

    verified: bool = True
    """Vero se la disponibilita' e' stata davvero accertata.

    Gli elenchi di link sanno solo che una voce c'e': senza aprire la pagina del
    prodotto non possono dire se sia acquistabile. In quel caso 'available' vale
    'presente in elenco' e non va spacciata per disponibilita'.
    """

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Change:
    """Transizione rilevata fra due poll consecutivi."""

    target: str
    item: Item
    kind: str
    """'restock' (esaurito -> disponibile) oppure 'new' (articolo mai visto, disponibile)."""

    @property
    def headline(self) -> str:
        if self.kind == "restock":
            # Un restock e' per definizione tornato disponibile: dirlo sarebbe ridondante.
            return f"[RESTOCK] {self.target} - {self.item.title}"

        if self.kind == "sconto":
            calo = self.item.extra.get("calo_pct")
            quanto = f" (-{calo:g}%)" if calo else ""
            return f"[SCONTO{quanto}] {self.target} - {self.item.title}"

        stato = ""
        if self.item.verified:
            stato = " [DISPONIBILE]" if self.item.available else " [ESAURITO]"
        return f"[NUOVO] {self.target} - {self.item.title}{stato}"
