"""Copia il motore dell'estensione Chrome dentro le risorse dell'app iOS.

Il riconoscimento dei campi e quello del carrello vivono in un posto solo:
`chrome-extension/`. Qui vengono adattati alla WKWebView, che non ha i moduli
ES né le API di Chrome. Da rieseguire ogni volta che si tocca l'estensione.

    python ios-app/tools/sync-js.py
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "chrome-extension"
DST = ROOT / "ios-app" / "CheckoutAutofill" / "Resources"

HEADER = (
    "// GENERATO da ios-app/tools/sync-js.py — non modificare a mano.\n"
    "// Sorgente: chrome-extension/{name}\n\n"
)


# Script classici che si espongono su globalThis: si copiano e basta.
DIRETTI = ["cartcore.js", "shopify.js"]


def copia(nome: str) -> str:
    testo = (SRC / nome).read_text(encoding="utf-8")
    return HEADER.format(name=nome) + testo


def adatta_filler() -> str:
    """filler.js esporta una funzione come modulo ES: qui diventa globale."""
    testo = (SRC / "filler.js").read_text(encoding="utf-8")
    if "export function autofillPage" not in testo:
        sys.exit("filler.js: manca 'export function autofillPage', formato inatteso")
    testo = testo.replace("export function autofillPage", "function autofillPage", 1)
    coda = (
        "\n\n// Aggancio per l'app iOS: il ponte chiama questa funzione.\n"
        "globalThis.__CA_FILL = autofillPage;\n"
    )
    return HEADER.format(name="filler.js") + testo + coda


def senza_commenti(testo: str) -> str:
    testo = re.sub(r"/\*.*?\*/", "", testo, flags=re.S)
    return "\n".join(r for r in testo.splitlines() if not r.lstrip().startswith("//"))


def controlla(testo: str, nome: str) -> None:
    """Difese contro un adattamento silenziosamente rotto."""
    codice = senza_commenti(testo)
    if re.search(r"^\s*(import|export)\s", codice, re.M):
        sys.exit(f"{nome}: sono rimasti import/export, non gira in una WKWebView")
    if "chrome." in codice:
        sys.exit(f"{nome}: usa ancora le API di Chrome, che su iOS non esistono")


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    lavori = {n: copia(n) for n in DIRETTI}
    lavori["filler.js"] = adatta_filler()
    for nome, testo in lavori.items():
        controlla(testo, nome)
        (DST / nome).write_text(testo, encoding="utf-8", newline="\n")
        print(f"scritto {nome}  ({len(testo.splitlines())} righe)")

    # Scritti a mano, non generati: qui si controlla solo che ci siano.
    for nome in ("bridge.js", "login.js"):
        f = DST / nome
        if not f.exists():
            sys.exit(f"manca {nome}: è scritto a mano, non generato")
        print(f"presente {nome} ({len(f.read_text(encoding='utf-8').splitlines())} righe)")


if __name__ == "__main__":
    main()
