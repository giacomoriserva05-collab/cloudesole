#!/usr/bin/env python3
"""Toglie di mezzo i certificati di sviluppo creati dalle build in cloud.

Ogni compilazione firmata in cloud si crea un certificato nuovo, e Apple ne
ammette un numero limitato per account. Dopo una dozzina di build la firma
smette di funzionare con un messaggio che non dice cosa fare:

    Your account has reached the maximum number of certificates.

Quei certificati sono comunque inservibili: la chiave privata resta sulla
macchina usa-e-getta di GitHub, che dopo la build non esiste più. Toglierli è
solo fare spazio.

Tocca soltanto quelli di tipo DEVELOPMENT con nome "Created via API": un
certificato di distribuzione, o uno creato a mano da una persona con un Mac,
non viene sfiorato.

Vuole nell'ambiente ASC_KEY_ID, ASC_ISSUER_ID e ASC_KEY_PATH (il file .p8).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

BASE = "https://api.appstoreconnect.apple.com"


def _b64(dati: bytes) -> bytes:
    return base64.urlsafe_b64encode(dati).rstrip(b"=")


def gettone(key_id: str, issuer_id: str, percorso: str) -> str:
    """Un JWT ES256 buono un quarto d'ora."""
    with open(percorso, "rb") as f:
        chiave = serialization.load_pem_private_key(f.read(), password=None)
    testa = _b64(json.dumps({"alg": "ES256", "kid": key_id, "typ": "JWT"}).encode())
    ora = int(time.time())
    corpo = _b64(json.dumps({"iss": issuer_id, "iat": ora, "exp": ora + 900,
                             "aud": "appstoreconnect-v1"}).encode())
    da_firmare = testa + b"." + corpo
    r, s = utils.decode_dss_signature(chiave.sign(da_firmare, ec.ECDSA(hashes.SHA256())))
    firma = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return (da_firmare + b"." + firma).decode()


def chiama(metodo: str, percorso: str, gettone_: str):
    richiesta = urllib.request.Request(BASE + percorso, method=metodo)
    richiesta.add_header("Authorization", "Bearer " + gettone_)
    try:
        with urllib.request.urlopen(richiesta, timeout=30) as risposta:
            corpo = risposta.read()
            return risposta.status, json.loads(corpo) if corpo else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


def main() -> int:
    manca = [n for n in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH")
             if not os.environ.get(n)]
    if manca:
        print("Manca nell'ambiente:", ", ".join(manca), file=sys.stderr)
        return 1

    g = gettone(os.environ["ASC_KEY_ID"], os.environ["ASC_ISSUER_ID"],
                os.environ["ASC_KEY_PATH"])
    stato, dati = chiama("GET", "/v1/certificates?limit=200", g)
    if stato != 200 or not isinstance(dati, dict):
        print(f"Elenco non riuscito ({stato}): {dati}", file=sys.stderr)
        return 1

    da_togliere = [
        c for c in dati["data"]
        if (c["attributes"].get("certificateType") or "").startswith("DEVELOPMENT")
        and c["attributes"].get("displayName") == "Created via API"
    ]
    totale = len(dati["data"])
    if not da_togliere:
        print(f"{totale} certificati sull'account, nessuno da togliere.")
        return 0

    tolti = 0
    for c in da_togliere:
        stato, _ = chiama("DELETE", "/v1/certificates/" + c["id"], g)
        if stato in (200, 204):
            tolti += 1
        else:
            print(f"  {c['id']}: non revocato ({stato})", file=sys.stderr)
    print(f"{tolti} certificati di sviluppo revocati su {totale} totali.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
