"""Notifiche push verso l'iPhone, direttamente dal monitor.

È il pezzo che chiude il cerchio: l'app su iOS non può interrogare i siti a
telefono chiuso — il sistema la sospende in pochi secondi — mentre questo
monitor gira già ventiquattr'ore su un computer acceso. Quindi è lui a
mandare la notifica, passando dai server di Apple.

Non serve un server: il monitor *è* il server. Toccando la notifica l'app si
apre sulla pagina del prodotto, perché l'indirizzo viaggia dentro il messaggio.

Cosa serve nella configurazione:

    apns:
      enabled: true
      key_file: AuthKey_XXXXXXXXXX.p8   # chiave APNs, non quella di App Store
      key_id: XXXXXXXXXX
      team_id: M2AY2QTFV7
      topic: com.giacomoriserva.checkoutautofill
      devices:
        - <codice del telefono, dalla scheda Monitor dell'app>

La chiave APNs si crea su developer.apple.com in Certificates, Identifiers &
Profiles → Keys → Apple Push Notifications service (APNs). È diversa da quella
di App Store Connect, e vale per tutte le app della squadra.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

PRODUZIONE = "https://api.push.apple.com"
SVILUPPO = "https://api.sandbox.push.apple.com"

# Il token JWT vale un'ora; Apple rifiuta quelli piu' vecchi di sessanta
# minuti e sgrida chi ne genera uno a ogni messaggio. Si riusa.
_DURATA_TOKEN = 45 * 60


class ApnsError(RuntimeError):
    """Configurazione mancante o rifiuto da parte di Apple."""


class ApnsClient:
    """Parla con Apple. Tiene in caldo il token JWT e la connessione HTTP/2."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.key_file = str(config.get("key_file") or "").strip()
        self.key_id = str(config.get("key_id") or "").strip()
        self.team_id = str(config.get("team_id") or "").strip()
        self.topic = str(config.get("topic") or "").strip()
        self.devices = [str(d).strip() for d in (config.get("devices") or []) if str(d).strip()]
        self.sandbox = bool(config.get("sandbox", False))

        self._token: str | None = None
        self._token_nato: float = 0.0
        self._client: httpx.AsyncClient | None = None

    # ----------------------------------------------------------------- setup

    def manca(self) -> str | None:
        """Cosa impedisce di mandare, in una frase leggibile."""
        if not self.key_file:
            return "manca il percorso della chiave APNs (.p8)."
        if not Path(self.key_file).exists():
            return f"la chiave APNs non si trova: {self.key_file}"
        if not self.key_id:
            return "manca key_id."
        if not self.team_id:
            return "manca team_id."
        if not self.topic:
            return "manca topic (l'identificatore dell'app)."
        if not self.devices:
            return (
                "nessun dispositivo: apri l'app, scheda Monitor, e copia il "
                "codice del telefono in devices."
            )
        return None

    def _firma(self) -> str:
        """Il JWT ES256 con cui Apple riconosce il mittente."""
        try:
            import jwt  # PyJWT
        except ImportError as exc:  # pragma: no cover - dipende dall'ambiente
            raise ApnsError(
                "manca PyJWT: installalo con  pip install \"PyJWT[crypto]\""
            ) from exc

        adesso = time.time()
        if self._token and (adesso - self._token_nato) < _DURATA_TOKEN:
            return self._token

        chiave = Path(self.key_file).read_text(encoding="utf-8")
        self._token = jwt.encode(
            {"iss": self.team_id, "iat": int(adesso)},
            chiave,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )
        self._token_nato = adesso
        return self._token

    async def _connessione(self) -> httpx.AsyncClient:
        if self._client is None:
            # APNs parla solo HTTP/2: senza, la richiesta viene rifiutata.
            try:
                self._client = httpx.AsyncClient(http2=True, timeout=10.0)
            except ImportError as exc:  # pragma: no cover
                raise ApnsError(
                    "manca il supporto HTTP/2: installalo con  pip install \"httpx[http2]\""
                ) from exc
        return self._client

    async def chiudi(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ----------------------------------------------------------------- invio

    async def manda(self, titolo: str, corpo: str, url: str = "") -> tuple[int, int]:
        """Manda a tutti i dispositivi. Restituisce (riusciti, totali)."""
        problema = self.manca()
        if problema:
            raise ApnsError(problema)

        base = SVILUPPO if self.sandbox else PRODUZIONE
        client = await self._connessione()
        intestazioni = {
            "authorization": f"bearer {self._firma()}",
            "apns-topic": self.topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }
        # "url" e' quello che l'app legge per aprire il prodotto giusto.
        corpo_messaggio = json.dumps(
            {
                "aps": {
                    "alert": {"title": titolo, "body": corpo},
                    "sound": "default",
                },
                "url": url,
            }
        )

        riusciti = 0
        for device in list(self.devices):
            try:
                r = await client.post(
                    f"{base}/3/device/{device}",
                    headers=intestazioni,
                    content=corpo_messaggio,
                )
            except Exception as exc:  # rete assente, DNS, TLS
                log.warning("APNs: invio fallito verso %s: %s", device[:12], exc)
                continue

            if r.status_code == 200:
                riusciti += 1
                continue

            motivo = ""
            try:
                motivo = (r.json() or {}).get("reason", "")
            except Exception:
                motivo = r.text[:120]
            log.warning("APNs: %s ha risposto %s (%s)", device[:12], r.status_code, motivo)

            # Un dispositivo che non esiste piu' va tolto, non ritentato.
            if motivo in {"BadDeviceToken", "Unregistered"}:
                log.warning(
                    "APNs: il codice %s... non e' piu' valido. Ricopialo dall'app.",
                    device[:12],
                )
            elif motivo == "TopicDisallowed":
                log.warning("APNs: topic sbagliato. Dev'essere l'identificatore dell'app.")
            elif motivo in {"ExpiredProviderToken", "InvalidProviderToken"}:
                self._token = None  # si rifara' al prossimo giro

        return riusciti, len(self.devices)
