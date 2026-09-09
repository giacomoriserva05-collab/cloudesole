"""Scheduler: un task asincrono per target, con jitter e gestione degli errori."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import replace
from datetime import datetime

import httpx

from . import adapters
from .config import Settings, Target
from .httpclient import Blocked, Cooldown, PoliteClient
from .istanza import GiaInEsecuzione, Lucchetto
from .models import Item
from .notify import Dispatcher
from .state import State

log = logging.getLogger(__name__)


class Observer:
    """Aggancio opzionale per interfacce esterne (la GUI).

    I metodi sono no-op: chi osserva sovrascrive solo cio' che gli serve.
    Un'eccezione sollevata qui non deve mai fermare il polling.
    """

    def on_poll(self, target: str, ok: bool, total: int = 0, available: int = 0, detail: str = "") -> None:
        ...

    def on_change(self, change) -> None:
        ...

    def on_target_disabled(self, target: str, reason: str) -> None:
        ...

    def on_gia_in_esecuzione(self, motivo: str) -> None:
        ...


class Monitor:
    def __init__(self, settings: Settings, observer: Observer | None = None) -> None:
        self.settings = settings
        self.state = State(settings.state_file)
        self.dispatcher = Dispatcher(settings.notifiers)
        self.client = PoliteClient(
            settings.user_agent,
            respect_robots=settings.respect_robots,
        )
        self.observer = observer or Observer()
        self._dirty = False
        # Punto di ripartenza della rotazione degli approfondimenti, per target:
        # con un tetto di controlli per giro, a turno tocca a tutti.
        self._rotation: dict[str, int] = {}

        # Ultimo esito per target e avvisi inviati: servono al riepilogo.
        self._ultimo_esito: dict[str, tuple[int, int]] = {}
        self._avvisi_inviati = 0
        self._avviato = datetime.now()

    def _tell(self, method: str, *args, **kwargs) -> None:
        try:
            getattr(self.observer, method)(*args, **kwargs)
        except Exception:
            log.debug("Observer.%s ha sollevato un'eccezione.", method, exc_info=True)

    async def close(self) -> None:
        await self.client.aclose()

    async def poll_once(self, target: Target) -> list[Item] | None:
        """Un singolo giro su un target. None se il giro e' stato saltato."""
        pagine = adapters.request_urls(target)

        raccolti: dict[str, Item] = {}
        for numero, url in enumerate(pagine, start=1):
            letti = await self._leggi_pagina(target, url)
            if letti is None:
                # La prima pagina e' indispensabile; sulle successive un errore
                # non deve buttare via quello che si e' gia' letto.
                if numero == 1:
                    return None
                break
            if not letti:
                break  # catalogo finito prima delle pagine previste
            for item in letti:
                raccolti.setdefault(item.key, item)

        items = list(raccolti.values())

        if target.checks_detail:
            items = await self._inspect(target, items)

        disponibili = sum(1 for i in items if i.available)
        self._ultimo_esito[target.name] = (len(items), disponibili)
        self._tell("on_poll", target.name, True, total=len(items), available=disponibili)
        return items

    async def _leggi_pagina(self, target: Target, url: str) -> list[Item] | None:
        """Scarica e interpreta una singola pagina. None se il giro va abbandonato."""
        try:
            response = await self.client.get(url, timeout=target.timeout)
        except Blocked as exc:
            log.error("[%s] %s - target disattivato.", target.name, exc)
            self._tell("on_target_disabled", target.name, str(exc))
            raise
        except Cooldown as exc:
            log.info("[%s] giro saltato: %s", target.name, exc)
            self._tell("on_poll", target.name, False, detail="in pausa")
            return None
        except httpx.HTTPError as exc:
            log.warning("[%s] errore di rete: %s", target.name, exc)
            self._tell("on_poll", target.name, False, detail=f"rete: {type(exc).__name__}")
            return None

        if response.status_code == 404:
            log.warning("[%s] 404 su %s - URL o tipo errato?", target.name, url)
            self._tell("on_poll", target.name, False, detail="404 - URL o tipo errato")
            return None
        if response.status_code >= 400:
            log.warning("[%s] HTTP %s su %s", target.name, response.status_code, url)
            self._tell("on_poll", target.name, False, detail=f"HTTP {response.status_code}")
            return None

        try:
            return adapters.parse(target, response)
        except (adapters.AdapterError, ValueError) as exc:
            log.warning("[%s] risposta non interpretabile: %s", target.name, exc)
            self._tell("on_poll", target.name, False, detail="risposta non interpretabile")
            return None

    async def _inspect(self, target: Target, items: list[Item]) -> list[Item]:
        """Apre le pagine prodotto per accertare la disponibilita' reale.

        Un elenco puo' contenere centinaia di voci: aprirle tutte a ogni giro
        sarebbe un carico assurdo sul sito. Se ne controlla un numero fisso per
        giro, dando la precedenza alle novita' e ruotando sulle altre, cosi' nel
        giro di qualche ciclo tutte vengono coperte.
        """
        detail = target.detail
        in_stock = detail.get("in_stock_when") or []
        out_of_stock = detail.get("out_of_stock_when") or []
        use_regex = bool(detail.get("regex", False))
        budget = max(1, int(detail.get("max_checks", 5)))
        recheck = bool(detail.get("recheck_sold_out", True))

        nuovi: list[Item] = []
        da_rivedere: list[Item] = []
        for item in items:
            previous = self.state.known(target.name, item.key)
            if previous is None:
                nuovi.append(item)
            elif not previous.get("verified"):
                # Visto ma mai accertato: va chiuso il buco.
                da_rivedere.append(item)
            elif recheck and not previous.get("available"):
                da_rivedere.append(item)

        # Rotazione sulla coda secondaria: le novita' hanno sempre la precedenza.
        if da_rivedere:
            offset = self._rotation.get(target.name, 0) % len(da_rivedere)
            da_rivedere = da_rivedere[offset:] + da_rivedere[:offset]
            self._rotation[target.name] = offset + max(0, budget - len(nuovi))

        accertati: dict[str, bool] = {}
        nomi: dict[str, str] = {}
        taglie: dict[str, list] = {}
        for item in (nuovi + da_rivedere)[:budget]:
            try:
                response = await self.client.get(item.url, timeout=target.timeout)
            except (Blocked, Cooldown) as exc:
                log.info("[%s] approfondimento interrotto: %s", target.name, exc)
                break
            except httpx.HTTPError as exc:
                log.debug("[%s] pagina non raggiungibile (%s): %s", target.name, item.title, exc)
                continue

            if response.status_code >= 400:
                log.debug("[%s] HTTP %s su %s", target.name, response.status_code, item.url)
                continue

            accertati[item.key] = adapters.evaluate_markers(
                response.text, in_stock, out_of_stock, use_regex
            )

            # La pagina e' gia' scaricata: il nome vero del prodotto costa zero
            # richieste in piu' e vale molto piu' dello slug dell'indirizzo.
            nome = adapters.estrai_nome(response.text, item.url)
            if nome:
                nomi[item.key] = nome

            # Stessa pagina, stessa occasione: le taglie e la disponibilita' di
            # ciascuna sono l'informazione che serve per decidere se andare.
            trovate = adapters.estrai_taglie(response.text)
            if trovate:
                taglie[item.key] = trovate

        if accertati:
            log.debug("[%s] disponibilita' accertata per %d articoli.", target.name, len(accertati))

        risultato: list[Item] = []
        for item in items:
            previous = self.state.known(target.name, item.key)

            # Il nome letto dalla pagina vale finche' non se ne legge uno nuovo:
            # senza conservarlo, gli articoli non riaperti in questo giro
            # tornerebbero a mostrare lo slug dell'indirizzo.
            nome = nomi.get(item.key) or (previous or {}).get("nome_pagina")
            extra = dict(item.extra)
            if nome:
                extra["nome_pagina"] = nome
            # Come il nome, anche le taglie vanno conservate fra un
            # approfondimento e il successivo.
            elenco = taglie.get(item.key) or (previous or {}).get("taglie")
            if elenco:
                extra["taglie"] = elenco

            base = replace(item, title=nome or item.title, extra=extra)

            if item.key in accertati:
                risultato.append(replace(base, available=accertati[item.key], verified=True))
            elif previous is not None and previous.get("verified"):
                # Non controllato in questo giro: si conserva l'ultimo stato
                # accertato, altrimenti tornerebbe "disponibile" per default e
                # produrrebbe un falso restock al giro successivo.
                risultato.append(
                    replace(base, available=bool(previous.get("available")), verified=True)
                )
            else:
                risultato.append(base)

        return risultato

    async def _handle(self, target: Target, items: list[Item]) -> None:
        first_run = not self.state.is_seeded(target.name)
        changes = self.state.diff(target.name, items)
        self._dirty = True

        if first_run:
            in_stock = sum(1 for i in items if i.available)
            log.info(
                "[%s] stato iniziale acquisito: %d articoli, %d disponibili.",
                target.name,
                len(items),
                in_stock,
            )
            return

        for change in changes:
            log.info("[%s] %s", target.name, change.headline)
            self._avvisi_inviati += 1
            self._tell("on_change", change)
            await self.dispatcher.dispatch(change, target.notify)

    async def _run_target(self, target: Target) -> None:
        log.info(
            "[%s] avviato - %s ogni %.0fs -> %s",
            target.name,
            target.type,
            target.interval,
            adapters.request_url(target),
        )
        # Sfalsa le partenze cosi' tutti i target non colpiscono insieme.
        await asyncio.sleep(random.uniform(0, min(target.interval, 5.0)))

        while True:
            try:
                items = await self.poll_once(target)
            except Blocked:
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("[%s] errore inatteso nel ciclo di polling.", target.name)
                items = None

            if items is not None:
                try:
                    await self._handle(target, items)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("[%s] errore nella gestione dei risultati.", target.name)

            spread = target.interval * max(0.0, target.jitter)
            await asyncio.sleep(max(1.0, target.interval + random.uniform(-spread, spread)))

    async def _riepilogo(self, ogni: float = 300.0) -> None:
        """Una riga ogni tanto, anche quando non succede niente.

        Senza questa, un monitor che funziona e non trova novita' e' identico a
        un monitor rotto: il registro resta vuoto in entrambi i casi. E' la
        differenza fra sapere che sta lavorando e doverlo indovinare.
        """
        while True:
            await asyncio.sleep(ogni)
            if not self._ultimo_esito:
                continue

            attivo_da = datetime.now() - self._avviato
            minuti = int(attivo_da.total_seconds() // 60)
            durata = f"{minuti // 60}h {minuti % 60}m" if minuti >= 60 else f"{minuti}m"
            dettaglio = ", ".join(
                f"{nome}: {totale} articoli, {disponibili} disponibili"
                for nome, (totale, disponibili) in sorted(self._ultimo_esito.items())
            )
            log.info(
                "In ascolto da %s - %d avvisi inviati finora. Ultimi controlli: %s",
                durata,
                self._avvisi_inviati,
                dettaglio,
            )

    async def _autosave(self, every: float = 30.0) -> None:
        while True:
            await asyncio.sleep(every)
            if self._dirty:
                self.state.save()
                self._dirty = False

    async def run(self) -> None:
        # Un solo monitor per configurazione: con l'avvio automatico e' facile
        # ritrovarsene due, e da li' in poi ogni avviso arriverebbe doppio.
        lucchetto = Lucchetto(self.settings.state_file.with_suffix(".lock"))
        try:
            lucchetto.acquisisci()
        except GiaInEsecuzione as exc:
            log.error("%s", exc)
            self._tell("on_gia_in_esecuzione", str(exc))
            return

        try:
            await self._run(lucchetto)
        finally:
            lucchetto.rilascia()

    async def _run(self, _lucchetto) -> None:
        active = [t for t in self.settings.targets if t.enabled]
        skipped = len(self.settings.targets) - len(active)

        log.info(
            "Monitor avviato alle %s - %d target attivi%s, canali: %s",
            datetime.now().strftime("%H:%M:%S"),
            len(active),
            f" ({skipped} disattivati)" if skipped else "",
            ", ".join(self.dispatcher.enabled) or "nessuno",
        )
        if not active:
            log.warning("Nessun target attivo: non c'e' niente da monitorare.")
            return

        tasks = [asyncio.create_task(self._run_target(t)) for t in active]
        tasks.append(asyncio.create_task(self._autosave()))
        tasks.append(asyncio.create_task(self._riepilogo()))
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.state.save()

    async def run_once(self) -> int:
        """Un solo giro su tutti i target: utile per validare la configurazione."""
        exit_code = 0
        for target in self.settings.targets:
            if not target.enabled:
                print(f"  [SPENTO]   {target.name}")
                continue
            try:
                items = await self.poll_once(target)
            except Blocked:
                exit_code = 1
                continue

            if items is None:
                print(f"  [FALLITO]  {target.name}")
                exit_code = 1
                continue

            if target.checks_detail:
                # Con l'accertamento attivo, "disponibile" ha due significati molto
                # diversi: verificato aprendo la scheda, oppure solo presente in
                # elenco. Tenerli separati evita di dichiarare piu' di quel che si sa.
                accertati = [i for i in items if i.verified]
                disponibili = [i for i in accertati if i.available]
                da_accertare = len(items) - len(accertati)
                riga = (
                    f"  [OK]       {target.name}: {len(items)} articoli, "
                    f"{len(disponibili)}/{len(accertati)} disponibili fra quelli accertati"
                )
                if da_accertare:
                    riga += f", {da_accertare} ancora da accertare"
                print(riga)
                in_stock = disponibili
            else:
                in_stock = [i for i in items if i.available]
                print(f"  [OK]       {target.name}: {len(items)} articoli, {len(in_stock)} disponibili")

            for item in in_stock[:10]:
                price = f" - {item.price}" if item.price else ""
                print(f"               disponibile: {item.title}{price}")
            await self._handle(target, items)

        self.state.save()
        return exit_code
