"""Istanza unica: impedisce che due monitor girino insieme.

Con l'avvio automatico il rischio diventa concreto: il monitor parte da solo
all'accesso, poi si apre la finestra e si preme Avvia, e da quel momento ogni
restock arriva due volte. Peggio, i due processi si sovrascriverebbero a vicenda
il file di stato.

Il lucchetto e' un blocco del sistema operativo su un file aperto: se il
processo muore, anche male, il sistema lo rilascia da solo. Non serve pulizia,
e non restano lucchetti fantasma dopo un blocco della macchina.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import TracebackType


class GiaInEsecuzione(RuntimeError):
    """Un altro monitor sta gia' girando su questa configurazione."""

    def __init__(self, percorso: Path, pid: str = "") -> None:
        chi = f" (processo {pid})" if pid else ""
        super().__init__(
            f"Un altro monitor sta gia' usando {percorso.name}{chi}.\n"
            f"Fermalo prima di avviarne un altro, altrimenti ricevi ogni avviso due volte."
        )
        self.percorso = percorso
        self.pid = pid


class Lucchetto:
    """Blocco esclusivo su un file, rilasciato dal sistema alla morte del processo."""

    def __init__(self, percorso: str | Path) -> None:
        self.percorso = Path(percorso)
        self._fd: int | None = None

    def _blocca(self, fd: int) -> bool:
        """Prova a prendere il blocco senza attendere. False se e' gia' preso."""
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _sblocca(self, fd: int) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass

    def _chi_lo_tiene(self) -> str:
        """Il PID scritto da chi detiene il lucchetto, se leggibile."""
        try:
            return self.percorso.read_text(encoding="utf-8").strip()[:20]
        except OSError:
            return ""

    def acquisisci(self) -> None:
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.percorso, os.O_RDWR | os.O_CREAT, 0o644)

        # Il byte iniziale deve esistere: su Windows si blocca un intervallo di
        # byte, e su un file vuoto la chiamata fallirebbe.
        if os.fstat(fd).st_size == 0:
            os.write(fd, b" ")
            os.lseek(fd, 0, os.SEEK_SET)

        if not self._blocca(fd):
            pid = self._chi_lo_tiene()
            os.close(fd)
            raise GiaInEsecuzione(self.percorso, pid)

        self._fd = fd
        # Il PID serve solo a dire all'utente chi tiene il lucchetto.
        os.lseek(fd, 1, os.SEEK_SET)
        os.truncate(fd, 1)
        os.write(fd, str(os.getpid()).encode())

    def rilascia(self) -> None:
        if self._fd is None:
            return
        self._sblocca(self._fd)
        os.close(self._fd)
        self._fd = None

    def __enter__(self) -> "Lucchetto":
        self.acquisisci()
        return self

    def __exit__(
        self,
        genere: type[BaseException] | None,
        valore: BaseException | None,
        traccia: TracebackType | None,
    ) -> None:
        self.rilascia()
