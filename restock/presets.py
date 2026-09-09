"""Configurazioni pronte per siti specifici.

Ogni preset e' stato verificato interrogando davvero il sito: robots.txt,
accessibilita' della pagina e marcatori di disponibilita'. I limiti indicati in
'caveat' non sono prudenza generica, sono cio' che il sito fa realmente.

Verifica effettuata il 07/09/2026. Se un sito cambia impaginazione o politica di
accesso, il preset va ricontrollato: usa 'Prova adesso' per accorgertene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Preset:
    key: str
    site: str
    name: str
    summary: str
    detail: str
    target: dict[str, Any]
    caveat: str = ""
    needs_edit: str = ""
    tested: str = ""


# Marcatore di disponibilita' usato da Shopify e da Nike: il campo "available"
# dentro al JSON incorporato nella pagina. Il backslash e' opzionale perche' su
# alcuni siti il JSON e' annidato dentro una stringa e le virgolette sono
# sfuggite (\"available\") mentre su altri no ("available").
AVAILABLE_TRUE = r'\\?"available\\?"\s*:\s*true'


PRESETS: list[Preset] = [

    # ----------------------------------------------------------------- #
    # Travis Scott - shop.travisscott.com (Shopify dietro Cloudflare)
    # ----------------------------------------------------------------- #
    Preset(
        key="travis-nuovi",
        site="Travis Scott",
        name="Travis Scott - nuovi prodotti nello shop",
        summary="Avvisa quando compare un prodotto nuovo su shop.travisscott.com.",
        detail=(
            "Legge la pagina della collezione completa ed estrae l'elenco dei prodotti,\n"
            "poi apre le singole schede per capire quali sono davvero acquistabili.\n\n"
            "Ricevi un avviso quando compare un prodotto nuovo (dicendoti se e' gia'\n"
            "disponibile o gia' esaurito) e quando uno che era esaurito torna comprabile.\n\n"
            "E' il preset piu' completo: copre l'intero store senza doverne configurare\n"
            "uno per prodotto."
        ),
        caveat=(
            "Le schede vengono aperte poche per giro, a rotazione: su un prodotto\n"
            "gia' noto ed esaurito il restock puo' arrivare con qualche minuto di ritardo\n"
            "rispetto a un target dedicato a quel singolo prodotto.\n\n"
            "La disponibilita' e' a livello di pagina, non di singola taglia."
        ),
        tested=(
            "Collezione: HTTP 200, 26 prodotti. Marcatore provato su 6 schede reali:\n"
            "separa correttamente esaurito e disponibile."
        ),
        target={
            "name": "Travis Scott - nuovi prodotti",
            "type": "links",
            "url": "https://shop.travisscott.com/collections/all",
            "interval": 60,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": r"/products/([a-z0-9][a-z0-9\-]{2,60})",
                "base": "https://shop.travisscott.com/products/",
            },
            "detail": {
                "in_stock_when": [AVAILABLE_TRUE],
                "regex": True,
                "max_checks": 5,
                "recheck_sold_out": True,
            },
        },
    ),

    Preset(
        key="travis-prodotto",
        site="Travis Scott",
        name="Travis Scott - disponibilita' di un prodotto",
        summary="Segue un singolo prodotto e avvisa quando torna disponibile.",
        detail=(
            "Legge la pagina del prodotto e cerca nel codice della pagina il campo di\n"
            "disponibilita' che Shopify vi incorpora.\n\n"
            "Marcatore verificato su prodotti reali: sulla pagina esaurita compare 24\n"
            "volte \"available\":false e mai \"available\":true; sulle pagine dei prodotti\n"
            "disponibili e' l'esatto contrario."
        ),
        caveat=(
            "La rilevazione e' a livello di pagina, non di singola taglia: sai che\n"
            "qualcosa e' tornato disponibile, non quale taglia."
        ),
        needs_edit=(
            "Sostituisci l'URL con quello del prodotto che ti interessa.\n"
            "Nasce disattivato apposta: com'e' adesso l'indirizzo e' un segnaposto e\n"
            "darebbe errore. Modificalo, poi attivalo con 'Attiva / Disattiva'."
        ),
        tested="6 pagine prodotto provate: il marcatore separa correttamente esaurito e disponibile.",
        target={
            "name": "Travis Scott - prodotto da seguire",
            "type": "html",
            "url": "https://shop.travisscott.com/products/CAMBIA-QUESTO-HANDLE",
            "interval": 60,
            "enabled": False,
            "notify": ["console", "desktop"],
            "options": {
                "regex": True,
                "in_stock_when": [r"\"available\"\s*:\s*true"],
            },
        },
    ),

    # ----------------------------------------------------------------- #
    # Nike SNKRS - www.nike.com/it/launch
    # ----------------------------------------------------------------- #
    Preset(
        key="snkrs-instock",
        site="Nike SNKRS",
        name="Nike SNKRS Italia - appena disponibili",
        summary="Avvisa quando un lancio entra nella sezione 'disponibili' di SNKRS.",
        detail=(
            "Legge la pagina dei lanci gia' acquistabili ed estrae l'elenco.\n"
            "Quando ne compare uno nuovo, ricevi l'avviso con il link alla pagina SNKRS.\n\n"
            "E' il segnale che conta per un rilascio a disponibilita' immediata: ti dice\n"
            "che il prodotto e' passato da 'in arrivo' ad 'acquistabile'."
        ),
        caveat=(
            "In Europa la maggior parte dei lanci SNKRS sono ESTRAZIONI, non vendite a\n"
            "chi arriva prima: si partecipa dall'app entro una finestra e poi si aspetta\n"
            "l'esito. Su quei drop il monitor ti dice quando la finestra si apre, ma non\n"
            "esiste nessun 'arrivare primi' che si possa vincere.\n\n"
            "'Disponibile' qui significa che almeno una taglia risulta acquistabile,\n"
            "non necessariamente la tua.\n\n"
            "Per cambiare paese sostituisci /it/ nell'URL con un altro codice (es. /fr/)."
        ),
        tested=(
            "HTTP 200, robots.txt consente /it/launch, 15 lanci letti.\n"
            "Sulle schede dei lanci il campo di disponibilita' per taglia e' presente\n"
            "e distingue: su un lancio provato 16 taglie disponibili e 8 esaurite."
        ),
        target={
            "name": "SNKRS IT - appena disponibili",
            "type": "links",
            "url": "https://www.nike.com/it/launch/in-stock",
            "interval": 90,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": r"/it/launch/t/([a-z0-9\-]{4,90})",
                "base": "https://www.nike.com/it/launch/t/",
            },
            "detail": {
                "in_stock_when": [AVAILABLE_TRUE],
                "regex": True,
                "max_checks": 4,
                "recheck_sold_out": True,
            },
        },
    ),

    Preset(
        key="snkrs-upcoming",
        site="Nike SNKRS",
        name="Nike SNKRS Italia - nuovi lanci annunciati",
        summary="Avvisa quando Nike annuncia un lancio che prima non c'era.",
        detail=(
            "Come il preset precedente ma sulla pagina dei lanci in arrivo: serve a\n"
            "sapere in anticipo cosa e' stato messo in calendario, con giorni di margine\n"
            "per organizzarsi."
        ),
        caveat="Intervallo lungo di proposito: il calendario cambia poche volte al giorno.",
        tested="HTTP 200, 4 lanci in calendario letti correttamente.",
        target={
            "name": "SNKRS IT - nuovi lanci annunciati",
            "type": "links",
            "url": "https://www.nike.com/it/launch/upcoming",
            "interval": 300,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": r"/it/launch/t/([a-z0-9\-]{4,90})",
                "base": "https://www.nike.com/it/launch/t/",
            },
        },
    ),

    # ----------------------------------------------------------------- #
    # Nike.com - sito normale, non SNKRS
    # ----------------------------------------------------------------- #
    Preset(
        key="nike-novita",
        site="Nike.com",
        name="Nike.com Italia - novita'",
        summary="Avvisa quando compare un prodotto nuovo nella sezione Novita'.",
        detail=(
            "Sorveglia la pagina Novita' del sito Nike normale (non SNKRS) ed estrae\n"
            "l'elenco dei prodotti. Quando ne compare uno che prima non c'era, ricevi\n"
            "l'avviso con il link alla scheda.\n\n"
            "E' il canale delle uscite ordinarie, quelle che non passano da SNKRS e non\n"
            "sono soggette a estrazione: qui chi arriva prima compra davvero."
        ),
        caveat=(
            "Segnala i prodotti NUOVI a catalogo, senza dire se sono acquistabili.\n\n"
            "E' l'unico dei preset che non riesce a distinguere disponibile da esaurito:\n"
            "sulle schede prodotto di nike.com taglie e stock arrivano via JavaScript, che\n"
            "questo strumento non esegue, e nell'HTML non c'e' nessun campo di stato. Su\n"
            "Travis Scott e SNKRS invece il controllo automatico c'e' e funziona."
        ),
        tested="HTTP 200, robots.txt consente /it/w/ e /it/t/, 33 prodotti letti.",
        target={
            "name": "Nike.com IT - novita",
            "type": "links",
            "url": "https://www.nike.com/it/w/novita-3n82y",
            "interval": 180,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": r"/it/t/([A-Za-z0-9\-]{4,90}/[A-Z0-9\-]{4,20})",
                "base": "https://www.nike.com/it/t/",
                "title_from": r"^([A-Za-z0-9\-]+?)(?:-[A-Za-z0-9]{8})?/",
            },
        },
    ),

    Preset(
        key="nike-saldi",
        site="Nike.com",
        name="Nike.com Italia - saldi",
        summary="Avvisa quando un prodotto entra nella sezione Saldi.",
        detail=(
            "Stessa logica della sezione Novita', puntata sui saldi: l'avviso arriva\n"
            "quando un prodotto viene messo in sconto e compare nell'elenco."
        ),
        caveat="Segnala l'ingresso nell'elenco, non la variazione di prezzo di chi c'e' gia'.",
        tested="HTTP 200, 33 prodotti letti.",
        target={
            "name": "Nike.com IT - saldi",
            "type": "links",
            "url": "https://www.nike.com/it/w/saldi-3yaep",
            "interval": 300,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": r"/it/t/([A-Za-z0-9\-]{4,90}/[A-Z0-9\-]{4,20})",
                "base": "https://www.nike.com/it/t/",
                "title_from": r"^([A-Za-z0-9\-]+?)(?:-[A-Za-z0-9]{8})?/",
            },
        },
    ),

    Preset(
        key="nike-categoria",
        site="Nike.com",
        name="Nike.com Italia - una categoria a scelta",
        summary="Sorveglia una qualsiasi pagina di catalogo Nike.",
        detail=(
            "Come i due preset precedenti, ma con l'indirizzo da scegliere tu.\n\n"
            "Vai su nike.com, applica i filtri che vuoi (uomo, scarpe, un modello, una\n"
            "taglia) e copia l'indirizzo dalla barra del browser: qualsiasi pagina che\n"
            "comincia con nike.com/it/w/ va bene.\n\n"
            "Cosi' puoi restringere il campo a cio' che ti interessa davvero invece di\n"
            "ricevere l'intero catalogo."
        ),
        caveat="Le pagine di catalogo pesano circa 1 MB: non scendere sotto i 2-3 minuti.",
        needs_edit="Sostituisci l'indirizzo con la pagina di catalogo che ti interessa.",
        tested="Provato su 'uomo scarpe' e 'donna scarpe': HTTP 200, 106 prodotti ciascuna.",
        target={
            "name": "Nike.com IT - categoria",
            "type": "links",
            "url": "https://www.nike.com/it/w/uomo-scarpe-nik1zy7ok",
            "interval": 300,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": r"/it/t/([A-Za-z0-9\-]{4,90}/[A-Z0-9\-]{4,20})",
                "base": "https://www.nike.com/it/t/",
                "title_from": r"^([A-Za-z0-9\-]+?)(?:-[A-Za-z0-9]{8})?/",
            },
        },
    ),

    # ----------------------------------------------------------------- #
    # GameLife - www.gamelife.it
    # ----------------------------------------------------------------- #
    Preset(
        key="gamelife-nuovi",
        site="GameLife",
        name="GameLife - nuovi prodotti a catalogo",
        summary="Avvisa quando GameLife pubblica un prodotto nuovo (filtrato per parola).",
        detail=(
            "GameLife risponde 403 alle richieste automatiche sulle pagine normali:\n"
            "l'unica superficie pubblica accessibile e' la sitemap, che il sito serve\n"
            "regolarmente perche' e' fatta apposta per essere letta dai programmi.\n\n"
            "Il preset la legge e ti avvisa quando compare un prodotto nuovo che\n"
            "corrisponde al filtro. Su un negozio come questo e' il segnale piu' utile:\n"
            "i preordini dei set nuovi si esauriscono nelle prime ore."
        ),
        caveat=(
            "Rileva i prodotti NUOVI a catalogo, senza dire se sono acquistabili: le\n"
            "schede prodotto rispondono 403 alle richieste automatiche, quindi non c'e'\n"
            "modo di aprirle per accertare lo stock.\n\n"
            "Il filtro e' obbligatorio nei fatti: la sitemap contiene circa 30.000 URL,\n"
            "senza filtro finirebbero tutti sotto osservazione. Il valore predefinito e'\n"
            "'pokemon' (1.297 prodotti); cambialo con quello che ti interessa.\n\n"
            "La sitemap pesa circa 3 MB: l'intervallo di 15 minuti e' scelto per non\n"
            "scaricarla di continuo."
        ),
        needs_edit="Cambia il filtro 'include' con la parola che ti interessa.",
        tested="Sitemap: HTTP 200, 30.858 URL, 1.297 corrispondenze per 'pokemon'.",
        target={
            "name": "GameLife - nuovi prodotti",
            "type": "links",
            "url": "https://www.gamelife.it/sitemap.xml",
            "interval": 900,
            "notify": ["console", "desktop"],
            "options": {
                "pattern": r"<loc>\s*(https://www\.gamelife\.it/[^<\s]+)\s*</loc>",
                "include": ["pokemon"],
                "limit": 3000,
            },
        },
    ),
]


def by_site() -> dict[str, list[Preset]]:
    """Preset raggruppati per sito, nell'ordine di definizione."""
    grouped: dict[str, list[Preset]] = {}
    for preset in PRESETS:
        grouped.setdefault(preset.site, []).append(preset)
    return grouped


def get(key: str) -> Preset | None:
    return next((p for p in PRESETS if p.key == key), None)


def instantiate(preset: Preset, existing_names: set[str]) -> dict[str, Any]:
    """Copia profonda del target, con il nome reso univoco se serve."""
    import copy

    target = copy.deepcopy(preset.target)
    base = str(target.get("name", preset.name))
    name, counter = base, 2
    while name in existing_names:
        name = f"{base} {counter}"
        counter += 1
    target["name"] = name
    return target
