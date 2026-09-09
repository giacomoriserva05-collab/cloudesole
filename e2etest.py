r"""Prova end-to-end: monta un finto store Shopify in locale e ci fa girare
contro il monitor completo (client HTTP, robots.txt, adapter, stato, notifiche).

Uso:  .venv\Scripts\python.exe e2etest.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8931
PROJECT = Path(__file__).resolve().parent
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"

sys.path.insert(0, str(PROJECT))
from restock.presets import AVAILABLE_TRUE  # noqa: E402

STATE = {
    "available": False,
    "hits": 0,
    "extra_launch": False,
    # Catalogo con schede prodotto, per provare l'accertamento della disponibilita'.
    "catalogo_extra": False,
    "stock": {"uno": True, "due": False, "tre": False},
    "schede_aperte": [],
    "pagine_chieste": [],
}

ROBOTS = "User-agent: *\nAllow: /\nDisallow: /vietato\n"

# Nomi veri dei prodotti: stanno solo sulle schede, non sono ricavabili dallo
# slug dell'indirizzo. E' il caso di Supreme.
NOMI_PRODOTTI = {"uno": "Felpa Rossa", "due": "Giacca Blu", "tre": "Scarpa Verde"}


def product_payload() -> dict:
    return {
        "title": "Sneaker X",
        "handle": "sneaker-x",
        "variants": [
            {"id": 1, "public_title": "42", "available": False, "price": 12900},
            {"id": 2, "public_title": "43", "available": STATE["available"], "price": 12900},
        ],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        path, _, query = self.path.partition("?")
        parametri = dict(p.split("=", 1) for p in query.split("&") if "=" in p)

        if path == "/robots.txt":
            body = ROBOTS.encode()
            ctype = "text/plain"
        elif path == "/products/sneaker-x.js":
            STATE["hits"] += 1
            body = json.dumps(product_payload()).encode()
            ctype = "application/json"
        elif path == "/vietato/prodotto.js":
            body = json.dumps(product_payload()).encode()
            ctype = "application/json"
        elif path == "/lanci":
            links = ['<a href="/t/air-max-uno">A</a>', '<a href="/t/dunk-due">B</a>']
            if STATE["extra_launch"]:
                links.append('<a href="/t/jordan-tre">C</a>')
            body = ("<html><body>" + "".join(links) + "</body></html>").encode()
            ctype = "text/html"
        elif path in ("/products.json", "/collections/all/products.json"):
            # Catalogo sfogliabile: due pagine piene, poi il vuoto.
            pagina = int(parametri.get("page", "1"))
            catalogo = {
                1: [("alfa", 101), ("beta", 102)],
                2: [("gamma", 103)],
            }.get(pagina, [])
            STATE["pagine_chieste"].append(pagina)
            body = json.dumps(
                {
                    "products": [
                        {
                            "title": nome,
                            "handle": nome,
                            "variants": [
                                {"id": vid, "title": "42", "available": True, "price": "10.00"}
                            ],
                        }
                        for nome, vid in catalogo
                    ]
                }
            ).encode()
            ctype = "application/json"
        elif path == "/catalogo":
            slugs = ["uno", "due"] + (["tre"] if STATE["catalogo_extra"] else [])
            links = "".join(f'<a href="/prod/{s}">{s}</a>' for s in slugs)
            body = f"<html><body>{links}</body></html>".encode()
            ctype = "text/html"
        elif path.startswith("/prod/"):
            slug = path.rsplit("/", 1)[-1]
            if slug not in STATE["stock"]:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            STATE["schede_aperte"].append(slug)
            stato = "true" if STATE["stock"][slug] else "false"
            nome = NOMI_PRODOTTI[slug]
            body = (
                f"<html><head><title>{nome} - Shop - FintoStore</title></head>"
                f"<body><h1>{nome}</h1>"
                f'<script>{{"available":{stato}}}</script></body></html>'
            ).encode()
            ctype = "text/html"
        elif path == "/lento.js":
            self.send_response(429)
            self.send_header("Retry-After", "120")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def write_config(directory: Path, targets: str) -> Path:
    path = directory / "config.yaml"
    path.write_text(
        "defaults:\n"
        "  interval: 5\n"
        "  jitter: 0\n"
        "  user_agent: \"RestockMonitor/1.0 (test locale)\"\n"
        "  respect_robots: true\n"
        "  notify: [console]\n"
        "notifiers:\n"
        "  console:\n"
        "    enabled: true\n"
        "  desktop:\n"
        "    enabled: false\n"
        f"targets:\n{targets}",
        encoding="utf-8",
    )
    return path


def run(config_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PYTHON), "-m", "restock", "-c", str(config_path), "--once"],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def show(label: str, result: subprocess.CompletedProcess) -> None:
    print(f"\n----- {label} (exit={result.returncode}) -----")
    print((result.stdout or "").strip())
    if result.stderr.strip():
        print("[stderr]", result.stderr.strip())


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        base = f"http://127.0.0.1:{PORT}"

        cfg = write_config(
            tmpdir,
            f"  - name: Store Locale - Sneaker X\n"
            f"    type: shopify_product\n"
            f"    url: {base}/products/sneaker-x\n",
        )

        # 1. Primo giro: acquisisce lo stato, non deve notificare.
        first = run(cfg)
        show("giro 1 - stato iniziale, taglia 43 esaurita", first)
        if first.returncode != 0:
            failures.append("il primo giro doveva uscire con 0")
        if "RESTOCK" in first.stdout:
            failures.append("il primo giro non doveva notificare")
        if "2 articoli" not in first.stdout:
            failures.append("attese 2 varianti lette")

        # 2. Nessun cambiamento: silenzio.
        second = run(cfg)
        show("giro 2 - nessun cambiamento", second)
        if "RESTOCK" in second.stdout:
            failures.append("nessuna notifica attesa senza cambiamenti")

        # 3. La taglia 43 torna disponibile: deve scattare il restock.
        STATE["available"] = True
        third = run(cfg)
        show("giro 3 - la taglia 43 torna disponibile", third)
        if "RESTOCK" not in third.stdout:
            failures.append("atteso un evento RESTOCK")
        if "Sneaker X - 43" not in third.stdout:
            failures.append("la notifica doveva citare la variante 43")
        if "?variant=2" not in third.stdout:
            failures.append("la notifica doveva contenere il link diretto alla variante")

        # 4. Ancora disponibile: non si riavvisa.
        fourth = run(cfg)
        show("giro 4 - ancora disponibile, niente doppioni", fourth)
        if "RESTOCK" in fourth.stdout:
            failures.append("notifica duplicata su articolo gia' segnalato")

        # 5. robots.txt: il target vietato va disattivato.
        blocked_dir = tmpdir / "b"
        blocked_dir.mkdir()
        blocked_cfg = write_config(
            blocked_dir,
            f"  - name: Percorso Vietato\n"
            f"    type: shopify_product\n"
            f"    url: {base}/vietato/prodotto\n",
        )
        blocked = run(blocked_cfg)
        show("giro 5 - URL vietato da robots.txt", blocked)
        if "robots.txt" not in (blocked.stdout + blocked.stderr):
            failures.append("il blocco da robots.txt doveva essere segnalato")
        if blocked.returncode == 0:
            failures.append("un target bloccato deve produrre exit code diverso da 0")

        # 6. Filtro sulle taglie.
        filtered_dir = tmpdir / "f"
        filtered_dir.mkdir()
        filtered_cfg = write_config(
            filtered_dir,
            f"  - name: Solo 42\n"
            f"    type: shopify_product\n"
            f"    url: {base}/products/sneaker-x\n"
            f"    match:\n"
            f"      variants: [\"42\"]\n",
        )
        filtered = run(filtered_cfg)
        show("giro 6 - filtro sulle taglie (solo 42)", filtered)
        if "1 articoli" not in filtered.stdout:
            failures.append("il filtro doveva restituire una sola variante")

        # 7. Risposta 429: l'host va in pausa senza far crollare il monitor.
        cooldown_dir = tmpdir / "c"
        cooldown_dir.mkdir()
        cooldown_cfg = write_config(
            cooldown_dir,
            f"  - name: Host Rate-Limitato\n"
            f"    type: json\n"
            f"    url: {base}/lento.js\n"
            f"    options:\n"
            f"      available_path: available\n",
        )
        cooldown = run(cooldown_cfg)
        show("giro 7 - il server risponde 429", cooldown)
        combined = cooldown.stdout + cooldown.stderr
        if "429" not in combined:
            failures.append("il 429 doveva comparire nei log")
        if "120" not in combined:
            failures.append("il monitor doveva rispettare Retry-After: 120")

        # 8. Elenco di link: un lancio nuovo che compare deve produrre un avviso.
        links_dir = tmpdir / "l"
        links_dir.mkdir()
        links_cfg = write_config(
            links_dir,
            f"  - name: Lanci\n"
            f"    type: links\n"
            f"    url: {base}/lanci\n"
            f"    options:\n"
            f"      pattern: '/t/([a-z0-9\\-]+)'\n"
            f"      base: '{base}/t/'\n",
        )

        seed = run(links_cfg)
        show("giro 8a - elenco lanci, stato iniziale", seed)
        if "2 articoli" not in seed.stdout:
            failures.append("l'elenco doveva contenere 2 lanci")
        if "NUOVO" in seed.stdout:
            failures.append("il primo giro sull'elenco non doveva notificare")

        STATE["extra_launch"] = True
        appeared = run(links_cfg)
        show("giro 8b - compare un lancio nuovo", appeared)
        if "NUOVO" not in appeared.stdout:
            failures.append("la comparsa di un lancio doveva produrre un evento NUOVO")
        if "jordan tre" not in appeared.stdout:
            failures.append("l'avviso doveva citare il lancio appena comparso")
        if f"{base}/t/jordan-tre" not in appeared.stdout:
            failures.append("l'avviso doveva contenere il link al nuovo lancio")

        again = run(links_cfg)
        show("giro 8c - nessun doppione sul lancio gia' visto", again)
        if "NUOVO" in again.stdout:
            failures.append("un lancio gia' segnalato non va rinotificato")

        # 9. Elenco + accertamento della disponibilita' sulle schede prodotto.
        detail_dir = tmpdir / "d"
        detail_dir.mkdir()
        detail_cfg = write_config(
            detail_dir,
            f"  - name: Catalogo\n"
            f"    type: links\n"
            f"    url: {base}/catalogo\n"
            f"    options:\n"
            f"      pattern: '/prod/([a-z]+)'\n"
            f"      base: '{base}/prod/'\n"
            f"    detail:\n"
            # json.dumps produce uno scalare fra virgolette valido anche in YAML,
            # evitando di riscrivere a mano le sequenze di escape della regex.
            f"      in_stock_when: [{json.dumps(AVAILABLE_TRUE)}]\n"
            f"      regex: true\n"
            f"      max_checks: 5\n"
            f"      recheck_sold_out: true\n",
        )

        STATE["schede_aperte"].clear()
        seed = run(detail_cfg)
        show("giro 9a - catalogo, stato iniziale con accertamento", seed)
        if "2 articoli, 1/2 disponibili fra quelli accertati" not in seed.stdout:
            failures.append("l'accertamento doveva trovare 1 disponibile su 2, entrambi verificati")
        if "ancora da accertare" in seed.stdout:
            failures.append("con 2 articoli e un tetto di 5 non doveva restare nulla da accertare")
        if set(STATE["schede_aperte"]) != {"uno", "due"}:
            failures.append(f"schede aperte inattese: {STATE['schede_aperte']}")
        if "NUOVO" in seed.stdout:
            failures.append("il primo giro non doveva notificare")

        # Compare un prodotto nuovo, gia' esaurito.
        STATE["catalogo_extra"] = True
        nuovo = run(detail_cfg)
        show("giro 9b - prodotto nuovo, gia' esaurito", nuovo)
        if "NUOVO" not in nuovo.stdout:
            failures.append("la comparsa di un prodotto doveva essere segnalata")
        if "ESAURITO" not in nuovo.stdout:
            failures.append("l'avviso doveva dichiarare che il prodotto e' esaurito")
        if "Scarpa Verde" not in nuovo.stdout:
            failures.append("l'avviso doveva usare il nome del prodotto, non lo slug")
        if "] tre [" in nuovo.stdout:
            failures.append("l'avviso mostra ancora lo slug al posto del nome")

        # Il prodotto esaurito torna disponibile.
        STATE["stock"]["tre"] = True
        restock = run(detail_cfg)
        show("giro 9c - il prodotto esaurito torna disponibile", restock)
        if "RESTOCK" not in restock.stdout:
            failures.append("il ritorno in disponibilita' doveva produrre un RESTOCK")
        if "ESAURITO" in restock.stdout:
            failures.append("un restock non deve portarsi dietro l'etichetta ESAURITO")

        # Nessun cambiamento: niente doppioni.
        fermo = run(detail_cfg)
        show("giro 9d - nessun cambiamento", fermo)
        if "RESTOCK" in fermo.stdout or "NUOVO" in fermo.stdout:
            failures.append("nessun avviso atteso senza cambiamenti")

        # Anche 'due' era esaurito: la rotazione deve accorgersi del suo restock.
        STATE["stock"]["due"] = True
        recupero = run(detail_cfg)
        show("giro 9e - restock di un prodotto gia' noto ed esaurito", recupero)
        if "RESTOCK" not in recupero.stdout or "Giacca Blu" not in recupero.stdout:
            failures.append("il ricontrollo degli esauriti non ha rilevato il restock col nome giusto")

        # 10. Paginazione: il catalogo va coperto tutto, non solo la prima pagina.
        pag_dir = tmpdir / "p"
        pag_dir.mkdir()
        pag_cfg = write_config(
            pag_dir,
            f"  - name: Catalogo intero\n"
            f"    type: shopify_collection\n"
            f"    url: {base}/collections/all\n"
            f"    options:\n"
            f"      pages: 5\n",
        )

        STATE["pagine_chieste"].clear()
        paginato = run(pag_cfg)
        show("giro 10 - catalogo su piu' pagine", paginato)
        if "3 articoli" not in paginato.stdout:
            failures.append("le due pagine piene dovevano dare 3 articoli in tutto")
        if STATE["pagine_chieste"][:3] != [1, 2, 3]:
            failures.append(f"pagine chieste inattese: {STATE['pagine_chieste']}")
        if len(STATE["pagine_chieste"]) > 3:
            failures.append(
                f"doveva fermarsi alla prima pagina vuota, invece ne ha chieste "
                f"{len(STATE['pagine_chieste'])}"
            )

        # 11. L'analizzatore riconosce il sito e propone una configurazione valida.
        import asyncio as _asyncio

        from restock import config as _config
        from restock import discover
        from restock.httpclient import PoliteClient

        async def _analizza():
            async with PoliteClient("RestockMonitor/1.0 (test locale)", respect_robots=True) as c:
                return await discover.analizza_sito(c, base)

        esito = _asyncio.run(_analizza())
        print(f"\n----- giro 11 - analisi automatica del sito -----")
        print(f"  piattaforma : {esito.piattaforma}")
        print(f"  copertura   : {esito.copertura}")
        print(f"  metodo      : {esito.metodo}")
        print(f"  prodotti    : {esito.prodotti}")
        for nota in esito.note:
            print(f"  nota        : {nota}")

        if esito.piattaforma != "Shopify":
            failures.append(f"l'analizzatore doveva riconoscere Shopify, ha detto {esito.piattaforma}")
        if esito.copertura != discover.COMPLETA:
            failures.append(f"copertura attesa completa, ottenuta {esito.copertura}")
        if not esito.proposta:
            failures.append("l'analisi doveva produrre una configurazione")
        else:
            an_dir = tmpdir / "a"
            an_dir.mkdir()
            an_path = an_dir / "config.yaml"
            _config.save_raw(
                an_path,
                {"defaults": {}, "notifiers": {"console": {"enabled": True}}, "targets": [esito.proposta]},
            )
            try:
                _config.load(an_path)
            except _config.ConfigError as exc:
                failures.append(f"la configurazione proposta non e' valida: {exc}")

            prova = run(an_path)
            show("giro 11b - la configurazione proposta funziona davvero", prova)
            if prova.returncode != 0 or "[OK]" not in prova.stdout:
                failures.append("il target proposto dall'analisi non ha funzionato")

    server.shutdown()

    print(f"\nRichieste ricevute dal finto store: {STATE['hits']}")
    print("=" * 60)
    if failures:
        print(f"{len(failures)} CONTROLLI FALLITI:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli end-to-end superati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
