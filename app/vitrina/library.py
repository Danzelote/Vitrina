"""La biblioteca de fotos: escanea una carpeta, lee fechas y genera en segundo
plano las versiones que la interfaz necesita:

- miniatura: lado corto de 256 px, sin recortar (el recorte cuadrado se hace al
  dibujar, para poder "desplegarla" a su proporción real);
- versión de pantalla: lado largo de 1600 px;
- fondo desenfocado: solo para fotos verticales, muy pequeño y oscurecido.
"""

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from . import config as C

try:  # HEIC del iPhone, si está instalado
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_DATE_PATTERNS = [
    re.compile(r"(20\d{2}|19\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"),
]


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "vitrina")
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class Item:
    path: str
    collection: str
    date: datetime
    key: str
    width: int = 0
    height: int = 0
    ready: bool = False
    failed: bool = False
    thumb_path: str = field(default="", repr=False)
    screen_path: str = field(default="", repr=False)
    backdrop_path: str = field(default="", repr=False)

    @property
    def aspect(self):
        return self.width / self.height if self.height else 1.0

    @property
    def vertical(self):
        return self.height > self.width

    @property
    def date_text(self):
        return f"{self.date.day} de {MONTHS[self.date.month - 1]} de {self.date.year}"


def _date_from_exif(img):
    try:
        exif = img.getexif()
        value = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        if value:
            return datetime.strptime(str(value).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def _date_from_name(name):
    for pat in _DATE_PATTERNS:
        m = pat.search(name)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


def scan(folder):
    """Lista las fotos de `folder` (incluye subcarpetas), de la más reciente a
    la más antigua. Cada subcarpeta de primer nivel es una colección."""
    folder = os.path.abspath(os.path.expanduser(folder))
    items = []
    for root, _dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        collection = "" if rel == "." else rel.split(os.sep)[0]
        for name in sorted(files):
            if name.startswith(".") or os.path.splitext(name)[1].lower() not in C.IMAGE_EXTS:
                continue
            path = os.path.join(root, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            date = None
            try:
                with Image.open(path) as img:
                    date = _date_from_exif(img)
            except Exception:
                continue
            date = date or _date_from_name(name) or datetime.fromtimestamp(st.st_mtime)
            key = hashlib.sha1(f"{path}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:16]
            items.append(Item(path=path, collection=collection, date=date, key=key))
    items.sort(key=lambda it: it.date, reverse=True)
    return items


class Processor:
    """Genera en un hilo aparte las versiones en caché de cada foto."""

    def __init__(self, items):
        self.items = items
        self.dir = os.path.join(cache_dir(), "img")
        os.makedirs(self.dir, exist_ok=True)
        self.meta_path = os.path.join(cache_dir(), "meta.json")
        try:
            with open(self.meta_path) as f:
                self.meta = json.load(f)
        except Exception:
            self.meta = {}
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.done = 0

    def start(self):
        for it in self.items:
            it.thumb_path = os.path.join(self.dir, it.key + "_t.jpg")
            it.screen_path = os.path.join(self.dir, it.key + "_s.jpg")
            it.backdrop_path = os.path.join(self.dir, it.key + "_b.jpg")
            m = self.meta.get(it.key)
            if m and os.path.exists(it.thumb_path) and os.path.exists(it.screen_path):
                it.width, it.height = m
                it.ready = True
                self.done += 1
        self._thread.start()

    def _run(self):
        changed = 0
        for it in self.items:
            if it.ready:
                continue
            try:
                self._process(it)
                it.ready = True
                with self._lock:
                    self.meta[it.key] = [it.width, it.height]
                changed += 1
                if changed % 25 == 0:
                    self._save_meta()
            except Exception:
                it.failed = True
            self.done += 1
        self._save_meta()

    def _process(self, it):
        with Image.open(it.path) as img:
            img.draft("RGB", (C.SCREEN_LONG_SIDE, C.SCREEN_LONG_SIDE))  # JPEG: decodifica reducido
            img = ImageOps.exif_transpose(img).convert("RGB")
        it.width, it.height = img.size
        screen = img.copy()
        screen.thumbnail((C.SCREEN_LONG_SIDE, C.SCREEN_LONG_SIDE), Image.LANCZOS)
        screen.save(it.screen_path, "JPEG", quality=85)
        short = min(img.size)
        k = C.THUMB_SHORT_SIDE / short if short > C.THUMB_SHORT_SIDE else 1.0
        thumb = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
        thumb.save(it.thumb_path, "JPEG", quality=85)
        if img.height > img.width:
            bw, bh = C.BACKDROP_SIZE
            back = ImageOps.fit(img, (bw, bh), Image.BILINEAR)
            back = back.filter(ImageFilter.GaussianBlur(9))
            back = ImageEnhance.Brightness(back).enhance(0.6)
            back.save(it.backdrop_path, "JPEG", quality=90)

    def _save_meta(self):
        with self._lock:
            data = dict(self.meta)
        tmp = self.meta_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.meta_path)


# ---------------------------------------------------------------------------
# Fotos de prueba
# ---------------------------------------------------------------------------

def make_demo(count=140, seed=7):
    """Crea fotos de prueba (paisajes simples) con fechas entre 2021 y 2026.
    Las subcarpetas funcionan como colecciones."""
    import random
    from PIL import ImageDraw

    folder = os.path.join(cache_dir(), f"demo-{count}")
    marker = os.path.join(folder, ".listo")
    if os.path.exists(marker):
        return folder
    rnd = random.Random(seed)
    scenes = {
        "Viajes": [((248, 200, 141), (199, 107, 124), (44, 93, 123)), ((198, 233, 255), (134, 201, 240), (13, 75, 114)),
                   ((246, 226, 193), (236, 184, 127), (125, 65, 38)), ((14, 24, 56), (39, 48, 106), (232, 154, 87))],
        "Perro": [((207, 232, 246), (180, 215, 235), (132, 181, 110))],
        "Familia": [((233, 201, 163), (185, 130, 94), (122, 78, 56)), ((239, 227, 246), (194, 176, 222), (122, 100, 168))],
        "Cumpleaños": [((59, 34, 67), (110, 60, 96), (80, 40, 70))],
        "Comida": [((122, 154, 104), (90, 120, 80), (79, 107, 69))],
    }
    names = list(scenes)
    for i in range(count):
        coll = rnd.choice(names)
        top, mid, ground = rnd.choice(scenes[coll])
        vertical = rnd.random() < 0.3
        w, h = (900, 1600) if vertical else (1600, 1000)
        img = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(img)
        horizon = int(h * rnd.uniform(0.45, 0.65))
        for y in range(h):
            if y < horizon:
                t = y / horizon
                c = tuple(int(top[k] + (mid[k] - top[k]) * t) for k in range(3))
            else:
                t = (y - horizon) / max(1, h - horizon)
                c = tuple(int(ground[k] * (1 - 0.35 * t)) for k in range(3))
            d.line([(0, y), (w, y)], fill=c)
        r = int(min(w, h) * rnd.uniform(0.05, 0.1))
        sx, sy = int(w * rnd.uniform(0.2, 0.8)), int(horizon * rnd.uniform(0.3, 0.8))
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 236, 190))
        if coll == "Perro":
            bx, by = int(w * rnd.uniform(0.3, 0.6)), horizon + int(h * 0.08)
            d.ellipse([bx, by, bx + int(w * 0.25), by + int(h * 0.14)], fill=(150, 104, 64))
        year = rnd.choice([2021, 2022, 2023, 2024, 2024, 2025, 2025, 2026, 2026])
        month = rnd.randint(1, 9 if year == 2026 else 12)
        day = rnd.randint(1, 28)
        sub = os.path.join(folder, coll)
        os.makedirs(sub, exist_ok=True)
        img.save(os.path.join(sub, f"{year}-{month:02d}-{day:02d}_{i:03d}.jpg"), "JPEG", quality=88)
    open(marker, "w").close()
    return folder
