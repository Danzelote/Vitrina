"""Constantes de diseño. Las medidas de la cuadrícula están en "unidades de plano":
a zoom 1, una unidad equivale a un píxel de pantalla."""

import os

# Cuadrícula
CELL = 230          # lado de cada miniatura cuadrada
GAP = 16            # espacio entre miniaturas
RADIUS_GRID = 14    # esquinas redondeadas en la cuadrícula
RADIUS_VIEW = 8     # esquinas en el visor

# Niveles de zoom de la cuadrícula (1 = ~5 columnas en una pantalla de 1280 px)
ZOOMS = [0.62, 0.8, 1.0, 1.3, 1.7]
DEFAULT_ZOOM = 2

# Márgenes de pantalla (px) que la cuadrícula respeta en sus límites
MARGIN_X = 40
MARGIN_TOP = 96          # bajo la barra superior
MARGIN_BOTTOM = 84

# Visor: la foto ocupa esta fracción de la altura de la pantalla
VIEW_FILL = 0.82

# Tiempos (segundos)
MORPH_TIME = 0.95       # marco <-> cuadrícula <-> visor
ZOOM_TIME = 0.45        # un paso de zoom
FADE_TIME = 1.2         # fundido entre fotos en la presentación
SLIDE_TIME = 6.0        # cada cuánto cambia la foto en la presentación
IDLE_TIME = 15.0        # sin mover el mouse -> vuelve a la presentación
HINT_TIME = 4.0         # aviso "Mueve el mouse para explorar"
FRAME_MOVE_GRACE = 0.9  # ignora el mouse justo al entrar a la presentación
FRAME_MOVE_PX = 20      # movimiento necesario para salir de la presentación

# Recorrido con el mouse
ANCHOR_DECAY_PX = 350   # recorrido tras el cual el mapa vuelve a ser absoluto

# Colores
BG_GRID = (13, 13, 15)
BG_FRAME = (0, 0, 0)
PLACEHOLDER = (40, 40, 44)
PILL_BG = (44, 44, 48, 200)
TEXT = (245, 245, 247)
TEXT_DIM = (199, 199, 204)

# Imágenes en caché
THUMB_SHORT_SIDE = 256
SCREEN_LONG_SIDE = 1600
BACKDROP_SIZE = (160, 100)

# Cuántas texturas mantener en memoria
THUMB_CACHE = 320
SCREEN_CACHE = 6

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
              # RAW de cámara: se usa la vista previa que traen dentro (ver raw.py)
              ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp"}

# Video: versión ligera para reproducir y clip de vista previa


def _light_hardware():
    """Mac vieja (Core 2 Duo y similares, sin AVX) en Linux: videos más ligeros."""
    if os.environ.get("VITRINA_LIGERO") is not None:
        return os.environ["VITRINA_LIGERO"] == "1"
    try:
        with open("/proc/cpuinfo") as f:
            flags = next((ln for ln in f if ln.startswith("flags")), "")
        return " avx" not in flags
    except OSError:
        return False        # macOS u otros: equipo actual


LIGHT = _light_hardware()
# Versión para reproducir: cabe en esto (o al revés si es vertical). En equipos
# viejos, más chica, a 30 cuadros como máximo y codificada para decodificarse fácil.
VIDEO_MAX = (960, 540) if LIGHT else (1280, 720)
VIDEO_PROFILE = "l" if LIGHT else "n"     # parte del nombre en caché: si cambia, se regenera
PREVIEW_SHORT_SIDE = 240
PREVIEW_SECONDS = 5
PREVIEW_DELAY = 1.5           # segundos con el mouse encima antes de la vista previa

# Si se deja una foto abierta en el visor, regresa a la presentación tras este tiempo.
VIEWER_IDLE = 10 * 60
