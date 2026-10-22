"""Fotos RAW de cámara (Canon .CR2/.CR3, Nikon .NEF, Sony .ARW, .DNG, …).

Revelar un RAW es lento y necesita librerías pesadas. Pero casi todas las
cámaras guardan dentro del archivo una vista previa JPEG del tamaño completo
(es la que muestra la propia cámara). Vitrina usa esa: es instantánea y se ve
igual que en la pantalla de la cámara.
"""

import re
from io import BytesIO

from PIL import Image

RAW_EXTS = {".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw"}
_SOI = b"\xff\xd8\xff"
_DATE = re.compile(rb"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})")
_ROTATE = {3: 180, 6: 270, 8: 90}


def _jpeg_end(data, start):
    """Dónde termina el JPEG que empieza en `start` (o None si no es válido)."""
    pos, n = start + 2, len(data)
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker == 0xFF:          # relleno
            pos += 1
            continue
        if marker == 0xD9:
            return pos + 2
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        if marker == 0xDA:          # imagen comprimida: dentro, 0xFF nunca va seguido de 0xD9
            end = data.find(b"\xff\xd9", pos + 2 + length)
            return end + 2 if end >= 0 else None
        pos += 2 + length
    return None


def _info(data):
    """(orientación, fecha 'AAAA:MM:DD hh:mm:ss') del encabezado TIFF/EXIF, si se encuentran."""
    orientation = 1
    try:
        with Image.open(BytesIO(data)) as tif:      # CR2, NEF, ARW, DNG… son TIFF por dentro
            orientation = tif.getexif().get(0x0112, 1) or 1
    except Exception:
        pass
    m = _DATE.search(data, 0, 1 << 20)
    return orientation, (m.group(0).decode() if m else None)


def open_preview(path):
    """La vista previa más grande del RAW como imagen de Pillow, ya derecha.
    Guarda la fecha en img.info['raw_date'] (o None)."""
    with open(path, "rb") as f:
        data = f.read()
    best, i = None, 0
    while True:
        i = data.find(_SOI, i)
        if i < 0:
            break
        end = _jpeg_end(data, i)
        if end and (best is None or end - i > best[1] - best[0]):
            best = (i, end)
        i = end if end else i + 3
    if not best:
        raise OSError("este RAW no trae vista previa")
    img = Image.open(BytesIO(data[best[0]:best[1]]))
    img.load()
    orientation, date = _info(data)
    if orientation in _ROTATE:
        img = img.rotate(_ROTATE[orientation], expand=True)
    img.info["raw_date"] = date
    return img
