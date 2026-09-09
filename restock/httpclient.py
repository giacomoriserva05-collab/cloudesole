"""Client HTTP 'educato': robots.txt, spaziatura per host, backoff sugli errori."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

# Distanza minima fra due richieste allo stesso host, anche con piu' target attivi.
HOST_MIN_SPACING = 1.0
ROBOTS_TTL = 3600.0
MAX_BACKOFF = 300.0


class Blocked(Exception):
    """L'URL e' escluso dal robots.txt del sito."""


class Cooldown(Exception):
    """L'host e' in pausa dopo un 429/5xx: la richiesta viene saltata."""


@dataclass
class _HostState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_request: float = 0.0
    cooldown_until: float = 0.0
    consecutive_errors: int = 0
    robots: RobotFileParser | None = None
    robots_fetched: float = 0.0


class PoliteClient:
    """Wrapper httpx che serializza e distanzia le richieste per host.

    Non nasconde la propria identita': invia uno User-Agent dichiarato e
    rispetta robots.txt, 429 e Retry-After.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        respect_robots: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self._hosts: dict[str, _HostState] = {}
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "PoliteClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    def _host_state(self, url: str) -> tuple[str, _HostState]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        state = self._hosts.get(origin)
        if state is None:
            state = _HostState()
            self._hosts[origin] = state
        return origin, state

    async def _load_robots(self, origin: str, state: _HostState) -> None:
        now = time.monotonic()
        if state.robots is not None and (now - state.robots_fetched) < ROBOTS_TTL:
            return

        parser = RobotFileParser()
        parser.set_url(f"{origin}/robots.txt")
        try:
            response = await self._client.get(f"{origin}/robots.txt", timeout=10.0)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                # Nessun robots.txt raggiungibile: per convenzione si considera tutto permesso.
                parser.allow_all = True
        except httpx.HTTPError as exc:
            log.debug("robots.txt non raggiungibile per %s: %s", origin, exc)
            parser.allow_all = True

        state.robots = parser
        state.robots_fetched = now

    async def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        origin, state = self._host_state(url)
        await self._load_robots(origin, state)
        assert state.robots is not None
        return state.robots.can_fetch(self.user_agent, url)

    async def get(self, url: str, *, timeout: float | None = None) -> httpx.Response:
        origin, state = self._host_state(url)

        if self.respect_robots:
            await self._load_robots(origin, state)
            assert state.robots is not None
            if not state.robots.can_fetch(self.user_agent, url):
                raise Blocked(f"robots.txt di {origin} vieta l'accesso a {url}")

        async with state.lock:
            now = time.monotonic()
            if now < state.cooldown_until:
                raise Cooldown(
                    f"{origin} in pausa per altri {state.cooldown_until - now:.0f}s"
                )

            gap = now - state.last_request
            if gap < HOST_MIN_SPACING:
                await asyncio.sleep(HOST_MIN_SPACING - gap)

            try:
                response = await self._client.get(url, timeout=timeout)
            except httpx.HTTPError:
                state.consecutive_errors += 1
                state.cooldown_until = time.monotonic() + self._backoff(state)
                raise
            finally:
                state.last_request = time.monotonic()

            if response.status_code in (429, 503):
                delay = self._retry_after(response) or self._backoff(state, bump=True)
                state.cooldown_until = time.monotonic() + delay
                log.warning(
                    "%s ha risposto %s: pausa di %.0fs su questo host.",
                    origin,
                    response.status_code,
                    delay,
                )
                raise Cooldown(f"{origin} ha risposto {response.status_code}")

            if response.status_code >= 500:
                state.consecutive_errors += 1
                state.cooldown_until = time.monotonic() + self._backoff(state)
            else:
                state.consecutive_errors = 0

            return response

    def _backoff(self, state: _HostState, *, bump: bool = False) -> float:
        if bump:
            state.consecutive_errors += 1
        exponent = max(state.consecutive_errors, 1)
        return min(MAX_BACKOFF, 5.0 * (2 ** (exponent - 1)))

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(1.0, float(value))
        except ValueError:
            return None
