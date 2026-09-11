"""Test di autoverifica, senza rete e senza dipendenze extra.

Uso:  .venv\\Scripts\\python.exe selftest.py
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

import httpx

from restock import adapters, config
from restock.config import Target
from restock.models import Change, Item
from restock.state import State

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def test(name):
    def wrap(fn):
        try:
            fn()
        except Exception:
            FAILED.append((name, traceback.format_exc()))
        else:
            PASSED.append(name)
        return fn

    return wrap


def make_target(**kw) -> Target:
    base = dict(
        name="T",
        type="shopify_product",
        url="https://shop.example.com/products/x",
        interval=20.0,
        jitter=0.3,
        timeout=15.0,
        notify=["console"],
        match={},
        options={},
    )
    base.update(kw)
    return Target(**base)


# --------------------------------------------------------------------------- #
# URL
# --------------------------------------------------------------------------- #

@test("normalizzazione URL prodotto Shopify")
def _() -> None:
    build = adapters.shopify_product_url
    expected = "https://s.com/products/x.js"
    assert build("https://s.com/products/x") == expected
    assert build("https://s.com/products/x/") == expected
    assert build("https://s.com/products/x.js") == expected
    assert build("https://s.com/products/x.json") == expected
    assert build("https://s.com/products/x?variant=99") == expected


@test("normalizzazione URL collezione Shopify")
def _() -> None:
    build = adapters.shopify_collection_url
    assert build("https://s.com/collections/all") == "https://s.com/collections/all/products.json?limit=250"
    assert build("https://s.com/collections/all/products.json") == "https://s.com/collections/all/products.json?limit=250"


# --------------------------------------------------------------------------- #
# Adapter Shopify
# --------------------------------------------------------------------------- #

SHOPIFY_PRODUCT = {
    "title": "Sneaker X",
    "handle": "sneaker-x",
    "variants": [
        {"id": 1, "public_title": "42", "available": False, "price": 12900},
        {"id": 2, "public_title": "43", "available": True, "price": 12900},
        {"id": 3, "public_title": "44", "available": True, "price": 12900},
    ],
}


@test("adapter shopify_product legge varianti e prezzo in centesimi")
def _() -> None:
    items = adapters.parse_shopify_product(
        make_target(), httpx.Response(200, json=SHOPIFY_PRODUCT)
    )
    assert len(items) == 3, len(items)
    assert items[0].title == "Sneaker X - 42"
    assert items[0].available is False
    assert items[1].available is True
    assert items[0].price == "129.00", items[0].price
    assert items[1].url.endswith("/products/sneaker-x?variant=2"), items[1].url


@test("adapter shopify_product applica il filtro sulle taglie")
def _() -> None:
    items = adapters.parse_shopify_product(
        make_target(match={"variants": ["43"]}),
        httpx.Response(200, json=SHOPIFY_PRODUCT),
    )
    assert [i.title for i in items] == ["Sneaker X - 43"]


@test("adapter shopify_product segnala una risposta senza varianti")
def _() -> None:
    try:
        adapters.parse_shopify_product(make_target(), httpx.Response(200, json={"title": "X"}))
    except adapters.AdapterError:
        return
    raise AssertionError("attesa AdapterError")


@test("adapter shopify_collection espande prodotti e varianti")
def _() -> None:
    payload = {
        "products": [
            {
                "title": "Air Jordan 1",
                "handle": "aj1",
                "variants": [
                    {"id": 10, "title": "42", "available": True, "price": "199.00"},
                    {"id": 11, "title": "43", "available": False, "price": "199.00"},
                ],
            },
            {
                "title": "Dunk Low",
                "handle": "dunk",
                "variants": [{"id": 20, "title": "42", "available": True, "price": "129.00"}],
            },
        ]
    }
    target = make_target(type="shopify_collection", url="https://s.com/collections/all")
    items = adapters.parse_shopify_collection(target, httpx.Response(200, json=payload))
    assert len(items) == 3

    filtered = adapters.parse_shopify_collection(
        make_target(
            type="shopify_collection",
            url="https://s.com/collections/all",
            match={"keyword": "jordan"},
        ),
        httpx.Response(200, json=payload),
    )
    assert len(filtered) == 2, len(filtered)
    assert filtered[0].url == "https://s.com/products/aj1?variant=10", filtered[0].url


# --------------------------------------------------------------------------- #
# Adapter JSON
# --------------------------------------------------------------------------- #

@test("adapter json naviga percorsi puntati e available_when")
def _() -> None:
    payload = {
        "data": {
            "variants": [
                {"sku": "A1", "size": "42", "stock": {"status": "in_stock"}, "price": {"amount": 99.5}},
                {"sku": "A2", "size": "43", "stock": {"status": "sold_out"}, "price": {"amount": 99.5}},
            ]
        }
    }
    target = make_target(
        type="json",
        url="https://api.example.com/p/1",
        options={
            "items_path": "data.variants",
            "key_path": "sku",
            "title_path": "size",
            "available_path": "stock.status",
            "available_when": ["in_stock"],
            "price_path": "price.amount",
        },
    )
    items = adapters.parse_json(target, httpx.Response(200, json=payload))
    assert len(items) == 2
    assert items[0].key == "A1" and items[0].available is True
    assert items[1].available is False
    assert items[0].price == "99.50", items[0].price


@test("adapter json richiede available_path")
def _() -> None:
    target = make_target(type="json", url="https://api.example.com/p/1", options={})
    try:
        adapters.parse_json(target, httpx.Response(200, json={}))
    except adapters.AdapterError:
        return
    raise AssertionError("attesa AdapterError")


# --------------------------------------------------------------------------- #
# Adapter HTML
# --------------------------------------------------------------------------- #

@test("adapter html: il marcatore di esaurito ha la precedenza")
def _() -> None:
    target = make_target(
        type="html",
        url="https://e.it/p",
        options={"out_of_stock_when": ["Esaurito"], "in_stock_when": ["Aggiungi al carrello"]},
    )
    sold_out = "<div>Esaurito</div><button>Aggiungi al carrello</button>"
    assert adapters.parse_html(target, httpx.Response(200, text=sold_out))[0].available is False

    in_stock = "<button>Aggiungi al carrello</button>"
    assert adapters.parse_html(target, httpx.Response(200, text=in_stock))[0].available is True

    neither = "<p>Pagina generica</p>"
    assert adapters.parse_html(target, httpx.Response(200, text=neither))[0].available is False


@test("adapter html supporta le regex")
def _() -> None:
    target = make_target(
        type="html",
        url="https://e.it/p",
        options={"in_stock_when": [r"disponibilit[aà]:\s*\d+"], "regex": True},
    )
    assert adapters.parse_html(target, httpx.Response(200, text="Disponibilita: 7"))[0].available is True
    assert adapters.parse_html(target, httpx.Response(200, text="Disponibilita: -"))[0].available is False


# --------------------------------------------------------------------------- #
# Stato
# --------------------------------------------------------------------------- #

@test("stato: primo giro silenzioso, poi solo le transizioni")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        state = State(path)

        def snapshot(a: bool, b: bool) -> list[Item]:
            return [
                Item(key="1", title="42", available=a, url="u1"),
                Item(key="2", title="43", available=b, url="u2"),
            ]

        # Primo giro: fotografa e basta, anche se qualcosa e' gia' disponibile.
        assert state.diff("T", snapshot(False, True)) == []

        # Nessun cambiamento -> nessun evento.
        assert state.diff("T", snapshot(False, True)) == []

        # Esaurito -> disponibile: un solo restock.
        changes = state.diff("T", snapshot(True, True))
        assert len(changes) == 1, changes
        assert changes[0].kind == "restock" and changes[0].item.key == "1"

        # Ancora disponibile: non si riavvisa.
        assert state.diff("T", snapshot(True, True)) == []

        # Tornato esaurito e poi di nuovo disponibile: si riavvisa.
        state.diff("T", snapshot(False, True))
        assert len(state.diff("T", snapshot(True, True))) == 1


@test("stato: una variante mai vista e disponibile e' un evento 'new'")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")
        state.diff("T", [Item(key="1", title="42", available=False, url="u")])
        changes = state.diff(
            "T",
            [
                Item(key="1", title="42", available=False, url="u"),
                Item(key="2", title="43", available=True, url="u"),
            ],
        )
        assert len(changes) == 1 and changes[0].kind == "new", changes


@test("stato: sopravvive al riavvio")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        first = State(path)
        first.diff("T", [Item(key="1", title="42", available=False, url="u")])
        first.save()

        second = State(path)
        assert second.is_seeded("T")
        changes = second.diff("T", [Item(key="1", title="42", available=True, url="u")])
        assert len(changes) == 1 and changes[0].kind == "restock"


@test("stato: file corrotto non blocca l'avvio")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        path.write_text("{ non json", encoding="utf-8")
        state = State(path)
        assert state.diff("T", [Item(key="1", title="42", available=True, url="u")]) == []


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def write_config(tmp: str, body: str) -> Path:
    path = Path(tmp) / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@test("config: caricamento valido con ereditarieta' dei default")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_config(
            tmp,
            "defaults:\n"
            "  interval: 25\n"
            "  notify: [console]\n"
            "targets:\n"
            "  - name: A\n"
            "    type: shopify_product\n"
            "    url: https://s.com/products/x\n"
            "  - name: B\n"
            "    type: html\n"
            "    url: https://s.com/p\n"
            "    interval: 10\n"
            "    options:\n"
            "      out_of_stock_when: [Esaurito]\n",
        )
        settings = config.load(path)
        assert len(settings.targets) == 2
        assert settings.targets[0].interval == 25.0
        assert settings.targets[1].interval == 10.0
        assert settings.targets[0].notify == ["console"]
        assert settings.state_file.name == "state.json"


@test("config: rifiuta un intervallo sotto il minimo")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_config(
            tmp,
            "targets:\n"
            "  - name: A\n"
            "    type: shopify_product\n"
            "    url: https://s.com/products/x\n"
            "    interval: 0.5\n",
        )
        try:
            config.load(path)
        except config.ConfigError as exc:
            assert "minimo" in str(exc), exc
            return
    raise AssertionError("atteso ConfigError sull'intervallo")


@test("config: rifiuta tipo sconosciuto, URL relativo e nomi duplicati")
def _() -> None:
    cases = [
        "targets:\n  - name: A\n    type: sconosciuto\n    url: https://s.com/x\n",
        "targets:\n  - name: A\n    type: html\n    url: /prodotto\n",
        (
            "targets:\n"
            "  - name: A\n    type: html\n    url: https://s.com/1\n"
            "  - name: A\n    type: html\n    url: https://s.com/2\n"
        ),
        "targets: []\n",
    ]
    for body in cases:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(tmp, body)
            try:
                config.load(path)
            except config.ConfigError:
                continue
            raise AssertionError(f"atteso ConfigError per:\n{body}")


@test("config: il template di esempio e' valido")
def _() -> None:
    example = Path(__file__).parent / "config.example.yaml"
    if not example.is_file():
        raise AssertionError("config.example.yaml non trovato")
    settings = config.load(example)
    assert len(settings.targets) == 5, len(settings.targets)
    assert settings.respect_robots is True
    for target in settings.targets:
        assert adapters.request_url(target).startswith("http")


# --------------------------------------------------------------------------- #
# Adapter links
# --------------------------------------------------------------------------- #

@test("adapter links estrae, deduplica e costruisce gli URL")
def _() -> None:
    body = """
      <a href="/products/sneaker-uno">A</a>
      <a href="/products/sneaker-due">B</a>
      <a href="/products/sneaker-uno">A di nuovo</a>
      <a href="/pages/chi-siamo">no</a>
    """
    target = make_target(
        type="links",
        url="https://s.com/collections/all",
        options={"pattern": r"/products/([a-z0-9\-]+)", "base": "https://s.com/products/"},
    )
    items = adapters.parse_links(target, httpx.Response(200, text=body))
    assert [i.key for i in items] == ["sneaker-uno", "sneaker-due"], [i.key for i in items]
    assert items[0].url == "https://s.com/products/sneaker-uno", items[0].url
    assert items[0].title == "sneaker uno", items[0].title
    assert all(i.available for i in items), "ogni voce di un elenco vale come disponibile"


@test("adapter links applica include, exclude e limit")
def _() -> None:
    body = " ".join(f'<loc>https://g.it/prod-{n}-pokemon</loc>' for n in range(5))
    body += " ".join(f'<loc>https://g.it/prod-{n}-magic</loc>' for n in range(5))
    body += '<loc>https://g.it/prod-9-pokemon-usato</loc>'

    pattern = r"<loc>\s*(https://g\.it/[^<\s]+)\s*</loc>"

    only_pokemon = adapters.parse_links(
        make_target(type="links", url="https://g.it/sitemap.xml", options={"pattern": pattern, "include": ["pokemon"]}),
        httpx.Response(200, text=body),
    )
    assert len(only_pokemon) == 6, len(only_pokemon)

    without_used = adapters.parse_links(
        make_target(
            type="links",
            url="https://g.it/sitemap.xml",
            options={"pattern": pattern, "include": ["pokemon"], "exclude": ["usato"]},
        ),
        httpx.Response(200, text=body),
    )
    assert len(without_used) == 5, len(without_used)

    capped = adapters.parse_links(
        make_target(type="links", url="https://g.it/sitemap.xml", options={"pattern": pattern, "limit": 3}),
        httpx.Response(200, text=body),
    )
    assert len(capped) == 3, len(capped)

    # Gli URL gia' assoluti non vengono prefissati.
    assert only_pokemon[0].url.startswith("https://g.it/"), only_pokemon[0].url


@test("adapter links segnala pattern mancante o non valido")
def _() -> None:
    for options in ({}, {"pattern": "([a-z"}):
        try:
            adapters.parse_links(
                make_target(type="links", url="https://s.com/x", options=options),
                httpx.Response(200, text="niente"),
            )
        except adapters.AdapterError:
            continue
        raise AssertionError(f"attesa AdapterError per options={options}")


@test("adapter links: una voce nuova produce un evento, le vecchie no")
def _() -> None:
    target = make_target(
        type="links",
        url="https://s.com/lanci",
        options={"pattern": r"/t/([a-z0-9\-]+)", "base": "https://s.com/t/"},
    )
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")

        first = adapters.parse_links(target, httpx.Response(200, text='<a href="/t/uno">'))
        assert state.diff("L", first) == [], "il primo giro deve restare silenzioso"

        same = adapters.parse_links(target, httpx.Response(200, text='<a href="/t/uno">'))
        assert state.diff("L", same) == [], "nessuna novita', nessun evento"

        more = adapters.parse_links(target, httpx.Response(200, text='<a href="/t/uno"><a href="/t/due">'))
        changes = state.diff("L", more)
        assert len(changes) == 1 and changes[0].kind == "new", changes
        assert changes[0].item.url == "https://s.com/t/due", changes[0].item.url


@test("adapter links: title_from ricava un titolo leggibile")
def _() -> None:
    # Forma reale di nike.com: slug-IDCASUALE/CODICE-ARTICOLO
    body = '<a href="/it/t/scarpa-nike-dunk-low-uomo-aDZDHfiy/IB3079-200">x</a>'
    options = {
        "pattern": r"/it/t/([A-Za-z0-9\-]{4,90}/[A-Z0-9\-]{4,20})",
        "base": "https://www.nike.com/it/t/",
    }
    target = make_target(type="links", url="https://www.nike.com/it/w/x", options=options)

    plain = adapters.parse_links(target, httpx.Response(200, text=body))
    assert plain[0].title == "IB3079 200", plain[0].title  # senza title_from: solo il codice

    options_with_title = dict(options, title_from=r"^([A-Za-z0-9\-]+?)(?:-[A-Za-z0-9]{8})?/")
    nicer = adapters.parse_links(
        make_target(type="links", url="https://www.nike.com/it/w/x", options=options_with_title),
        httpx.Response(200, text=body),
    )
    assert nicer[0].title == "scarpa nike dunk low uomo", nicer[0].title
    assert nicer[0].key == "scarpa-nike-dunk-low-uomo-aDZDHfiy/IB3079-200", nicer[0].key
    assert nicer[0].url == "https://www.nike.com/it/t/scarpa-nike-dunk-low-uomo-aDZDHfiy/IB3079-200"


@test("adapter links: title_from non valido viene segnalato")
def _() -> None:
    try:
        adapters.parse_links(
            make_target(type="links", url="https://s.com/x", options={"pattern": "(a)", "title_from": "([a-z"}),
            httpx.Response(200, text="a"),
        )
    except adapters.AdapterError:
        return
    raise AssertionError("attesa AdapterError")


# --------------------------------------------------------------------------- #
# Accertamento della disponibilita' (blocco detail)
# --------------------------------------------------------------------------- #

@test("elenchi: le voci nascono non accertate")
def _() -> None:
    items = adapters.parse_links(
        make_target(type="links", url="https://s.com/x", options={"pattern": r"/p/(\w+)"}),
        httpx.Response(200, text='<a href="/p/uno">'),
    )
    assert items[0].verified is False, "un elenco non puo' sapere se il prodotto e' comprabile"
    assert items[0].available is True, "available=True significa 'presente in elenco'"


@test("il marcatore dei preset riconosce sia le virgolette semplici sia quelle sfuggite")
def _() -> None:
    from restock.presets import AVAILABLE_TRUE

    # Travis Scott: JSON diretto nella pagina.
    assert adapters.evaluate_markers('{"available":true}', [AVAILABLE_TRUE], [], True)
    assert not adapters.evaluate_markers('{"available":false}', [AVAILABLE_TRUE], [], True)
    # Nike SNKRS: JSON dentro una stringa, virgolette sfuggite.
    assert adapters.evaluate_markers(r'{\"available\":true}', [AVAILABLE_TRUE], [], True)
    assert not adapters.evaluate_markers(r'{\"available\":false}', [AVAILABLE_TRUE], [], True)
    # Pagina mista: basta una taglia disponibile.
    assert adapters.evaluate_markers(r'\"available\":false,\"available\":true', [AVAILABLE_TRUE], [], True)


@test("evaluate_markers: l'esaurito ha la precedenza")
def _() -> None:
    body = "Esaurito. Aggiungi al carrello"
    assert adapters.evaluate_markers(body, ["Aggiungi al carrello"], ["Esaurito"]) is False
    assert adapters.evaluate_markers("Aggiungi al carrello", ["Aggiungi al carrello"], ["Esaurito"]) is True


@test("nome del prodotto: preferisce h1, poi og:title, poi title")
def _() -> None:
    h1 = "<title>Roba - Shop - Supreme</title><h1 class='x'>Giacca Larry Clark</h1>"
    assert adapters.estrai_nome(h1, "https://eu.supreme.com/products/abc") == "Giacca Larry Clark"

    og = '<meta property="og:title" content="Felpa con cappuccio - Shop"><title>x - Supreme</title>'
    assert adapters.estrai_nome(og, "https://eu.supreme.com/p") == "Felpa con cappuccio"

    solo_title = "<title>Sneaker X - Shop - Supreme</title>"
    assert adapters.estrai_nome(solo_title, "https://eu.supreme.com/p") == "Sneaker X"


@test("nome del prodotto: entita' HTML e spazi vengono ripuliti")
def _() -> None:
    corpo = "<h1>\n  Supreme&#174;/Schott&reg;\n  Leather   Jacket\n</h1>"
    assert adapters.estrai_nome(corpo) == "Supreme®/Schott® Leather Jacket"


@test("nome del prodotto: se non c'e' niente di utile non inventa")
def _() -> None:
    assert adapters.estrai_nome("<p>nessun titolo qui</p>") is None
    assert adapters.estrai_nome("<h1></h1><title>x</title>") is None  # troppo corto


@test("stato: il nome letto dalla pagina viene conservato")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        percorso = Path(tmp) / "state.json"
        state = State(percorso)

        con_nome = Item(
            key="abc",
            title="Giacca Larry Clark",
            available=False,
            url="u",
            verified=True,
            extra={"nome_pagina": "Giacca Larry Clark"},
        )
        state.diff("T", [con_nome])
        assert state.known("T", "abc")["nome_pagina"] == "Giacca Larry Clark"

        state.save()
        ricaricato = State(percorso)
        assert ricaricato.known("T", "abc")["nome_pagina"] == "Giacca Larry Clark"


@test("taglie: lette dall'elenco varianti, con id per il link diretto")
def _() -> None:
    corpo = (
        '<html><script>var meta = {"product":{"variants":['
        '{"id":1,"public_title":"Small","sku":"A"},'
        '{"id":2,"public_title":"Medium","sku":"B"}]}};</script>'
        '<script>{"variants":['
        '{"id":11,"public_title":"Small","available":true},'
        '{"id":12,"public_title":"Medium","available":false},'
        '{"id":13,"public_title":"Large","available":true}]}</script></html>'
    )
    taglie = adapters.estrai_taglie(corpo)
    # Il primo elenco non ha la disponibilita': va scartato in favore del secondo.
    assert [t["nome"] for t in taglie] == ["Small", "Medium", "Large"], taglie
    assert [t["disponibile"] for t in taglie] == [True, False, True], taglie
    assert taglie[0]["id"] == "11", taglie[0]


@test("taglie: sigle minuscole normalizzate, duplicati rimossi")
def _() -> None:
    corpo = (
        '{"variants":[{"id":1,"option1":"s","available":true},'
        '{"id":2,"option1":"2xl","available":true},'
        '{"id":3,"option1":"s","available":false}]}'
    )
    taglie = adapters.estrai_taglie(corpo)
    assert [t["nome"] for t in taglie] == ["S", "2XL"], taglie
    # La prima occorrenza vince: la ripetizione non deve sovrascrivere.
    assert taglie[0]["disponibile"] is True


@test("taglie: senza elenco affidabile non se ne inventano")
def _() -> None:
    assert adapters.estrai_taglie("<p>niente</p>") == []
    # Una sola variante non e' un elenco di taglie: e' il prodotto stesso.
    assert adapters.estrai_taglie('{"variants":[{"id":1,"title":"Unica","available":true}]}') == []


@test("notifiche: il messaggio elenca le taglie con il link a ciascuna")
def _() -> None:
    from restock.notify import _line

    item = Item(
        key="k",
        title="Giacca",
        available=True,
        url="https://s.com/products/x",
        verified=True,
        extra={
            "taglie": [
                {"nome": "Small", "disponibile": True, "id": "11"},
                {"nome": "Medium", "disponibile": False, "id": "12"},
                {"nome": "Large", "disponibile": True, "id": None},
            ]
        },
    )
    testo = _line(Change("Store", item, "restock"))
    assert "Taglie disponibili (2 su 3)" in testo, testo
    assert "Small  ->  https://s.com/products/x?variant=11" in testo, testo
    assert "Large" in testo and "?variant=None" not in testo, testo
    # L'esaurita non compare fra quelle acquistabili.
    assert "Medium" not in testo, testo


@test("telegram: una tastiera con un pulsante per taglia")
def _() -> None:
    from restock.notify import tastiera_taglie

    item = Item(
        key="k",
        title="Giacca",
        available=True,
        url="https://s.com/products/x",
        verified=True,
        extra={
            "taglie": [
                {"nome": "S", "disponibile": True, "id": "1"},
                {"nome": "M", "disponibile": False, "id": "2"},
                {"nome": "L", "disponibile": True, "id": "3"},
                {"nome": "XL", "disponibile": True, "id": "4"},
                {"nome": "2XL", "disponibile": True, "id": "5"},
            ]
        },
    )
    tastiera = tastiera_taglie(Change("Store", item, "restock"))
    righe = tastiera["inline_keyboard"]

    # Tre per riga, piu' la riga finale con il prodotto intero.
    etichette = [[b["text"] for b in riga] for riga in righe]
    assert etichette == [["S", "L", "XL"], ["2XL"], ["Apri il prodotto"]], etichette

    primo = righe[0][0]
    assert primo["url"] == "https://s.com/products/x?variant=1", primo
    assert righe[-1][0]["url"] == "https://s.com/products/x"


@test("telegram: il separatore del link rispetta la query gia' presente")
def _() -> None:
    from restock.notify import link_taglia

    con_query = Item(key="k", title="x", available=True, url="https://s.com/p?utm=1")
    cambio = Change("S", con_query, "restock")
    assert link_taglia(cambio, {"nome": "S", "id": "9"}) == "https://s.com/p?utm=1&variant=9"

    pulito = Item(key="k", title="x", available=True, url="https://s.com/p")
    assert link_taglia(Change("S", pulito, "restock"), {"nome": "S", "id": "9"}) == (
        "https://s.com/p?variant=9"
    )
    # Senza id non si inventa una variante: si apre il prodotto e basta.
    assert link_taglia(Change("S", pulito, "restock"), {"nome": "S", "id": None}) == "https://s.com/p"


@test("telegram: senza taglie non c'e' nessuna tastiera")
def _() -> None:
    from restock.notify import tastiera_taglie

    item = Item(key="k", title="x", available=True, url="https://s.com/p")
    assert tastiera_taglie(Change("S", item, "restock")) is None

    esaurite = Item(
        key="k", title="x", available=True, url="https://s.com/p",
        extra={"taglie": [{"nome": "S", "disponibile": False, "id": "1"}]},
    )
    assert tastiera_taglie(Change("S", esaurite, "restock")) is None


@test("notifiche: senza taglie il messaggio resta quello di prima")
def _() -> None:
    from restock.notify import _line

    item = Item(key="k", title="Prodotto", available=True, url="https://s.com/p")
    testo = _line(Change("Store", item, "restock"))
    assert "Taglie" not in testo, testo
    assert testo.endswith("https://s.com/p"), testo


# --------------------------------------------------------------------------- #
# Amazon
# --------------------------------------------------------------------------- #

AMAZON_RICERCA = """
<div data-asin="B0AAAAAAA1" data-index="1" data-component-type="s-search-result">
  <h2><span>Console Uno</span></h2>
  <span class="a-price" data-a-size="xl"><span class="a-offscreen">619,79&nbsp;€</span></span>
  <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">649,99&nbsp;€</span></span>
</div>
<div data-asin="B0AAAAAAA2" data-index="2" data-component-type="s-search-result">
  <h2><span>Controller Due</span></h2>
  <span class="a-price" data-a-size="xl"><span class="a-offscreen">1.067,49 €</span></span>
</div>
<div data-asin="B0AAAAAAA3" data-index="3" data-component-type="s-search-result">
  <h2><span>Gioco Esaurito</span></h2>
</div>
"""


def _amazon(tipo: str, url: str, **opzioni) -> Target:
    return make_target(type=tipo, url=url, options=opzioni)


@test("amazon: prezzi italiani con punto delle migliaia e virgola decimale")
def _() -> None:
    assert adapters.prezzo_italiano("619,79 €") == 619.79
    assert adapters.prezzo_italiano("1.067,49&nbsp;€") == 1067.49
    assert adapters.prezzo_italiano("€ 12,00") == 12.0
    assert adapters.prezzo_italiano("") is None
    assert adapters.prezzo_italiano("gratis") is None


@test("amazon: la ricerca da' prodotti, prezzi, listino e sconto")
def _() -> None:
    items = adapters.parse_amazon_search(
        _amazon("amazon_search", "https://www.amazon.it/s?k=x"),
        httpx.Response(200, text=AMAZON_RICERCA, request=httpx.Request("GET", "https://www.amazon.it/s?k=x")),
    )
    assert [i.key for i in items] == ["B0AAAAAAA1", "B0AAAAAAA2", "B0AAAAAAA3"]

    uno, due, tre = items
    assert uno.title == "Console Uno" and uno.available
    assert uno.extra["prezzo_num"] == 619.79 and uno.extra["listino_num"] == 649.99
    assert uno.extra["sconto_pct"] == 5, uno.extra
    assert uno.url == "https://www.amazon.it/dp/B0AAAAAAA1"

    assert due.extra["prezzo_num"] == 1067.49 and due.extra["listino_num"] is None

    # Senza prezzo in pagina non si puo' comprare da li'.
    assert tre.available is False and tre.extra["prezzo_num"] is None


@test("amazon: la scheda legge disponibilita' e prezzo del riquadro d'acquisto")
def _() -> None:
    scheda = """
      <input type="hidden" name="ASIN" value="B0AAAAAAA1">
      <span id="productTitle">  Console Uno  </span>
      <div id="corePriceDisplay_desktop_feature_div">
        <span class="a-price aok-align-center priceToPay" data-a-size="xl"><span class="a-offscreen">619,79 €</span></span>
        <span class="a-price a-text-price apex-basisprice-value" data-a-strike="true"><span class="a-offscreen">649,99 €</span></span>
      </div>
      <div id="availability"><span>Disponibilità immediata</span></div>
    """
    t = _amazon("amazon_product", "https://www.amazon.it/dp/B0AAAAAAA1")
    [p] = adapters.parse_amazon_product(t, httpx.Response(200, text=scheda))
    assert p.key == "B0AAAAAAA1" and p.title == "Console Uno"
    assert p.available is True
    assert p.extra["prezzo_num"] == 619.79 and p.extra["sconto_pct"] == 5, p.extra

    esaurita = scheda.replace("Disponibilità immediata", "Attualmente non disponibile.")
    [p] = adapters.parse_amazon_product(t, httpx.Response(200, text=esaurita))
    assert p.available is False


@test("amazon: la verifica anti-bot viene riconosciuta e non interpretata come dati")
def _() -> None:
    sfida = "<html><form action='/errors/validateCaptcha'>Inserisci i caratteri che vedi</form></html>"
    for tipo, url in (("amazon_search", "https://www.amazon.it/s?k=x"), ("amazon_product", "https://www.amazon.it/dp/B0AAAAAAA1")):
        try:
            adapters.parse(_amazon(tipo, url), httpx.Response(200, text=sfida, request=httpx.Request("GET", url)))
        except adapters.SfidaAntiBot:
            continue
        raise AssertionError(f"{tipo}: la verifica anti-bot doveva essere segnalata")


@test("sconto: un calo oltre la soglia produce un avviso con il prezzo di prima")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")

        def prodotto(prezzo: float) -> Item:
            return Item(key="A", title="Console", available=True, url="u",
                        price=f"{prezzo:.2f}", extra={"prezzo_num": prezzo})

        state.diff("T", [prodotto(649.99)], soglia_sconto=5)            # fotografia
        assert state.diff("T", [prodotto(640.00)], soglia_sconto=5) == []  # -1.5%: sotto soglia

        cambi = state.diff("T", [prodotto(599.00)], soglia_sconto=5)
        assert len(cambi) == 1 and cambi[0].kind == "sconto", cambi
        assert cambi[0].item.extra["prezzo_precedente"] == 640.00
        assert "[SCONTO (-6.4%)]" in cambi[0].headline, cambi[0].headline

        # Lo stesso prezzo al giro dopo non e' di nuovo uno sconto.
        assert state.diff("T", [prodotto(599.00)], soglia_sconto=5) == []
        # Un rialzo non e' uno sconto.
        assert state.diff("T", [prodotto(629.00)], soglia_sconto=5) == []


@test("sconto: senza soglia il prezzo si ricorda ma non si notifica")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")
        voce = lambda p: Item(key="A", title="x", available=True, url="u", extra={"prezzo_num": p})
        state.diff("T", [voce(100.0)])
        assert state.diff("T", [voce(50.0)]) == []
        assert state.known("T", "A")["prezzo_num"] == 50.0


@test("sconto: il prezzo resta in memoria anche mentre il prodotto e' esaurito")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")
        state.diff("T", [Item(key="A", title="x", available=True, url="u", extra={"prezzo_num": 100.0})], 5)
        # Esaurito: su Amazon il prezzo sparisce dalla pagina.
        state.diff("T", [Item(key="A", title="x", available=False, url="u", extra={"prezzo_num": None})], 5)
        assert state.known("T", "A")["prezzo_num"] == 100.0, "l'ultimo prezzo noto andava conservato"


@test("notifiche: lo sconto dice da quanto a quanto")
def _() -> None:
    from restock.notify import testo_prezzo

    item = Item(key="A", title="Console", available=True, url="u", price="599,00 €",
                extra={"prezzo_num": 599.0, "prezzo_precedente": 649.99, "calo_pct": 7.8})
    assert testo_prezzo(Change("Amazon", item, "sconto")) == "599,00 € (era 649,99 €)"

    listino = Item(key="A", title="x", available=True, url="u", price="619,79 €",
                   extra={"listino_num": 649.99, "sconto_pct": 5})
    assert testo_prezzo(Change("Amazon", listino, "new")) == "619,79 € (listino 649,99 €, -5%)"


@test("amazon: la soglia di sconto predefinita vale solo per i target Amazon")
def _() -> None:
    from restock.monitor import _soglia

    assert _soglia(make_target(type="amazon_search", url="https://www.amazon.it/s?k=x")) == 5.0
    assert _soglia(make_target(type="html", url="https://s.com/p", options={"out_of_stock_when": ["x"]})) is None
    assert _soglia(make_target(type="html", url="https://s.com/p", options={"soglia_sconto": 12})) == 12.0


@test("config: il blocco detail viene validato")
def _() -> None:
    base = (
        "targets:\n"
        "  - name: A\n"
        "    type: {tipo}\n"
        "    url: https://s.com/x\n"
        "    options: {{pattern: '/p/(a)'}}\n"
        "    detail:\n{detail}"
    )
    casi = [
        # detail su un tipo che gia' sa leggere la disponibilita' da solo
        ("html", "      in_stock_when: [x]\n", "solo per type=links"),
        # detail senza nessun marcatore
        ("links", "      max_checks: 3\n", "in_stock_when o out_of_stock_when"),
        # max_checks assurdo
        ("links", "      in_stock_when: [x]\n      max_checks: 0\n", "maggiore di zero"),
    ]
    for tipo, blocco, atteso in casi:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(base.format(tipo=tipo, detail=blocco), encoding="utf-8")
            try:
                config.load(path)
            except config.ConfigError as exc:
                assert atteso in str(exc), f"messaggio poco chiaro: {exc}"
                continue
            raise AssertionError(f"atteso ConfigError per {tipo} / {blocco!r}")

    # Caso valido.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(
            base.format(tipo="links", detail="      in_stock_when: ['x']\n      max_checks: 3\n"),
            encoding="utf-8",
        )
        target = config.load(path).targets[0]
        assert target.checks_detail is True
        assert target.detail["max_checks"] == 3


@test("stato: un articolo nuovo gia' esaurito viene comunque segnalato")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")
        state.diff("T", [Item(key="1", title="a", available=True, url="u", verified=True)])

        # Nuovo, accertato ed esaurito: e' comunque una novita' da sapere.
        changes = state.diff(
            "T",
            [
                Item(key="1", title="a", available=True, url="u", verified=True),
                Item(key="2", title="b", available=False, url="u2", verified=True),
            ],
        )
        assert len(changes) == 1 and changes[0].kind == "new", changes
        assert "[ESAURITO]" in changes[0].headline, changes[0].headline

        # Quando torna disponibile e' un restock, senza etichetta ridondante.
        changes = state.diff(
            "T",
            [
                Item(key="1", title="a", available=True, url="u", verified=True),
                Item(key="2", title="b", available=True, url="u2", verified=True),
            ],
        )
        assert len(changes) == 1 and changes[0].kind == "restock", changes
        assert "ESAURITO" not in changes[0].headline


@test("stato: senza accertamento non si dichiara la disponibilita'")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")
        state.diff("T", [Item(key="1", title="a", available=True, url="u", verified=False)])
        changes = state.diff(
            "T",
            [
                Item(key="1", title="a", available=True, url="u", verified=False),
                Item(key="2", title="nuovo", available=True, url="u2", verified=False),
            ],
        )
        assert len(changes) == 1 and changes[0].kind == "new"
        titolo = changes[0].headline
        assert "DISPONIBILE" not in titolo and "ESAURITO" not in titolo, titolo


# --------------------------------------------------------------------------- #
# Attivazione dei singoli target
# --------------------------------------------------------------------------- #

@test("config: il campo enabled viene letto, con default a true")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(
            "targets:\n"
            "  - name: A\n    type: html\n    url: https://s.com/1\n"
            "    options: {out_of_stock_when: [x]}\n"
            "  - name: B\n    type: html\n    url: https://s.com/2\n"
            "    enabled: false\n"
            "    options: {out_of_stock_when: [x]}\n"
            "  - name: C\n    type: html\n    url: https://s.com/3\n"
            "    enabled: true\n"
            "    options: {out_of_stock_when: [x]}\n",
            encoding="utf-8",
        )
        settings = config.load(path)
        assert [t.enabled for t in settings.targets] == [True, False, True]


@test("monitor: run_once salta i target disattivati")
def _() -> None:
    import asyncio

    from restock.monitor import Monitor

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        # URL irraggiungibile di proposito: se venisse interrogato fallirebbe,
        # quindi un exit code pulito prova che e' stato saltato davvero.
        path.write_text(
            "defaults: {user_agent: test}\n"
            "targets:\n"
            "  - name: Spento\n"
            "    type: html\n"
            "    url: http://127.0.0.1:9/mai\n"
            "    enabled: false\n"
            "    options: {out_of_stock_when: [x]}\n",
            encoding="utf-8",
        )
        settings = config.load(path)

        async def run() -> int:
            monitor = Monitor(settings)
            try:
                return await monitor.run_once()
            finally:
                await monitor.close()

        assert asyncio.run(run()) == 0, "un target disattivato non deve produrre errori"


@test("monitor: run termina subito se nessun target e' attivo")
def _() -> None:
    import asyncio

    from restock.monitor import Monitor

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(
            "defaults: {user_agent: test}\n"
            "targets:\n"
            "  - name: Spento\n"
            "    type: html\n"
            "    url: http://127.0.0.1:9/mai\n"
            "    enabled: false\n"
            "    options: {out_of_stock_when: [x]}\n",
            encoding="utf-8",
        )
        settings = config.load(path)

        async def run() -> None:
            monitor = Monitor(settings)
            try:
                # Senza l'uscita anticipata questo resterebbe appeso.
                await asyncio.wait_for(monitor.run(), timeout=5)
            finally:
                await monitor.close()

        asyncio.run(run())


# --------------------------------------------------------------------------- #
# Notifiche Telegram
# --------------------------------------------------------------------------- #

@test("istanza unica: il secondo lucchetto viene rifiutato")
def _() -> None:
    from restock.istanza import GiaInEsecuzione, Lucchetto

    with tempfile.TemporaryDirectory() as tmp:
        percorso = Path(tmp) / "monitor.lock"

        primo = Lucchetto(percorso)
        primo.acquisisci()
        try:
            secondo = Lucchetto(percorso)
            try:
                secondo.acquisisci()
            except GiaInEsecuzione as exc:
                assert "due volte" in str(exc), f"messaggio poco chiaro: {exc}"
            else:
                secondo.rilascia()
                raise AssertionError("il secondo lucchetto doveva essere rifiutato")
        finally:
            primo.rilascia()

        # Rilasciato il primo, il lucchetto torna disponibile.
        terzo = Lucchetto(percorso)
        terzo.acquisisci()
        terzo.rilascia()


@test("istanza unica: due processi separati non possono monitorare insieme")
def _() -> None:
    import subprocess
    import sys as _sys

    from restock.istanza import Lucchetto

    with tempfile.TemporaryDirectory() as tmp:
        percorso = Path(tmp) / "monitor.lock"
        mio = Lucchetto(percorso)
        mio.acquisisci()
        try:
            # Un vero secondo processo: il blocco e' del sistema operativo,
            # quindi deve valere anche fuori da questo interprete.
            codice = (
                "import sys;"
                "sys.path.insert(0, r'" + str(Path(__file__).resolve().parent) + "');"
                "from restock.istanza import Lucchetto, GiaInEsecuzione;"
                "l = Lucchetto(r'" + str(percorso) + "');"
                "\ntry:\n l.acquisisci()\n print('PRESO')\nexcept GiaInEsecuzione:\n print('RIFIUTATO')"
            )
            esito = subprocess.run(
                [_sys.executable, "-c", codice],
                capture_output=True, text=True, timeout=60,
            )
            assert "RIFIUTATO" in esito.stdout, f"uscita inattesa: {esito.stdout!r} {esito.stderr[:200]!r}"
        finally:
            mio.rilascia()


@test("monitor: il riepilogo periodico dice che sta lavorando")
def _() -> None:
    import asyncio
    import logging as _logging

    from restock.monitor import Monitor

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(
            "defaults: {user_agent: test}\n"
            "targets:\n"
            "  - name: A\n    type: html\n    url: https://s.com/x\n"
            "    options: {out_of_stock_when: [x]}\n",
            encoding="utf-8",
        )
        settings = config.load(path)

    righe: list[str] = []

    class Cattura(_logging.Handler):
        def emit(self, record):
            righe.append(record.getMessage())

    async def run() -> None:
        monitor = Monitor(settings)
        monitor._ultimo_esito["A"] = (224, 163)
        monitor._avvisi_inviati = 2
        try:
            # Intervallo minuscolo: si vuole solo vedere la riga prodotta.
            await asyncio.wait_for(monitor._riepilogo(ogni=0.05), timeout=0.4)
        except asyncio.TimeoutError:
            pass
        finally:
            await monitor.close()

    logger = _logging.getLogger("restock.monitor")
    handler = Cattura()
    livello = logger.level
    # Senza questo il logger resta a WARNING e le righe INFO non arrivano mai
    # al gestore: il test fallirebbe per un motivo suo, non del codice provato.
    logger.setLevel(_logging.INFO)
    logger.addHandler(handler)
    try:
        asyncio.run(run())
    finally:
        logger.removeHandler(handler)
        logger.setLevel(livello)

    assert righe, "il riepilogo non ha prodotto nessuna riga"
    riga = righe[-1]
    for atteso in ("In ascolto da", "2 avvisi inviati", "224 articoli", "163 disponibili"):
        assert atteso in riga, f"{atteso!r} assente da {riga!r}"


@test("telegram: gli errori vengono tradotti in indicazioni utili")
def _() -> None:
    from restock.notify import TelegramNotifier

    cases = [
        (401, "Unauthorized", "token"),
        (400, "Bad Request: chat not found", "chat_id"),
        (403, "Forbidden: bot was blocked by the user", "sbloccalo"),
        (400, "Bad Request: not enough rights", "permesso"),
    ]
    for status, description, expected in cases:
        message = TelegramNotifier.diagnose(status, description)
        assert expected in message, f"{description!r} -> {message!r}"


# --------------------------------------------------------------------------- #
# Paginazione: coprire tutto il catalogo, non solo la prima pagina
# --------------------------------------------------------------------------- #

@test("paginazione: una sola pagina se non richiesto altrimenti")
def _() -> None:
    target = make_target(type="shopify_collection", url="https://s.com/collections/all")
    assert adapters.request_urls(target) == [adapters.request_url(target)]


@test("paginazione: sfoglia le pagine successive col separatore giusto")
def _() -> None:
    # L'URL Shopify ha gia' una query: il separatore deve essere &
    collezione = make_target(
        type="shopify_collection",
        url="https://s.com/collections/all",
        options={"pages": 3},
    )
    urls = adapters.request_urls(collezione)
    assert len(urls) == 3, urls
    assert urls[1].endswith("&page=2") and urls[2].endswith("&page=3"), urls

    # Un URL pulito deve invece ricevere ?
    elenco = make_target(type="links", url="https://s.com/catalogo", options={"pattern": "(a)", "pages": 2})
    urls = adapters.request_urls(elenco)
    assert urls == ["https://s.com/catalogo", "https://s.com/catalogo?page=2"], urls

    # Nome del parametro personalizzabile.
    custom = make_target(
        type="links", url="https://s.com/c", options={"pattern": "(a)", "pages": 2, "page_param": "p"}
    )
    assert adapters.request_urls(custom)[1].endswith("?p=2")


@test("paginazione: valori assurdi non rompono nulla")
def _() -> None:
    for valore in (0, -3, None, "molte"):
        target = make_target(type="links", url="https://s.com/c", options={"pattern": "(a)", "pages": valore})
        assert len(adapters.request_urls(target)) == 1, valore


# --------------------------------------------------------------------------- #
# Analisi di un sito
# --------------------------------------------------------------------------- #

@test("analisi: normalizzazione dell'indirizzo di partenza")
def _() -> None:
    from restock import discover

    for scritto, atteso in (
        ("shop.esempio.com", "https://shop.esempio.com"),
        ("https://shop.esempio.com/collections/all", "https://shop.esempio.com"),
        ("http://esempio.it/prodotto?x=1", "http://esempio.it"),
    ):
        assert discover.origine_di(scritto) == atteso, scritto


@test("analisi: la proposta generata e' una configurazione valida")
def _() -> None:
    from restock import discover

    # Forme che l'analizzatore puo' produrre, tutte devono passare la validazione.
    proposte = [
        {
            "name": "sito - tutto",
            "type": "shopify_collection",
            "url": "https://s.com",
            "interval": 45,
            "notify": ["console"],
            "options": {"pages": 10},
        },
        {
            "name": "sito - elenco",
            "type": "links",
            "url": "https://s.com/collections/all",
            "interval": 60,
            "notify": ["console"],
            "options": {"pattern": r"/products/([a-z0-9\-]+)", "base": "https://s.com/products/"},
            "detail": {
                "in_stock_when": [discover.AVAILABLE_TRUE],
                "regex": True,
                "max_checks": 5,
                "recheck_sold_out": True,
            },
        },
        {
            "name": "prodotto",
            "type": "shopify_product",
            "url": "https://s.com/products/x",
            "interval": 30,
            "notify": ["console"],
        },
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        config.save_raw(path, {"defaults": {}, "notifiers": {}, "targets": proposte})
        settings = config.load(path)
    assert len(settings.targets) == 3
    assert settings.targets[0].options["pages"] == 10
    assert settings.targets[1].checks_detail is True


# --------------------------------------------------------------------------- #
# Preset
# --------------------------------------------------------------------------- #

@test("preset: ogni configurazione predefinita e' valida")
def _() -> None:
    from restock import presets

    assert presets.PRESETS, "nessun preset definito"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        config.save_raw(
            path,
            {
                "defaults": {"user_agent": "test"},
                "notifiers": {"console": {"enabled": True}},
                "targets": [dict(p.target) for p in presets.PRESETS],
            },
        )
        settings = config.load(path)

    assert len(settings.targets) == len(presets.PRESETS)
    for target in settings.targets:
        assert adapters.request_url(target).startswith("https://")


@test("preset: gli schemi di ricerca compilano e i metadati ci sono")
def _() -> None:
    import re as _re

    from restock import presets

    for preset in presets.PRESETS:
        assert preset.site and preset.name and preset.summary, preset.key
        assert preset.tested, f"{preset.key}: manca la nota di verifica"
        target = preset.target
        assert target["type"] in config.VALID_TYPES, target["type"]
        if target["type"] == "links":
            _re.compile(target["options"]["pattern"])
        if target["type"] == "html":
            for expression in target["options"].get("in_stock_when", []):
                _re.compile(expression)


@test("preset: l'inserimento evita i nomi duplicati")
def _() -> None:
    from restock import presets

    preset = presets.PRESETS[0]
    base = preset.target["name"]
    first = presets.instantiate(preset, set())
    second = presets.instantiate(preset, {base})
    third = presets.instantiate(preset, {base, f"{base} 2"})
    assert first["name"] == base
    assert second["name"] == f"{base} 2"
    assert third["name"] == f"{base} 3"
    # Deve essere una copia: modificarla non tocca il preset originale.
    first["options"]["pattern"] = "cambiato"
    assert preset.target["options"]["pattern"] != "cambiato"


# --------------------------------------------------------------------------- #

def main() -> int:
    for name in PASSED:
        print(f"  ok    {name}")
    for name, tb in FAILED:
        print(f"  FALLITO  {name}")
        print("    " + tb.replace("\n", "\n    "))

    total = len(PASSED) + len(FAILED)
    print(f"\n{len(PASSED)}/{total} test superati.")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
