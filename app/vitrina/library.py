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
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from . import config as C
from . import raw

try:  # HEIC del iPhone, si está instalado
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

# libheif no siempre tolera decodificar en dos hilos a la vez: los HEIC van de uno en uno.
HEIF_LOCK = threading.Lock()


def open_image(path, decode=True):
    """Image.open, pero los HEIC se abren y decodifican sin que se encimen hilos.
    Con decode=False solo se leen los datos (fecha, lugar), sin la imagen."""
    ext = os.path.splitext(path)[1].lower()
    if ext in raw.RAW_EXTS:
        return raw.open_preview(path)
    if ext in (".heic", ".heif"):
        with HEIF_LOCK:
            img = Image.open(path)
            if decode:
                img.load()
            return img
    return Image.open(path)


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
    is_video: bool = False
    duration: float = 0.0
    video_path: str = field(default="", repr=False)     # versión ligera para reproducir
    preview_path: str = field(default="", repr=False)   # clip corto sin sonido
    video_ready: bool = False
    lat: float = None                                   # ubicación, si la foto la trae
    lon: float = None

    @property
    def play_path(self):
        """Lo que se reproduce: la versión ligera si ya está, si no el original."""
        return self.video_path if self.video_ready else self.path

    @property
    def duration_text(self):
        sec = max(0, int(round(self.duration)))
        return f"{sec // 60}:{sec % 60:02d}"

    @property
    def aspect(self):
        return self.width / self.height if self.height else 1.0

    @property
    def vertical(self):
        return self.height > self.width

    @property
    def date_text(self):
        from .i18n import long_date
        return long_date(self.date)


def _date_from_exif(img):
    try:
        exif = img.getexif()
        value = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        if value:
            return datetime.strptime(str(value).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def _gps_from_exif(img):
    """(latitud, longitud) de la foto, o (None, None)."""
    try:
        gps = img.getexif().get_ifd(0x8825)
        if not gps or 2 not in gps or 4 not in gps:
            return None, None

        def deg(v):
            d, m, s = (float(x) for x in v)
            return d + m / 60 + s / 3600
        lat, lon = deg(gps[2]), deg(gps[4])
        if str(gps.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(gps.get(3, "E")).upper().startswith("W"):
            lon = -lon
        if lat == 0 and lon == 0:
            return None, None
        return lat, lon
    except Exception:
        return None, None


def _date_from_name(name):
    for pat in _DATE_PATTERNS:
        m = pat.search(name)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def probe(path):
    """Duración y fecha de un video, con ffprobe."""
    try:
        out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", path],
                             capture_output=True, text=True, timeout=20).stdout
        fmt = json.loads(out).get("format", {})
    except Exception:
        return 0.0, None, (None, None)
    dur = float(fmt.get("duration") or 0)
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    raw = tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time")
    date = None
    if raw:
        try:
            date = datetime.fromisoformat(raw.replace("Z", "+00:00")[:25]).replace(tzinfo=None)
        except ValueError:
            date = None
    if date and date.year < 1990:  # algunas cámaras ponen 1970 o 1904
        date = None
    loc = tags.get("com.apple.quicktime.location.iso6709") or tags.get("location") or ""
    m = re.match(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", loc)
    gps = (float(m.group(1)), float(m.group(2))) if m else (None, None)
    return dur, date, gps


def media_kind(name):
    """'image', 'video' o None según la extensión (los videos necesitan ffmpeg)."""
    ext = os.path.splitext(name)[1].lower()
    if name.startswith("."):
        return None
    if ext in C.IMAGE_EXTS:
        return "image"
    if ext in C.VIDEO_EXTS and FFMPEG and FFPROBE:
        return "video"
    return None


def item_key(path, size, mtime):
    """Identificador estable de un archivo: no cambia si se mueve de colección."""
    return hashlib.sha1(f"{os.path.basename(path)}|{size}|{int(mtime)}".encode()).hexdigest()[:16]


def collection_of(folder, path):
    rel = os.path.relpath(os.path.dirname(path), folder)
    return "" if rel == "." else rel.split(os.sep)[0]


def scan_file(folder, path):
    """Un Item para el archivo `path` dentro de `folder`, o None si no sirve."""
    name = os.path.basename(path)
    kind = media_kind(name)
    if not kind:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    date, duration, lat, lon = None, 0.0, None, None
    if kind == "video":
        duration, date, (lat, lon) = probe(path)
        if duration <= 0:
            return None
    else:
        try:
            with open_image(path, decode=False) as img:
                date = _date_from_exif(img)
                lat, lon = _gps_from_exif(img)
                if not date and img.info.get("raw_date"):
                    try:
                        date = datetime.strptime(img.info["raw_date"], "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        pass
        except Exception:
            return None
    date = date or _date_from_name(name) or datetime.fromtimestamp(st.st_mtime)
    return Item(path=path, collection=collection_of(folder, path), date=date,
                key=item_key(path, st.st_size, st.st_mtime), is_video=kind == "video", duration=duration,
                lat=lat, lon=lon)


def scan(folder):
    """Lista las fotos de `folder` (incluye subcarpetas), de la más reciente a
    la más antigua. Cada subcarpeta de primer nivel es una colección. Las
    carpetas que empiezan con punto (por ejemplo la papelera) se ignoran."""
    folder = os.path.abspath(os.path.expanduser(folder))
    items = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in sorted(files):
            it = scan_file(folder, os.path.join(root, name))
            if it:
                items.append(it)
    items.sort(key=lambda it: it.date, reverse=True)
    return items


def collections_on_disk(folder):
    """Nombres de las colecciones (subcarpetas), aunque estén vacías."""
    try:
        return sorted(d for d in os.listdir(folder)
                      if not d.startswith(".") and os.path.isdir(os.path.join(folder, d)))
    except OSError:
        return []


class Processor:
    """Genera en un hilo aparte las versiones en caché de cada foto. Se le
    pueden agregar fotos en cualquier momento (por ejemplo, al subirlas desde
    el celular)."""

    def __init__(self, items):
        self.items = list(items)
        self.dir = os.path.join(cache_dir(), "img")
        os.makedirs(self.dir, exist_ok=True)
        self.meta_path = os.path.join(cache_dir(), "meta.json")
        try:
            with open(self.meta_path) as f:
                self.meta = json.load(f)
        except Exception:
            self.meta = {}
        self._lock = threading.Lock()
        self._cv = threading.Condition()
        self._photos = deque()
        self._videos = deque()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.done = 0
        self.total = 0
        self.videos_total = 0
        self.videos_done = 0

    def _prepare(self, it):
        it.thumb_path = os.path.join(self.dir, it.key + "_t.jpg")
        it.screen_path = os.path.join(self.dir, it.key + "_s.jpg")
        it.backdrop_path = os.path.join(self.dir, it.key + "_b.jpg")
        it.video_path = os.path.join(self.dir, f"{it.key}_v{C.VIDEO_PROFILE}.mp4")
        it.preview_path = os.path.join(self.dir, f"{it.key}_p{C.VIDEO_PROFILE}.mp4")
        m = self.meta.get(it.key)
        if m and os.path.exists(it.thumb_path) and os.path.exists(it.screen_path):
            it.width, it.height = m[0], m[1]
            it.ready = True
        if it.is_video and os.path.exists(it.video_path) and os.path.exists(it.preview_path):
            it.video_ready = True
        self.total += 1
        if it.ready:
            self.done += 1
        else:
            self._photos.append(it)
        if it.is_video:
            self.videos_total += 1
            if it.video_ready:
                self.videos_done += 1
            else:
                self._videos.append(it)

    def start(self):
        with self._cv:
            for it in self.items:
                self._prepare(it)
        self._thread.start()

    def add(self, items):
        """Agrega fotos nuevas a la cola (llamar desde la interfaz)."""
        with self._cv:
            for it in items:
                self.items.append(it)
                self._prepare(it)
            self._cv.notify()

    @property
    def busy(self):
        return self.done < self.total

    def _run(self):
        changed = 0
        while True:
            with self._cv:
                while not self._photos and not self._videos and not changed:
                    self._cv.wait()
                if self._photos:
                    stage, it = "photo", self._photos.popleft()
                elif self._videos:
                    stage, it = "video", self._videos.popleft()
                else:
                    stage, it = None, None
            if it is None:          # cola vacía: guarda lo hecho y espera
                self._save_meta()
                changed = 0
            elif stage == "photo":
                # Primero las imágenes (y las portadas de los videos): la cuadrícula se llena rápido.
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
            else:
                # Después, la versión ligera de cada video (lo más lento).
                if it.ready and not it.failed and os.path.exists(it.path):
                    try:
                        self._transcode(it)
                        it.video_ready = True
                    except Exception:
                        pass
                self.videos_done += 1

    def _poster(self, it):
        """Un cuadro del video (a un tercio, máximo en el segundo 1) como imagen."""
        at = min(1.0, it.duration / 3)
        out = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-ss", f"{at:.2f}", "-i", it.path, "-frames:v", "1",
                              "-vf", f"scale='min({C.SCREEN_LONG_SIDE},iw)':-2", "-f", "image2pipe",
                              "-vcodec", "png", "-"], capture_output=True, timeout=60).stdout
        from io import BytesIO
        return Image.open(BytesIO(out)).convert("RGB")

    def _transcode(self, it):
        mw, mh = C.VIDEO_MAX
        if it.vertical:
            mw, mh = mh, mw
        tmp = it.video_path + ".tmp.mp4"
        light = ["-tune", "fastdecode", "-fpsmax", "30"] if C.LIGHT else []
        subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", it.path,
                        "-vf", f"scale='min({mw},iw)':'min({mh},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", *light,
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", tmp],
                       check=True, capture_output=True, timeout=3600)
        os.replace(tmp, it.video_path)
        short = C.PREVIEW_SHORT_SIDE
        scale = f"-2:{short}" if not it.vertical else f"{short}:-2"
        tmp = it.preview_path + ".tmp.mp4"
        subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", it.video_path, "-t", str(C.PREVIEW_SECONDS),
                        "-vf", f"scale={scale}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
                       check=True, capture_output=True, timeout=600)
        os.replace(tmp, it.preview_path)

    def _process(self, it):
        if it.is_video:
            img = self._poster(it)
        else:
            with open_image(it.path) as img:
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

    from datetime import date as _date, timedelta
    today = _date.today()
    folder = os.path.join(cache_dir(), f"demo2-{count}")
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
        if i % 15 == 3:   # algunas de estas fechas en años anteriores ("Un día como hoy")
            d0 = today - timedelta(days=rnd.randint(-2, 2))
            year, month, day = today.year - rnd.randint(1, 5), d0.month, min(d0.day, 28)
        sub = os.path.join(folder, coll)
        os.makedirs(sub, exist_ok=True)
        img.save(os.path.join(sub, f"{year}-{month:02d}-{day:02d}_{i:03d}.jpg"), "JPEG", quality=88)
    if FFMPEG:
        _make_demo_videos(folder, max(4, count // 12), rnd)
    open(marker, "w").close()
    return folder


def _make_demo_videos(folder, n, rnd):
    """Videos de prueba cortos con movimiento y un tono suave de audio."""
    sources = ["testsrc2", "mandelbrot", "life=mold=10:ratio=0.5:death_color=#203040:life_color=#88c0ff",
               "cellauto=rule=110", "smptehdbars"]
    for k in range(n):
        vertical = k % 3 == 1
        size = "720x1280" if vertical else "1280x720"
        src = sources[k % len(sources)]
        dur = rnd.choice([6, 8, 12, 15])
        year = rnd.choice([2023, 2024, 2025, 2026])
        month = rnd.randint(1, 9 if year == 2026 else 12)
        day = rnd.randint(1, 28)
        coll = rnd.choice(["Viajes", "Perro", "Familia", "Cumpleaños"])
        sub = os.path.join(folder, coll)
        os.makedirs(sub, exist_ok=True)
        out = os.path.join(sub, f"{year}-{month:02d}-{day:02d}_video{k:02d}.mp4")
        freq = 220 + 110 * (k % 4)
        subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}{':' if '=' in src else '='}size={size}:rate=30",
                        "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=44100",
                        "-t", str(dur), "-af", "volume=0.15", "-c:v", "libx264", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out],
                       capture_output=True, timeout=300)
