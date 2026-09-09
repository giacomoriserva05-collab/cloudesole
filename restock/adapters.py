"""Adapter: trasformano la risposta di un endpoint pubblico in una lista di Item."""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .config import Target
from .models import Item


class AdapterError(RuntimeError):
    """La risposta non ha la forma attesa per questo tipo di target."""


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _strip(url: str) -> str:
    """Rimuove query e fragment, mantenendo schema/host/path."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _dig(data: Any, path: str) -> Any:
    """Naviga una struttura JSON con un percorso puntato, es. a.b.0.c"""
    current = data
    if not path:
        return current
    for segment in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
        if current is None:
            return None
    return current


def _money(value: Any, *, cents: bool = False) -> str | None:
    if value is None:
        return None
    try:
        amount = float(value) / 100 if cents else float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{amount:.2f}"


def _keep(title: str, target: Target) -> bool:
    """Applica il filtro match.variants: sottostringhe, case-insensitive."""
    wanted = target.match.get("variants")
    if not wanted:
        return True
    lowered = title.lower()
    return any(str(w).lower() in lowered for w in wanted)


# --------------------------------------------------------------------------- #
# Shopify
# --------------------------------------------------------------------------- #

def shopify_product_url(url: str) -> str:
    """Normalizza un URL prodotto Shopify sull'endpoint AJAX pubblico .js"""
    base = _strip(url)
    for suffix in (".js", ".json"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}.js"


def parse_shopify_product(target: Target, response: httpx.Response) -> list[Item]:
    data = response.json()
    variants = data.get("variants")
    if not isinstance(variants, list):
        raise AdapterError("Risposta Shopify priva della lista variants.")

    product_title = str(data.get("title") or target.name)
    handle = data.get("handle") or ""
    page_url = f"{_origin(target.url)}/products/{handle}" if handle else _strip(target.url)

    items: list[Item] = []
    for variant in variants:
        variant_title = str(variant.get("public_title") or variant.get("title") or "default")
        if not _keep(variant_title, target):
            continue
        variant_id = variant.get("id")
        items.append(
            Item(
                key=str(variant_id),
                title=f"{product_title} - {variant_title}",
                available=bool(variant.get("available")),
                url=f"{page_url}?variant={variant_id}" if variant_id else page_url,
                price=_money(variant.get("price"), cents=True),
            )
        )
    return items


def shopify_collection_url(url: str) -> str:
    base = _strip(url)
    if not base.endswith("products.json"):
        base = f"{base}/products.json"
    return f"{base}?limit=250"


def parse_shopify_collection(target: Target, response: httpx.Response) -> list[Item]:
    data = response.json()
    products = data.get("products")
    if not isinstance(products, list):
        raise AdapterError("Risposta Shopify priva della lista products.")

    origin = _origin(target.url)
    keyword = str(target.match.get("keyword") or "").lower()

    items: list[Item] = []
    for product in products:
        product_title = str(product.get("title") or "")
        if keyword and keyword not in product_title.lower():
            continue
        handle = product.get("handle") or ""
        page_url = f"{origin}/products/{handle}"

        for variant in product.get("variants") or []:
            variant_title = str(variant.get("title") or "default")
            if not _keep(f"{product_title} {variant_title}", target):
                continue
            variant_id = variant.get("id")
            items.append(
                Item(
                    key=str(variant_id),
                    title=f"{product_title} - {variant_title}",
                    available=bool(variant.get("available")),
                    url=f"{page_url}?variant={variant_id}" if variant_id else page_url,
                    price=_money(variant.get("price")),
                )
            )
    return items


# --------------------------------------------------------------------------- #
# JSON generico
# --------------------------------------------------------------------------- #

def parse_json(target: Target, response: httpx.Response) -> list[Item]:
    opts = target.options
    data = response.json()

    items_path = opts.get("items_path", "")
    raw_items = _dig(data, items_path) if items_path else data
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        raise AdapterError(
            f"items_path ({items_path!r}) non punta a una lista nella risposta JSON."
        )

    available_path = opts.get("available_path")
    if not available_path:
        raise AdapterError("Per type=json serve options.available_path")

    truthy = opts.get("available_when")
    key_path = opts.get("key_path", "id")
    title_path = opts.get("title_path", "title")
    price_path = opts.get("price_path")
    url_path = opts.get("url_path")

    items: list[Item] = []
    for index, raw in enumerate(raw_items):
        title = str(_dig(raw, title_path) or f"item-{index}")
        if not _keep(title, target):
            continue

        raw_available = _dig(raw, available_path)
        if truthy is None:
            available = bool(raw_available)
        else:
            expected = truthy if isinstance(truthy, list) else [truthy]
            available = str(raw_available).lower() in {str(e).lower() for e in expected}

        item_url = str(_dig(raw, url_path) or target.url) if url_path else target.url
        items.append(
            Item(
                key=str(_dig(raw, key_path) or index),
                title=title,
                available=available,
                url=item_url,
                price=_money(_dig(raw, price_path)) if price_path else None,
            )
        )
    return items


# --------------------------------------------------------------------------- #
# HTML per marcatori testuali
# --------------------------------------------------------------------------- #

_TITOLI = (
    # L'h1 di solito contiene il nome del prodotto e nient'altro: e' la fonte
    # migliore. og:title e <title> spesso si portano dietro il nome del sito.
    r"<h1[^>]*>(.*?)</h1>",
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title',
    r"<title[^>]*>(.*?)</title>",
)

# Code che i siti aggiungono al titolo della pagina e che non fanno parte del nome.
_CODE_INUTILI = re.compile(
    r"\s*[-|–—]\s*(shop|store|negozio|official site|sito ufficiale)\s*$", re.IGNORECASE
)


def _etichetta_sito(url: str) -> str:
    """'eu.supreme.com' -> 'supreme'. Serve il nome del dominio, non il primo pezzo."""
    if not url:
        return ""
    pezzi = [p for p in urlsplit(url).netloc.split(":")[0].split(".") if p]
    if len(pezzi) >= 2:
        return pezzi[-2]
    return pezzi[0] if pezzi else ""


def estrai_nome(corpo: str, url: str = "") -> str | None:
    """Nome leggibile del prodotto, preso dalla sua pagina.

    Serve sui siti dove l'indirizzo non dice niente: su Supreme un prodotto sta
    su /products/gh-ii_gyou4-fsju, e da quello non si ricava un nome. La pagina
    pero' si apre gia' per accertare la disponibilita', quindi il nome vero
    costa zero richieste in piu'.
    """
    for schema in _TITOLI:
        trovato = re.search(schema, corpo, re.IGNORECASE | re.DOTALL)
        if not trovato:
            continue

        nome = re.sub(r"<[^>]+>", " ", trovato.group(1))
        nome = html.unescape(nome)
        nome = re.sub(r"\s+", " ", nome).strip()

        # Toglie in coda il nome del sito e le diciture di servizio, una alla
        # volta: "Prodotto - Shop - Supreme" deve tornare "Prodotto".
        etichetta = _etichetta_sito(url)
        for _ in range(3):
            precedente = nome
            nome = _CODE_INUTILI.sub("", nome)
            if etichetta:
                nome = re.sub(
                    rf"\s*[-|–—]\s*{re.escape(etichetta)}\s*$", "", nome, flags=re.IGNORECASE
                )
            if nome == precedente:
                break

        if 2 <= len(nome) <= 120:
            return nome
    return None


# Nomi di campo che contengono davvero una taglia, dal piu' specifico al piu'
# generico. 'title' viene per ultimo perche' su molte pagine e' il nome del
# prodotto, non della variante.
_CAMPI_TAGLIA = r"public_title|variant|option1|size|localizedSize"

_SCHEMI_TAGLIE = (
    # Con l'id accanto: permette di costruire il link diretto alla taglia.
    rf'"id"\s*:\s*(\d{{6,20}})[^{{}}]{{0,300}}?"(?:{_CAMPI_TAGLIA})"\s*:\s*"([^"]{{1,24}})"'
    rf'[^{{}}]{{0,300}}?"available"\s*:\s*(true|false)',
    rf'"(?:{_CAMPI_TAGLIA})"\s*:\s*"([^"]{{1,24}})"[^{{}}]{{0,400}}?"available"\s*:\s*(true|false)',
    r'"id"\s*:\s*(\d{6,20})[^{}]{0,300}?"title"\s*:\s*"([^"]{1,24})"'
    r'[^{}]{0,300}?"available"\s*:\s*(true|false)',
    r'"title"\s*:\s*"([^"]{1,24})"[^{}]{0,400}?"available"\s*:\s*(true|false)',
)


def _normalizza_taglia(nome: str) -> str:
    """'2xl' -> '2XL'. Alcuni store espongono le sigle in minuscolo."""
    nome = nome.strip()
    if len(nome) <= 4 and nome.islower():
        return nome.upper()
    return nome


def _array_bilanciati(corpo: str, chiave: str):
    """Tutti gli array JSON incorporati sotto una certa chiave, contando le parentesi.

    Cercare per adiacenza con una regex non funziona: fra il nome della taglia e
    la sua disponibilita' i siti infilano oggetti annidati, e qualunque limite
    di distanza si scelga sbaglia su meta' delle pagine.

    Vengono restituiti tutti e non solo il primo, perche' una stessa pagina puo'
    contenere piu' elenchi con lo stesso nome: su alcuni store il primo e' quello
    delle statistiche, che i campi di disponibilita' non li ha affatto.
    """
    for candidato in (f'"{chiave}"', f'\\"{chiave}\\"'):
        inizio = corpo.find(candidato)
        while inizio != -1:
            apertura = corpo.find("[", inizio + len(candidato))
            if apertura != -1 and apertura - inizio <= 40:
                profondita = 0
                dentro_stringa = False
                fuga = False
                for posizione in range(apertura, min(len(corpo), apertura + 400_000)):
                    carattere = corpo[posizione]
                    if fuga:
                        fuga = False
                        continue
                    if carattere == "\\":
                        fuga = True
                        continue
                    if carattere == '"':
                        dentro_stringa = not dentro_stringa
                        continue
                    if dentro_stringa:
                        continue
                    if carattere == "[":
                        profondita += 1
                    elif carattere == "]":
                        profondita -= 1
                        if profondita == 0:
                            yield corpo[apertura : posizione + 1]
                            break
            inizio = corpo.find(candidato, inizio + 1)


def _taglie_da_elenco(testo: str) -> list[dict[str, Any]]:
    for tentativo in (testo, testo.replace('\\"', '"').replace("\\\\", "\\")):
        try:
            varianti = json.loads(tentativo)
        except ValueError:
            continue
        if not isinstance(varianti, list):
            continue

        trovate: dict[str, dict[str, Any]] = {}
        for variante in varianti:
            if not isinstance(variante, dict):
                continue
            # Senza campo di disponibilita' l'elenco non serve: e' il caso degli
            # array usati per le statistiche, che elencano le taglie e basta.
            if "available" not in variante and "availableForSale" not in variante:
                continue
            nome = variante.get("public_title") or variante.get("title") or variante.get("option1")
            if not nome:
                continue
            nome = _normalizza_taglia(str(nome))
            identificativo = variante.get("id")
            trovate.setdefault(
                nome,
                {
                    "nome": nome,
                    "disponibile": bool(
                        variante.get("available", variante.get("availableForSale"))
                    ),
                    "id": str(identificativo) if identificativo else None,
                },
            )
        if trovate:
            return list(trovate.values())[:40]
    return []


def _taglie_da_json(corpo: str) -> list[dict[str, Any]]:
    for chiave in ("variants", "productVariants"):
        for testo in _array_bilanciati(corpo, chiave):
            taglie = _taglie_da_elenco(testo)
            if len(taglie) >= 2:
                return taglie
    return []


def estrai_taglie(corpo: str) -> list[dict[str, Any]]:
    """Taglie della scheda prodotto, con la disponibilita' di ciascuna.

    La pagina si apre gia' per accertare lo stock: sapere *quali* taglie ci sono
    costa zero richieste in piu' ed e' l'informazione che serve davvero per
    decidere se andare a comprare.

    Si prova prima a leggere l'elenco delle varianti come JSON, che e' esatto;
    le espressioni regolari restano come ripiego per le pagine dove quell'elenco
    non c'e' o non e' interpretabile.
    """
    dal_json = _taglie_da_json(corpo)
    if len(dal_json) >= 2:
        return dal_json

    for schema in _SCHEMI_TAGLIE:
        trovate: dict[str, dict[str, Any]] = {}
        for gruppi in re.findall(schema, corpo):
            if len(gruppi) == 3:
                identificativo, nome, stato = gruppi
            else:
                identificativo, (nome, stato) = "", gruppi

            nome = html.unescape(nome).strip()
            if not nome:
                continue
            # La prima occorrenza vince: le pagine ripetono spesso i blocchi.
            trovate.setdefault(
                nome,
                {"nome": nome, "disponibile": stato == "true", "id": identificativo or None},
            )

        if len(trovate) >= 2:
            return list(trovate.values())[:40]
    return []


def evaluate_markers(
    body: str,
    in_stock: list[Any],
    out_of_stock: list[Any],
    use_regex: bool = False,
) -> bool:
    """Decide se una pagina descrive un articolo disponibile.

    L'esaurito ha la precedenza: se la pagina dichiara esplicitamente che il
    prodotto non c'e', quello vince su qualsiasi indizio contrario (il pulsante
    "aggiungi al carrello" resta spesso nel markup anche da esaurito).
    """
    lowered = body.lower()

    def hit(patterns: list[Any]) -> bool:
        for pattern in patterns:
            text = str(pattern)
            if use_regex:
                if re.search(text, body, re.IGNORECASE | re.DOTALL):
                    return True
            elif text.lower() in lowered:
                return True
        return False

    if out_of_stock and hit(out_of_stock):
        return False
    if in_stock:
        return hit(in_stock)
    # Solo marcatori di esaurito configurati e nessuno trovato: si assume disponibile.
    return True


def parse_html(target: Target, response: httpx.Response) -> list[Item]:
    opts = target.options
    in_stock = opts.get("in_stock_when") or []
    out_of_stock = opts.get("out_of_stock_when") or []
    if not in_stock and not out_of_stock:
        raise AdapterError(
            "Per type=html serve almeno options.in_stock_when o options.out_of_stock_when"
        )

    available = evaluate_markers(
        response.text, in_stock, out_of_stock, bool(opts.get("regex", False))
    )

    return [
        Item(
            key="page",
            title=target.name,
            available=available,
            url=target.url,
        )
    ]


# --------------------------------------------------------------------------- #
# Elenchi di link
# --------------------------------------------------------------------------- #

def parse_links(target: Target, response: httpx.Response) -> list[Item]:
    """Estrae un elenco di voci da una pagina o da una sitemap.

    Ogni voce trovata e' considerata disponibile: il segnale utile non e' la
    transizione esaurito -> disponibile, ma la comparsa di una voce che prima
    non c'era. Serve per i siti dove la disponibilita' non e' leggibile ma
    l'elenco dei prodotti si', come le pagine dei lanci o una sitemap.
    """
    opts = target.options
    pattern = opts.get("pattern")
    if not pattern:
        raise AdapterError("Per type=links serve options.pattern")

    try:
        regex = re.compile(str(pattern))
    except re.error as exc:
        raise AdapterError(f"pattern non valido: {exc}") from None

    # Regex facoltativa applicata alla voce trovata: il gruppo 1 diventa il
    # titolo mostrato nelle notifiche. Serve quando la voce contiene anche
    # codici interni che non hanno senso da leggere.
    title_from = opts.get("title_from")
    title_regex = None
    if title_from:
        try:
            title_regex = re.compile(str(title_from))
        except re.error as exc:
            raise AdapterError(f"title_from non valido: {exc}") from None

    base = str(opts.get("base") or "")
    include = [str(v).lower() for v in (opts.get("include") or [])]
    exclude = [str(v).lower() for v in (opts.get("exclude") or [])]
    try:
        limit = max(1, int(opts.get("limit", 5000)))
    except (TypeError, ValueError):
        limit = 5000

    found: dict[str, None] = {}
    for match in regex.finditer(response.text):
        value = (match.group(1) if regex.groups else match.group(0)).strip()
        if not value:
            continue
        lowered = value.lower()
        if include and not any(word in lowered for word in include):
            continue
        if exclude and any(word in lowered for word in exclude):
            continue
        found.setdefault(value, None)
        if len(found) >= limit:
            break

    items: list[Item] = []
    for value in found:
        url = value if value.startswith(("http://", "https://")) else base + value

        raw_title = ""
        if title_regex is not None:
            match = title_regex.search(value)
            if match:
                raw_title = match.group(1) if match.groups() else match.group(0)
        if not raw_title:
            raw_title = value.rstrip("/").rsplit("/", 1)[-1]

        title = raw_title.replace("-", " ").replace("_", " ").strip() or value
        if not _keep(title, target):
            continue
        # available=True significa "presente in elenco", non "acquistabile":
        # verified=False lo dichiara. Se il target ha un blocco 'detail', il
        # monitor aprira' la pagina e sostituira' questo valore con quello vero.
        items.append(Item(key=value, title=title, available=True, url=url, verified=False))
    return items


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

_URL_BUILDERS = {
    "shopify_product": shopify_product_url,
    "shopify_collection": shopify_collection_url,
}

_PARSERS = {
    "shopify_product": parse_shopify_product,
    "shopify_collection": parse_shopify_collection,
    "json": parse_json,
    "html": parse_html,
    "links": parse_links,
}


def request_url(target: Target) -> str:
    """URL effettivamente interrogato: puo' differire da quello leggibile in config."""
    builder = _URL_BUILDERS.get(target.type)
    return builder(target.url) if builder else target.url


def request_urls(target: Target) -> list[str]:
    """Tutte le pagine da interrogare per coprire l'intero catalogo.

    Un negozio con piu' prodotti di quanti ne stiano in una risposta va sfogliato:
    senza questo, monitorare "tutto il sito" significherebbe monitorarne la prima
    pagina e credere che sia tutto.
    """
    base = request_url(target)
    try:
        pages = max(1, int(target.options.get("pages", 1) or 1))
    except (TypeError, ValueError):
        pages = 1
    if pages == 1:
        return [base]

    param = str(target.options.get("page_param") or "page")
    separator = "&" if "?" in base else "?"
    return [base] + [f"{base}{separator}{param}={n}" for n in range(2, pages + 1)]


def parse(target: Target, response: httpx.Response) -> list[Item]:
    parser = _PARSERS.get(target.type)
    if parser is None:
        raise AdapterError(f"Tipo di target non gestito: {target.type}")
    return parser(target, response)
