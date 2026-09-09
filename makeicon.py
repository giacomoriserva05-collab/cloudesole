r"""Genera restock.ico senza librerie grafiche esterne.

Disegna l'icona a risoluzione alta e la riduce per ogni misura richiesta: la
media dei pixel sui blocchi fa da antialiasing, quindi i bordi restano puliti
anche a 16x16. Il file ICO contiene immagini PNG, formato accettato da Windows
da Vista in poi.

Uso:  .venv\Scripts\python.exe makeicon.py
"""

from __future__ import annotations

import struct
from pathlib import Path

from restock.imaging import png_rgba, riduci

RENDER = 1024
SIZES = (256, 64, 48, 32, 16)

# Colori (R, G, B, A)
SFONDO = (0x23, 0x29, 0x36, 0xFF)
BORSA = (0xF3, 0xF5, 0xF9, 0xFF)
SPIA = (0x2E, 0xC4, 0x5F, 0xFF)
TRASPARENTE = (0, 0, 0, 0)


def _rounded_rect(px: float, py: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if not (x0 <= px <= x1 and y0 <= py <= y1):
        return False
    qx = max(x0 + r - px, px - (x1 - r), 0.0)
    qy = max(y0 + r - py, py - (y1 - r), 0.0)
    return qx * qx + qy * qy <= r * r


def render(size: int) -> bytearray:
    """Disegna l'icona: sacchetto della spesa con una spia di monitoraggio accesa."""
    pixels = bytearray(size * size * 4)
    step = 1.0 / size

    for row in range(size):
        py = (row + 0.5) * step
        base = row * size * 4
        for col in range(size):
            px = (col + 0.5) * step

            colour = TRASPARENTE

            # Sfondo: quadrato con angoli arrotondati.
            if _rounded_rect(px, py, 0.02, 0.02, 0.98, 0.98, 0.22):
                colour = SFONDO

                # Manico: semianello sopra il corpo della borsa.
                dx, dy = px - 0.50, py - 0.455
                distance = (dx * dx + dy * dy) ** 0.5
                if py <= 0.455 and 0.113 <= distance <= 0.157:
                    colour = BORSA

                # Corpo della borsa.
                if _rounded_rect(px, py, 0.255, 0.435, 0.745, 0.845, 0.055):
                    colour = BORSA

                # Spia di stato: il monitor e' in ascolto.
                sx, sy = px - 0.775, py - 0.225
                if sx * sx + sy * sy <= 0.088 * 0.088:
                    colour = SPIA

            offset = base + col * 4
            pixels[offset : offset + 4] = bytes(colour)

    return pixels


def to_ico(images: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)

    directory = bytearray()
    payload = bytearray()
    for size, png in images:
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0,
            0,
            1,
            32,
            len(png),
            offset,
        )
        payload += png
        offset += len(png)

    return bytes(header + directory + payload)


def main() -> int:
    print(f"Disegno a {RENDER}x{RENDER}...")
    master = render(RENDER)

    images = []
    for size in SIZES:
        print(f"  riduco a {size}x{size}")
        images.append((size, png_rgba(riduci(master, RENDER, size), size)))

    destination = Path(__file__).resolve().parent / "restock.ico"
    destination.write_bytes(to_ico(images))
    print(f"\nScritto {destination} ({destination.stat().st_size} byte, {len(images)} misure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
