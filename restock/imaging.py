"""Scrittura di PNG in memoria, senza librerie grafiche esterne.

Serve in due punti: l'icona dell'applicazione e i segni di spunta
dell'interfaccia. Sta qui per non averne due copie.
"""

from __future__ import annotations

import struct
import zlib


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def png_rgba(pixels: bytes | bytearray, larghezza: int, altezza: int | None = None) -> bytes:
    """Immagine PNG a 32 bit da un buffer RGBA riga per riga."""
    altezza = larghezza if altezza is None else altezza
    grezzo = bytearray()
    for riga in range(altezza):
        grezzo.append(0)  # filtro "none"
        grezzo += pixels[riga * larghezza * 4 : (riga + 1) * larghezza * 4]

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", larghezza, altezza, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(grezzo), 9))
        + chunk(b"IEND", b"")
    )


def riduci(sorgente: bytes | bytearray, da: int, a: int) -> bytearray:
    """Media dei blocchi: e' quello che produce l'antialiasing.

    I colori vanno premoltiplicati per l'alpha prima di mediarli, altrimenti i
    pixel trasparenti trascinano il proprio colore nella media e i bordi
    vengono fuori con un alone.
    """
    if da == a:
        return bytearray(sorgente)

    fattore = da // a
    campioni = fattore * fattore
    uscita = bytearray(a * a * 4)

    for riga in range(a):
        for colonna in range(a):
            r = g = b = alpha = 0
            for sub_riga in range(fattore):
                inizio = ((riga * fattore + sub_riga) * da + colonna * fattore) * 4
                for sub_col in range(fattore):
                    i = inizio + sub_col * 4
                    a_pixel = sorgente[i + 3]
                    r += sorgente[i] * a_pixel
                    g += sorgente[i + 1] * a_pixel
                    b += sorgente[i + 2] * a_pixel
                    alpha += a_pixel

            fuori = (riga * a + colonna) * 4
            if alpha:
                uscita[fuori] = min(255, r // alpha)
                uscita[fuori + 1] = min(255, g // alpha)
                uscita[fuori + 2] = min(255, b // alpha)
                uscita[fuori + 3] = alpha // campioni
    return uscita
