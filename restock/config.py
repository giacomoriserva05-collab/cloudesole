"""Caricamento e validazione della configurazione YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Limite non configurabile: nessun target viene interrogato piu' spesso di cosi'.
# Serve a impedire che il monitor si trasformi in un generatore di carico sul sito.
MIN_INTERVAL_SECONDS = 3.0

DEFAULT_USER_AGENT = (
    "RestockMonitor/1.0 (monitor personale di disponibilita'; "
    "contatto: imposta 'user_agent' in config.yaml)"
)

VALID_TYPES = {"shopify_product", "shopify_collection", "json", "html", "links"}


class ConfigError(ValueError):
    """Configurazione assente, malformata o incoerente."""


@dataclass
class Target:
    name: str
    type: str
    url: str
    interval: float
    jitter: float
    timeout: float
    notify: list[str]
    match: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    """Se falso il target resta in configurazione ma non viene interrogato."""

    detail: dict[str, Any] = field(default_factory=dict)
    """Solo per type=links: apre la pagina di ogni voce per accertarne lo stock.

    Senza questo blocco un elenco sa solo che una voce e' comparsa. Con questo,
    il monitor apre la pagina del prodotto e distingue disponibile da esaurito.
    """

    @property
    def checks_detail(self) -> bool:
        return bool(self.detail) and self.type == "links"


@dataclass
class Settings:
    user_agent: str
    respect_robots: bool
    state_file: Path
    targets: list[Target]
    notifiers: dict[str, dict[str, Any]]


def _as_float(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"'{name}' deve essere un numero, trovato: {value!r}") from None


HEADER = """\
# Restock Monitor - configurazione.
# Questo file e' gestito anche dall'interfaccia grafica: se lo modifichi a mano
# i commenti che aggiungi verranno persi al primo salvataggio dalla GUI.
"""


def load_raw(path: str | Path) -> dict[str, Any]:
    """Legge il YAML cosi' com'e', senza validare. Usato dall'editor grafico."""
    path = Path(path)
    if not path.is_file():
        return {"defaults": {}, "notifiers": {}, "targets": []}

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Il file di configurazione deve contenere una mappa YAML.")

    raw.setdefault("defaults", {})
    raw.setdefault("notifiers", {})
    raw.setdefault("targets", [])
    return raw


def save_raw(path: str | Path, data: dict[str, Any]) -> None:
    """Riscrive il YAML in modo atomico, preceduto da un'intestazione."""
    path = Path(path)
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(HEADER + body, encoding="utf-8")
    tmp.replace(path)


def load(path: str | Path) -> Settings:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"File di configurazione non trovato: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Il file di configurazione deve contenere una mappa YAML.")

    defaults = raw.get("defaults") or {}
    notifiers = raw.get("notifiers") or {}

    user_agent = str(defaults.get("user_agent") or DEFAULT_USER_AGENT)
    respect_robots = bool(defaults.get("respect_robots", True))
    default_interval = _as_float(defaults.get("interval", 20), "defaults.interval")
    default_jitter = _as_float(defaults.get("jitter", 0.3), "defaults.jitter")
    default_timeout = _as_float(defaults.get("timeout", 15), "defaults.timeout")
    default_notify = defaults.get("notify") or ["console", "desktop"]

    state_file = Path(raw.get("state_file") or path.parent / "state.json")

    raw_targets = raw.get("targets")
    if not raw_targets:
        raise ConfigError("Nessun target definito: la chiave 'targets' e' vuota.")

    targets: list[Target] = []
    seen_names: set[str] = set()

    for index, entry in enumerate(raw_targets, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"targets[{index}] deve essere una mappa.")

        name = str(entry.get("name") or f"target-{index}")
        if name in seen_names:
            raise ConfigError(f"Nome target duplicato: {name!r}. I nomi devono essere univoci.")
        seen_names.add(name)

        ttype = str(entry.get("type") or "").strip()
        if ttype not in VALID_TYPES:
            raise ConfigError(
                f"{name}: 'type' non valido ({ttype!r}). "
                f"Valori ammessi: {', '.join(sorted(VALID_TYPES))}."
            )

        url = str(entry.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"{name}: 'url' deve essere un URL http/https assoluto.")

        interval = _as_float(entry.get("interval", default_interval), f"{name}.interval")
        if interval < MIN_INTERVAL_SECONDS:
            raise ConfigError(
                f"{name}: interval={interval}s sotto il minimo consentito "
                f"di {MIN_INTERVAL_SECONDS}s."
            )

        notify = entry.get("notify", default_notify)
        if isinstance(notify, str):
            notify = [notify]

        detail = entry.get("detail") or {}
        if detail:
            if not isinstance(detail, dict):
                raise ConfigError(f"{name}: 'detail' deve essere una mappa.")
            if ttype != "links":
                raise ConfigError(
                    f"{name}: 'detail' vale solo per type=links "
                    f"(gli altri tipi leggono gia' la disponibilita' da soli)."
                )
            if not (detail.get("in_stock_when") or detail.get("out_of_stock_when")):
                raise ConfigError(
                    f"{name}: in 'detail' serve almeno in_stock_when o out_of_stock_when, "
                    f"altrimenti non c'e' modo di riconoscere l'esaurito."
                )
            max_checks = detail.get("max_checks", 5)
            try:
                if int(max_checks) < 1:
                    raise ValueError
            except (TypeError, ValueError):
                raise ConfigError(
                    f"{name}: 'detail.max_checks' deve essere un intero maggiore di zero."
                ) from None

        targets.append(
            Target(
                name=name,
                type=ttype,
                url=url,
                interval=interval,
                jitter=_as_float(entry.get("jitter", default_jitter), f"{name}.jitter"),
                timeout=_as_float(entry.get("timeout", default_timeout), f"{name}.timeout"),
                notify=[str(n) for n in notify],
                match=entry.get("match") or {},
                options=entry.get("options") or {},
                enabled=bool(entry.get("enabled", True)),
                detail=detail,
            )
        )

    return Settings(
        user_agent=user_agent,
        respect_robots=respect_robots,
        state_file=state_file,
        targets=targets,
        notifiers=notifiers,
    )
