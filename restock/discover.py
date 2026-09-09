"""Analisi di un sito: capire cosa e' monitorabile prima di configurarlo.

Automatizza il lavoro che altrimenti si fa a mano: leggere robots.txt, provare
gli endpoint pubblici, aprire una scheda prodotto e cercare il campo di stock.
Alla fine propone una configurazione gia' pronta, oppure dice chiaramente che su
quel sito non c'e' niente da leggere.

Il principio e' non promettere: se la disponibilita' non e' ricavabile, l'esito
lo dichiara invece di inventare un marcatore che non funzionerebbe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from .httpclient import Blocked, Cooldown, PoliteClient
from .presets import AVAILABLE_TRUE

# Copertura di cio' che il monitor riuscirebbe a fare sul sito.
COMPLETA = "completa"
PARZIALE = "parziale"
NESSUNA = "nessuna"


@dataclass
class Esito:
    origine: str
    titolo: str = ""
    piattaforma: str = "sconosciuta"
    copertura: str = NESSUNA
    metodo: str = ""
    prodotti: int = 0
    proposta: dict[str, Any] | None = None
    note: list[str] = field(default_factory=list)
    problemi: list[str] = field(default_factory=list)

    alternative: list[dict[str, Any]] = field(default_factory=list)
    """Altre famiglie di link trovate nella pagina.

    Su un sito grande la navigazione puo' somigliare al catalogo piu' del
    catalogo stesso. Invece di insistere con un'euristica, si mostrano le
    possibilita' con i numeri veri e si lascia scegliere.
    """

    @property
    def riuscito(self) -> bool:
        return self.proposta is not None


def origine_di(url: str) -> str:
    parti = urlsplit(url if "://" in url else "https://" + url)
    return f"{parti.scheme}://{parti.netloc}"


def _nome_sito(origine: str) -> str:
    return urlsplit(origine).netloc.replace("www.", "")


async def _prendi(client: PoliteClient, url: str) -> httpx.Response | None:
    try:
        return await client.get(url)
    except (Blocked, Cooldown, httpx.HTTPError):
        return None


# --------------------------------------------------------------------------- #
# Deduzione dello schema dei link prodotto
# --------------------------------------------------------------------------- #

# Segmenti che quasi sempre fanno parte della struttura del sito, non del prodotto.
_SEGMENTI_FISSI = {
    "it", "en", "fr", "de", "es", "eu", "us", "uk", "shop", "store", "collections",
    "collection", "products", "product", "prodotti", "prodotto", "p", "t", "w",
    "catalogo", "categoria", "c", "launch", "pages", "page",
}


def _variabile(segmento: str) -> bool:
    """Un segmento che identifica il singolo prodotto, non la struttura del sito."""
    if segmento.lower() in _SEGMENTI_FISSI:
        return False
    return len(segmento) > 6 or any(ch.isdigit() for ch in segmento) or "-" in segmento


# Percorsi che non sono mai schede prodotto: risorse statiche e pagine di servizio.
_RUMORE = (
    "/cdn/", "/static/", "/_next/", "/assets/", "/wp-content/", "/wp-includes/",
    "/media/", "/images/", "/img/", "/fonts/", "/api/", "/help/", "/pages/",
    "/policies/", "/account", "/cart", "/checkout", "/search",
)
_ESTENSIONI = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".json", ".xml", ".atom", ".pdf", ".mp4", ".avif",
)


def _percorsi_interni(corpo: str, origine: str) -> list[str]:
    """Percorsi interni presenti nella pagina, ovunque si trovino.

    Non basta guardare gli href: su molti siti la griglia dei prodotti e' dentro
    un blocco JSON e i link veri non compaiono come attributi. Si scandisce tutto
    il corpo e si scarta il rumore (risorse statiche, pagine di servizio).
    """
    # Il percorso deve essere delimitato da virgolette su entrambi i lati: senza
    # questo vincolo si raccolgono frammenti di codice e di CSS a centinaia, che
    # poi sommergono le famiglie di link vere.
    chiusura = r"""(?=["'\\?#])"""
    grezzi = re.findall(r"""["'](/[A-Za-z0-9][A-Za-z0-9._\-/]{2,150})""" + chiusura, corpo)
    grezzi += re.findall(
        re.escape(origine) + r"(/[A-Za-z0-9][A-Za-z0-9._\-/]{2,150})" + chiusura, corpo
    )

    percorsi = []
    for percorso in grezzi:
        percorso = percorso.split("?")[0].split("#")[0].rstrip("/")
        basso = percorso.lower()
        if not percorso or basso.endswith(_ESTENSIONI):
            continue
        if any(pezzo in basso for pezzo in _RUMORE):
            continue
        percorsi.append(percorso)
    return percorsi


def _forma_di(percorso: str) -> tuple[str, ...] | None:
    segmenti = [s for s in percorso.split("/") if s]
    if not segmenti:
        return None
    forma = tuple("*" if _variabile(s) else s for s in segmenti)
    return forma if "*" in forma else None


def _regex_da_forma(forma: tuple[str, ...], origine: str) -> tuple[str, str]:
    fissi = list(forma[: forma.index("*")])
    variabili = len(forma) - len(fissi)
    prefisso = "/" + "/".join(fissi) + "/" if fissi else "/"
    pezzo = r"[A-Za-z0-9._\-]{2,90}"
    cattura = "(" + "/".join([pezzo] * variabili) + ")"
    return prefisso + cattura, origine + prefisso


def famiglie_candidate(
    corpo: str, origine: str, minimo: int = 8, quante: int = 5
) -> list[tuple[tuple[str, ...], set[str]]]:
    """Le famiglie di link piu' numerose, in ordine, fra cui cercare i prodotti."""
    famiglie: dict[tuple[str, ...], set[str]] = {}
    for percorso in _percorsi_interni(corpo, origine):
        forma = _forma_di(percorso)
        if forma is not None:
            famiglie.setdefault(forma, set()).add(percorso)

    ordinate = sorted(famiglie.items(), key=lambda kv: -len(kv[1]))
    return [(forma, membri) for forma, membri in ordinate if len(membri) >= minimo][:quante]


def punteggio_prodotto(corpo: str) -> int:
    """Quanto una pagina somiglia a una scheda prodotto.

    Serve a scegliere fra le famiglie di link candidate: quella i cui campioni
    sono davvero schede prodotto, non voci di menu. Contare i link non basta,
    perche' la navigazione di un sito grande e' quasi sempre piu' numerosa del
    catalogo mostrato in una pagina.
    """
    punti = 0
    if re.search(AVAILABLE_TRUE, corpo) or re.search(r'\\?"available\\?"\s*:\s*false', corpo):
        punti += 5
    for indizio, peso in (
        (r'"@type"\s*:\s*"Product"', 4),
        (r'og:type"?\s*content="product', 3),
        (r'itemprop="price"', 3),
        (r'\\?"price\\?"\s*:', 2),
        (r"aggiungi al carrello|add to cart", 2),
        (r'\\?"sku\\?"\s*:|itemprop="sku"', 2),
    ):
        if re.search(indizio, corpo, re.IGNORECASE):
            punti += peso
    return punti


# --------------------------------------------------------------------------- #
# Intero sito
# --------------------------------------------------------------------------- #

async def analizza_sito(client: PoliteClient, url: str) -> Esito:
    """Prova le strade possibili, dalla migliore alla peggiore."""
    origine = origine_di(url)
    esito = Esito(origine=origine, titolo=_nome_sito(origine))

    if not await client.allowed(origine + "/"):
        esito.problemi.append("Il robots.txt del sito vieta l'accesso automatico.")
        return esito

    # --- 1. Shopify in blocco: prodotti e disponibilita' in una sola risposta.
    risposta = await _prendi(client, f"{origine}/products.json?limit=250")
    if risposta is not None and risposta.status_code == 200:
        try:
            prodotti = risposta.json().get("products")
        except ValueError:
            prodotti = None

        if isinstance(prodotti, list) and prodotti:
            esito.piattaforma = "Shopify"
            esito.prodotti = len(prodotti)
            pagine = 1

            # Se la prima pagina e' piena il catalogo continua: si sfoglia.
            if len(prodotti) >= 250:
                pagine = 10
                esito.note.append(
                    "Catalogo grande: configurate 10 pagine, il monitor si ferma da solo "
                    "quando finiscono i prodotti."
                )

            esito.copertura = COMPLETA
            esito.metodo = "Elenco prodotti pubblico di Shopify"
            esito.note.append(
                f"{len(prodotti)} prodotti letti in una sola richiesta, con la "
                f"disponibilita' di ogni singola taglia."
            )
            esito.note.append("Rileva sia i restock sia i prodotti nuovi, su tutto il negozio.")
            esito.proposta = {
                "name": f"{esito.titolo} - tutto il sito",
                "type": "shopify_collection",
                "url": origine,
                "interval": 45,
                "notify": ["console", "desktop"],
                "options": {"pages": pagine} if pagine > 1 else {},
            }
            if not esito.proposta["options"]:
                del esito.proposta["options"]
            return esito

    esito.problemi.append(
        "L'elenco prodotti in blocco non e' accessibile"
        + (f" (HTTP {risposta.status_code})." if risposta is not None else " (nessuna risposta).")
    )

    # --- 2. Pagina di catalogo in HTML + apertura delle schede.
    #     Si prova per prima la pagina che l'utente ha indicato, se ne ha data una
    #     piu' specifica del dominio: e' quasi sempre quella giusta.
    percorso_dato = urlsplit(url if "://" in url else "https://" + url).path.rstrip("/")
    candidati = [percorso_dato] if percorso_dato not in ("", "/") else []
    candidati += ["/collections/all", "/", "/collections"]

    for percorso in dict.fromkeys(candidati):
        pagina = await _prendi(client, origine + percorso)
        if pagina is None or pagina.status_code != 200:
            continue

        corpo = pagina.text
        if "cdn.shopify.com" in corpo:
            esito.piattaforma = "Shopify"

        candidate = famiglie_candidate(corpo, origine)
        if not candidate:
            continue

        # Si apre un campione per famiglia e si tiene quella che somiglia
        # davvero a un catalogo di prodotti, non a un menu di categorie.
        valutate = []
        for forma, membri in candidate:
            campione = sorted(membri)[0]
            scheda = await _prendi(client, origine + campione)
            if scheda is None or scheda.status_code != 200:
                continue

            punti = punteggio_prodotto(scheda.text)

            # Una pagina di categoria somiglia a una scheda prodotto (ha prezzi,
            # immagini, pulsanti), ma si tradisce in un modo: dentro contiene
            # decine di link di un'ALTRA famiglia, cioe' i prodotti veri.
            interne = famiglie_candidate(scheda.text, origine, minimo=8, quante=1)
            e_elenco = bool(interne) and interne[0][0] != forma

            stock = bool(
                re.search(AVAILABLE_TRUE, scheda.text)
                or re.search(r'\\?"available\\?"\s*:\s*false', scheda.text)
            )
            valutate.append((forma, len(membri), punti, e_elenco, scheda, stock))

        if not valutate:
            continue

        # Ordine di preferenza: prima le famiglie dove lo stock e' leggibile
        # (sono quelle che permettono di avvisare dei restock, cioe' lo scopo),
        # poi le pagine finali rispetto agli elenchi, poi la somiglianza a una
        # scheda prodotto e infine la profondita' del percorso.
        valutate.sort(key=lambda v: (v[5], not v[3], v[2], len(v[0])), reverse=True)

        for forma_alt, quanti_alt, punti_alt, elenco_alt, _scheda_alt, stock_alt in valutate:
            pattern_alt, base_alt = _regex_da_forma(forma_alt, origine)
            esito.alternative.append(
                {
                    "etichetta": "/" + "/".join(forma_alt),
                    "quanti": quanti_alt,
                    "pattern": pattern_alt,
                    "base": base_alt,
                    "disponibilita": stock_alt,
                    "sembra_elenco": elenco_alt,
                }
            )

        forma, quanti, punti, _e_elenco, scheda, _stock = valutate[0]
        if punti < 2:
            continue
        pattern, base_link = _regex_da_forma(forma, origine)
        esito.prodotti = quanti
        primo = sorted(m for m in dict(candidate)[forma])[0]

        leggibile = bool(
            re.search(AVAILABLE_TRUE, scheda.text)
            or re.search(r'\\?"available\\?"\s*:\s*false', scheda.text)
        )

        proposta: dict[str, Any] = {
            "name": f"{esito.titolo} - tutto il sito",
            "type": "links",
            "url": origine + percorso,
            "interval": 60,
            "notify": ["console", "desktop"],
            "options": {"pattern": pattern, "base": base_link},
        }
        if primo.count("/"):
            # Lo slug contiene anche codici interni: si estrae un titolo leggibile.
            proposta["options"]["title_from"] = r"^([A-Za-z0-9\-]+?)(?:-[A-Za-z0-9]{8})?/"

        if leggibile:
            esito.copertura = COMPLETA
            esito.metodo = "Elenco in pagina + apertura delle schede prodotto"
            esito.note.append(f"{quanti} prodotti nell'elenco.")
            esito.note.append(
                "Il campo di disponibilita' e' presente nelle schede: il monitor le apre "
                "poche per giro, a rotazione, e riconosce disponibile da esaurito."
            )
            giri = max(1, -(-quanti // 5))
            esito.note.append(f"Copertura completa del catalogo in circa {giri} giri.")
            proposta["detail"] = {
                "in_stock_when": [AVAILABLE_TRUE],
                "regex": True,
                "max_checks": 5,
                "recheck_sold_out": True,
            }
        else:
            esito.copertura = PARZIALE
            esito.metodo = "Solo elenco: le schede non sono leggibili"
            esito.note.append(f"{quanti} prodotti nell'elenco.")
            esito.problemi.append(
                "Nelle schede prodotto non c'e' nessun campo di disponibilita' leggibile: "
                "il monitor puo' avvisarti dei prodotti NUOVI, non dei restock."
            )

        esito.proposta = proposta
        return esito

    # --- 3. Ultima spiaggia: la sitemap. Elenco si', disponibilita' no.
    sitemap = await _prendi(client, f"{origine}/sitemap.xml")
    if sitemap is not None and sitemap.status_code == 200 and "<loc>" in sitemap.text:
        indirizzi = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap.text)
        esito.prodotti = len(indirizzi)
        esito.copertura = PARZIALE
        esito.metodo = "Sitemap: l'unica superficie pubblica raggiungibile"
        esito.note.append(f"{len(indirizzi)} indirizzi nella sitemap.")
        esito.problemi.append(
            "Le pagine normali non rispondono alle richieste automatiche: si possono "
            "rilevare i prodotti nuovi, non i restock."
        )
        if len(indirizzi) > 2000:
            esito.problemi.append(
                "Sitemap molto grande: metti un filtro nel campo 'Tieni solo se contiene', "
                "altrimenti finiranno sotto osservazione migliaia di voci."
            )
        dominio = re.escape(origine)
        esito.proposta = {
            "name": f"{esito.titolo} - nuovi prodotti",
            "type": "links",
            "url": f"{origine}/sitemap.xml",
            "interval": 900,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": rf"<loc>\s*({dominio}/[^<\s]+)\s*</loc>",
                "limit": 3000,
            },
        }
        return esito

    esito.problemi.append(
        "Nessuna superficie pubblica leggibile: il sito risponde solo a un browser vero."
    )
    return esito


# --------------------------------------------------------------------------- #
# Singolo prodotto
# --------------------------------------------------------------------------- #

async def analizza_prodotto(client: PoliteClient, url: str) -> Esito:
    """Sceglie il modo migliore per seguire un solo prodotto."""
    origine = origine_di(url)
    pulito = url.split("?")[0].rstrip("/")
    esito = Esito(origine=origine, titolo=_nome_sito(origine))

    if not await client.allowed(pulito):
        esito.problemi.append("Il robots.txt del sito vieta l'accesso a questo indirizzo.")
        return esito

    nome_base = pulito.rsplit("/", 1)[-1].replace("-", " ")[:40] or esito.titolo

    # --- 1. Shopify: l'endpoint .js da' la disponibilita' taglia per taglia.
    if "/products/" in pulito:
        js = await _prendi(client, pulito + ".js")
        if js is not None and js.status_code == 200:
            try:
                varianti = js.json().get("variants")
            except ValueError:
                varianti = None
            if isinstance(varianti, list) and varianti:
                esito.piattaforma = "Shopify"
                esito.copertura = COMPLETA
                esito.metodo = "Endpoint prodotto di Shopify"
                esito.prodotti = len(varianti)
                esito.note.append(
                    f"{len(varianti)} varianti lette, ognuna con la propria disponibilita'."
                )
                esito.note.append("Puoi filtrare le taglie che ti interessano.")
                esito.proposta = {
                    "name": f"{esito.titolo} - {nome_base}",
                    "type": "shopify_product",
                    "url": pulito,
                    "interval": 30,
                    "notify": ["console", "desktop"],
                }
                return esito

    # --- 2. Pagina HTML con il campo di stock incorporato.
    pagina = await _prendi(client, pulito)
    if pagina is None:
        esito.problemi.append("La pagina non risponde.")
        return esito
    if pagina.status_code != 200:
        esito.problemi.append(
            f"La pagina risponde HTTP {pagina.status_code} alle richieste automatiche."
        )
        if "just a moment" in pagina.text.lower():
            esito.problemi.append(
                "E' una schermata di verifica anti-bot: nessuna configurazione la aggira."
            )
        return esito

    if re.search(AVAILABLE_TRUE, pagina.text) or re.search(r'\\?"available\\?"\s*:\s*false', pagina.text):
        esito.copertura = COMPLETA
        esito.metodo = "Campo di disponibilita' incorporato nella pagina"
        esito.note.append("Il monitor riconosce da solo disponibile ed esaurito.")
        esito.note.append("La rilevazione e' a livello di pagina, non di singola taglia.")
        esito.proposta = {
            "name": f"{esito.titolo} - {nome_base}",
            "type": "html",
            "url": pulito,
            "interval": 30,
            "notify": ["console", "desktop"],
            "options": {"in_stock_when": [AVAILABLE_TRUE], "regex": True},
        }
        return esito

    esito.copertura = PARZIALE
    esito.metodo = "Pagina leggibile, ma senza un campo di stato riconoscibile"
    esito.problemi.append(
        "La pagina si apre ma non contiene nessun campo di disponibilita' noto: "
        "probabilmente lo stock arriva via JavaScript."
    )
    esito.note.append(
        "Puoi comunque provare a mano: apri la pagina da esaurita, trova una frase "
        "presente solo in quel caso e mettila fra i marcatori di esaurito."
    )
    esito.proposta = {
        "name": f"{esito.titolo} - {nome_base}",
        "type": "html",
        "url": pulito,
        "interval": 30,
        "enabled": False,
        "notify": ["console", "desktop"],
        "options": {"out_of_stock_when": ["Esaurito", "Non disponibile"]},
    }
    return esito
