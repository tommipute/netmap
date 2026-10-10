"""Immagini caricate dagli utenti (sfondo delle mappe): tipo e misure lette dall'intestazione del file.

Solo PNG, JPEG e WebP: niente SVG, che può contenere codice. Niente librerie: bastano pochi byte dell'intestazione.
"""
import struct

MAX_IMAGE_BYTES = 15 * 1024 * 1024  # nginx accetta corpi fino a 20 MB
MAX_SIDE_PX = 20000  # oltre è quasi certamente un file rotto


class ImageError(ValueError):
    pass


def _jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:  # byte di riempimento
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # marcatori senza lunghezza
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2:i + 4])
        # SOF0..SOF15 tranne DHT (C4), JPG (C8) e DAC (CC): lì ci sono le misure
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    raise ImageError("Immagine JPEG non leggibile")


def image_info(data: bytes) -> tuple[str, int, int]:
    """(content type, larghezza, altezza) in pixel; ImageError se il file non è un'immagine accettata."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError(f"L'immagine è troppo grande: il massimo è {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
            kind, (width, height) = "image/png", struct.unpack(">II", data[16:24])
        elif data[:3] == b"\xff\xd8\xff":
            kind, (width, height) = "image/jpeg", _jpeg_size(data)
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            chunk = data[12:16]
            if chunk == b"VP8X":
                width = 1 + int.from_bytes(data[24:27], "little")
                height = 1 + int.from_bytes(data[27:30], "little")
            elif chunk == b"VP8 ":
                width, height = struct.unpack("<HH", data[26:30])
                width, height = width & 0x3FFF, height & 0x3FFF
            elif chunk == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            else:
                raise ImageError("Immagine WebP non leggibile")
            kind = "image/webp"
        else:
            raise ImageError("Formato non accettato: carica un'immagine PNG, JPG o WebP")
    except struct.error as exc:
        raise ImageError("Immagine rovinata o incompleta") from exc
    if not (0 < width <= MAX_SIDE_PX and 0 < height <= MAX_SIDE_PX):
        raise ImageError("Immagine rovinata o incompleta")
    return kind, width, height
