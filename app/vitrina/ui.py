"""La interfaz de Vitrina: presentación, cuadrícula, niveles y visor.

Un solo espacio continuo: la presentación es la cuadrícula vista de muy cerca.
Al mover el mouse la cámara se aleja y la foto se encoge hasta su lugar; al
alejarse más, las fotos se agrupan por meses y por años (zoom semántico).
"""

import math
import os
import queue
import random
import time
from datetime import date, datetime

os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")  # escalado suave (lineal)

import pygame  # noqa: E402
from pygame._sdl2.video import Renderer, Window  # noqa: E402

from . import __version__  # noqa: E402
from . import camera as cam  # noqa: E402
from . import kenburns as KB  # noqa: E402
from . import memories as MEM  # noqa: E402
from . import night as NIGHT  # noqa: E402
from . import nightclock as NC  # noqa: E402
from . import i18n as I18N  # noqa: E402
from .i18n import tr  # noqa: E402
from .places import place_of  # noqa: E402
from . import wifi as WIFI  # noqa: E402
from . import qrscan as QR  # noqa: E402
from . import splash as SPL  # noqa: E402
from . import installer as INST  # noqa: E402
from . import ambient as AMB  # noqa: E402
from . import watchdog as WATCH  # noqa: E402
from . import updater as UPD  # noqa: E402
from . import config as C  # noqa: E402
from . import levels as LV  # noqa: E402
from . import video as VID  # noqa: E402
from . import theme as TH  # noqa: E402
from .theme import T  # noqa: E402
from .easing import EASE, EASE_IN_OUT, Tween, cubic_bezier, lerp  # noqa: E402
from pygame._sdl2.video import Texture  # noqa: E402
from .gfx import Gfx  # noqa: E402
from .settings import Settings  # noqa: E402

FRAME, GRID, VIEWER = "frame", "grid", "viewer"
PHOTOS, MONTHS, YEARS, COLLS = "photos", "months", "years", "colls"
RANK = {PHOTOS: 0, MONTHS: 1, COLLS: 1, YEARS: 2}
LEVEL_TIME = 0.75
SWIPE_TIME = 0.85     # cambio de foto en el visor (flechas, botones y gesto)
SWIPE_EASE = cubic_bezier(0.6, 0.0, 0.25, 1.0)    # arranca suave, acelera a la mitad y aterriza despacio
SWIPE_TRIGGER = 1.0    # desplazamiento del trackpad que cuenta como gesto
RELEASE_PAUSE = 0.7    # sin aviso de dedos: pausa que se toma como "soltado"
SWIPE_UNIT = 60        # puntos que avanza la foto por cada unidad de desplazamiento del trackpad
GESTURE_GAP = 0.25     # segundos sin eventos de rueda = gesto nuevo
SETTINGS_IN = 0.38     # Ajustes aparece...
SETTINGS_OUT = 0.24    # ...y se va un poco más rápido
THEME_TIME = 0.7       # cambio gradual entre tema claro y oscuro
BAR_H = 72
HUD_IN, HUD_HOLD, HUD_OUT = 0.15, 1.4, 0.35   # píldora de volumen y brillo
# Teclas de volumen y brillo (códigos de SDL; pygame no les pone nombre).
ENTER_EASE = cubic_bezier(0.7, 0.0, 0.3, 1.0)
SHUT_SHRINK, SHUT_SPLIT = 1.0, 0.7    # apagar: la pantalla se cierra en la ventanita; luego se separa en 4    # la ventanita del logo crece hasta llenar la pantalla
POWER_KEY = 0x40000066        # tecla de encendido (SDLK_POWER)
MEDIA_KEYS = {0x40000080: "vol_up", 0x40000081: "vol_down", 0x4000007F: "mute", 0x40000106: "mute",
              0x40000114: "bright_up", 0x40000113: "bright_down"}


def inside(rect, x, y):
    return rect is not None and rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]


class App:
    def __init__(self, items, processor=None, fullscreen=False, invert_zoom=False, size=(1280, 800),
                 debug_input=False, lib=None, splash=None):
        self.debug_input = debug_input
        self.lib = lib                      # biblioteca en vivo (fotos que llegan del celular)
        self.events = queue.Queue()         # órdenes del servidor web, se atienden en este hilo
        self.web = None                     # servidor web (lo asigna main.py)
        pygame.display.init()
        pygame.font.init()
        if splash:      # la ventana ya está abierta con el logo de arranque
            self.win, self.ren = splash.win, splash.ren
        else:
            self.win = Window("Vitrina", size=size, resizable=True, allow_high_dpi=True)
            if fullscreen:
                self.win.set_fullscreen(True)
            self.ren = Renderer(self.win, accelerated=-1, vsync=True)
        self.gfx = Gfx(self.ren)
        self.fit_to_window()
        self.items = list(items)
        self.processor = processor
        self.settings = Settings.load()
        T.set(TH.resolve(self.settings.theme))
        I18N.set_lang(self.settings.language)
        self.zoom_sign = -1 if invert_zoom else 1
        self.plane = cam.Plane(*cam.grid_shape(max(1, len(items))), len(items))
        self.groups = LV.Groups(items)

        now = time.monotonic()
        self.mode = FRAME
        self.lvl = PHOTOS
        self.lvl_prev = None
        self.lvl_tween = None
        self.lvl_origin = (self.vw / 2, self.vh / 2)
        self.zi = C.DEFAULT_ZOOM
        self.hero = max(0, min(len(items) - 1, 4 * self.plane.cols + 6))
        self.morph_i = self.hero
        self.big_kind = FRAME
        cx, cy = self.plane.cell_center(self.hero)
        self.cx, self.cy, self.s = cx, cy, self.frame_scale()
        self.tcx, self.tcy, self.target_s = cx, cy, self.s
        self.cam_tween = None
        self.m = 1.0
        self.m_tween = None
        self.fade = None
        self._next = None
        self._next_since = 0.0
        self.anchor = None
        self.long_until = 0.0
        self.mx, self.my = self.vw / 2, self.vh / 2
        self.inside = False
        self.last_move = now
        self.last_slide = now
        self.frame_since = now
        self.frame_anchor = None
        self.hint_until = now + C.HINT_TIME
        self.hover_i = None
        self.hover_amt = 0.0
        self.hover_amts = {}        # cuánto está "levantada" cada foto (crece al entrar el mouse, baja al salir)
        self.hover_group = None
        self.cluster_rects = []
        self.wheel_acc = 0.0
        self.wheel_last = 0.0
        self.gesture_start = 0.0
        self.level_at = 0.0
        self.edge_at = 0.0
        self.month_frac = 0.0
        self.month_target = 0.0
        self.month_anchor = None
        self.coll_filter = None
        self.queue = []
        self.settings_open = False
        # Videos: un reproductor por papel (visor, presentación, vista previa).
        self.players = {}          # papel -> (índice, Player)
        self.dying = []            # reproductores bajando el volumen antes de cerrarse
        self.hover_since = 0.0
        self.swipe = None          # animación de cambio de foto en el visor (arrastre)
        self.glide = None          # cambio de foto con flechas: una tira que se desliza (ver viewer_step)
        self.drag = None           # arrastre con dos dedos en curso (progreso con signo)
        self.rubber = None         # rebote al arrastrar en la primera o la última foto
        self.drag_vis = 0.0        # posición dibujada (sigue a self.drag suavemente)
        self.drag_vel = 0.0
        self.fingers = set()       # dedos sobre el trackpad (si el sistema los reporta)
        self.touch_seen = False
        self.ignore_swipe_until_gap = False
        self.swipe_acc = 0.0
        self.settings_tab = "show"
        self.slide_history = []     # fotos ya mostradas (flecha izquierda en la presentación)
        self.mouse_at = now         # último movimiento real del mouse
        self.keys_drove = False     # en el visor se avanzó con flechas o deslizando: sin puntero
        self.chrome_amt = 1.0       # controles del visor (se ocultan al no mover el mouse)
        self.zoom_amt = 0.0         # sin controles, la foto crece un poco (0–1)
        self.pointer_shown = None
        self.lib_version = lib.version if lib else 0
        self.new_keys = []          # fotos recién llegadas: se muestran primero
        self.toast = None           # (texto, inicio) aviso discreto arriba
        self.toast_new = 0
        self.settings_tw = None     # animación al abrir y cerrar Ajustes
        self.settings_amt = 0.0
        self.offscreen_tex = {}     # texturas para el desenfoque del fondo y el panel
        self.theme_target = T.name
        self.theme_anim = None      # (paleta de origen, paleta destino, inicio)
        # Ken Burns: movimiento de cada foto en pantalla (índice -> (inicio, Motion)).
        self.kb = {}
        # "Un día como hoy"
        self.memory_queue = []
        self.memory_day = None
        self.seq_pos = None
        self.slides_since_memory = 0
        # Reloj e información: se mueven unos píxeles de vez en cuando (pantallas viejas).
        self.drift = [0.0, 0.0]
        self.drift_target = (0.0, 0.0)
        self.drift_at = now + 180
        # Modo noche
        self.night = 0.0            # 0 = normal, 1 = apagada (o solo el reloj tenue)
        self.night_force = False    # tecla n: simula la noche para probar
        self.forced_recent = False
        self.dark = False
        self.woke = False
        self.last_input = now
        self.sleeping = False
        self.sensor = NIGHT.light_sensor()
        self.glyphs = NC.Glyphs(self.ren)
        self.wifi = WIFI.Wifi()
        self.volume = WIFI.Volume()
        self.power_dlg = None       # ventana de "¿Apagar la Vitrina?" (tecla de encendido o Ajustes)
        self.power_amt = 0.0
        self.wall_ref = (time.time(), time.monotonic())   # para notar que la Mac despertó del reposo
        self.resumed_at = -1e9
        self.hud = None             # aviso de volumen o brillo: (tipo, nivel 0–1, silencio, inicio)
        self.wifi.refresh_status()
        self.wifi_checked = now
        self.pw = None              # contraseña de WiFi que se está escribiendo: {"ssid", "text", "show"}
        self.backlight = NIGHT.Backlight(self.settings.min_brightness)
        if self.settings.brightness < 0:
            self.settings.brightness = self.backlight.initial_level()
        self.bright = self.settings.brightness   # brillo que se ve ahorita (se acerca al objetivo)
        self.bright_fast_until = -1e9
        self.calib = None           # calibración del brillo mínimo en curso
        # Logo de arranque: sigue la animación del que se vio mientras cargaba (mismo reloj).
        self.intro = {"start": splash.start if splash else now, "phase": "load"}
        self.shutting = None        # apagando o reiniciando: solo el logo
        self.inst = None            # instalar en esta Mac: {"stage", "at", "ins", "disk"}
        self.updater = UPD.Updater()   # actualizar la Vitrina instalada desde GitHub
        self.update_done_at = None
        self.help_open = False      # lista de atajos de teclado (tecla H)
        self.help_at = 0.0
        self.help_amt = 0.0
        self.scan = None            # cámara leyendo el código QR del WiFi: {"scanner", "start", "tex"}
        self.hits = []
        self.ui_rects = []
        self.running = True
        self.last_t = now
        self.show_pointer(False)
        self.set_pointer()

    def show_pointer(self, visible):
        if visible != getattr(self, "pointer_shown", None):
            self.pointer_shown = visible
            pygame.mouse.set_visible(visible)

    def set_pointer(self):
        """Puntero propio: un círculo suave (como el del iPad), no la flecha ni la X."""
        try:
            size = 26
            big = pygame.Surface((size * 4, size * 4), pygame.SRCALPHA)
            c = size * 2
            pygame.draw.circle(big, (0, 0, 0, 40), (c, c + 4), 40)          # sombra
            pygame.draw.circle(big, (0, 0, 0, 120), (c, c), 38)            # orilla
            pygame.draw.circle(big, (255, 255, 255, 225), (c, c), 33)      # centro
            surf = pygame.transform.smoothscale(big, (size, size))
            pygame.mouse.set_cursor(pygame.cursors.Cursor((size // 2, size // 2), surf))
        except Exception:      # noqa: BLE001  (sin puntero de color: se queda el del sistema)
            pass

    # ------------------------------------------------------------------ escalas

    def fit_to_window(self):
        """Dibuja en puntos de pantalla pero a la resolución real (Retina)."""
        self.ren.logical_size = (0, 0)
        out_w = self.ren.get_viewport().width
        win_w, win_h = self.win.size
        self.gfx.dpi = max(1.0, out_w / win_w) if win_w else 1.0
        self.ren.logical_size = (win_w, win_h)
        self.vw, self.vh = win_w, win_h

    def frame_scale(self):
        return self.vh / C.CELL

    def view_scale(self):
        return C.VIEW_FILL * self.vh / C.CELL

    def grid_scale(self):
        return C.ZOOMS[self.zi]

    def fitting_zoom(self):
        """Con pocas fotos, el zoom más grande en que se ve toda la cuadrícula
        (así no queda una fila escondida bajo la barra). Si no cabe, el de siempre."""
        aw = self.vw - 2 * C.MARGIN_X
        ah = self.vh - C.MARGIN_TOP - C.MARGIN_BOTTOM
        fits = [k for k, z in enumerate(C.ZOOMS)
                if self.plane.width * z <= aw and self.plane.height * z <= ah]
        return max(fits) if fits else C.DEFAULT_ZOOM

    def big_dims(self, item, kind):
        ar = item.aspect if item.ready else 1.6
        if kind == FRAME:
            if item.ready and item.vertical:
                return C.CELL * ar, C.CELL
            return C.CELL * self.vw / self.vh, C.CELL
        w, h = C.CELL * ar, C.CELL
        max_w = 0.92 * self.vw / self.view_scale()
        if w > max_w:
            w, h = max_w, max_w / ar
        return w, h

    # ------------------------------------------------------------------ filtro

    def matches(self, i):
        return self.coll_filter is None or self.items[i].collection == self.coll_filter

    def set_filter(self, name):
        self.coll_filter = name
        self.queue = []

    # ------------------------------------------------------------------ cámara

    def move_camera(self, cx, cy, s, duration, now, ease=EASE):
        start = cam.to_screen(self.cx, self.cy, self.s, self.vw, self.vh)
        end = cam.to_screen(cx, cy, s, self.vw, self.vh)
        self.cam_tween = Tween(start, end, duration, ease, now)
        self.tcx, self.tcy, self.target_s = cx, cy, s
        self.long_until = now + duration

    def jump_camera(self, cx, cy, s):
        self.cam_tween = None
        self.cx, self.cy, self.s = cx, cy, s
        self.tcx, self.tcy, self.target_s = cx, cy, s

    def morph_to(self, value, duration, now):
        self.m_tween = Tween((self.m,), (value,), duration, EASE, now)

    def set_anchor(self):
        self.anchor = cam.Anchor(self.mx, self.my, self.tcx, self.tcy)

    def nearest(self):
        pitch = C.CELL + C.GAP
        col = min(max(round((self.cx - C.CELL / 2) / pitch), 0), self.plane.cols - 1)
        row = min(max(round((self.cy - C.CELL / 2) / pitch), 0), self.plane.rows - 1)
        return min(row * self.plane.cols + col, len(self.items) - 1)

    def photo_under_mouse(self):
        px = self.cx + (self.mx - self.vw / 2) / self.s
        py = self.cy + (self.my - self.vh / 2) / self.s
        i = self.plane.index_at(px, py, len(self.items))
        return i if i is not None else self.nearest()

    # ------------------------------------------------------------------ videos

    def video_size(self, item, max_w):
        """Tamaño en píxeles al que conviene decodificar un video."""
        w, h = item.width or 1280, item.height or 720
        max_w = min(max_w, C.VIDEO_MAX[0])        # en equipos viejos, no más que la versión ligera
        k = min(1.0, max_w / max(w, 1), (max_w * 0.75 if not item.vertical else max_w * 1.8) / max(h, 1))
        return max(64, w * k), max(64, h * k)

    def start_video(self, role, i, path=None, audio=False, loop=False, max_w=1280, start_paused=False):
        self.stop_video(role, fade=False)
        item = self.items[i]
        # Solo la versión ya preparada (H.264 ligera): los originales del celular
        # (HEVC, 4K) son demasiado pesados y se ve la portada mientras tanto.
        if not (VID.AVAILABLE and item.is_video and item.ready and item.video_ready):
            return
        try:
            p = VID.Player(self.ren, path or item.play_path, self.video_size(item, max_w), audio=audio,
                           loop=loop, start_paused=start_paused)
        except Exception as exc:
            print("No se pudo reproducir el video:", exc)
            return
        self.players[role] = (i, p)

    def stop_video(self, role, fade=True):
        entry = self.players.pop(role, None)
        if not entry:
            return
        i, p = entry
        if fade and p.audio:
            p.fade_out_and_close()
            self.dying.append((i, p))      # sigue moviéndose mientras se desvanece el sonido
        else:
            p.close()

    def player_for(self, role, i):
        entry = self.players.get(role)
        return entry[1] if entry and entry[0] == i else None

    def video_layer(self, i, now):
        """(textura, opacidad) del video del elemento i, si se está reproduciendo."""
        starting = False
        for role in ("view", "view_next", "frame", "next", "preview"):
            p = self.player_for(role, i)
            if p and p.has_frame and p.texture is not None:
                return p.texture, p.frame_alpha(now)
            starting = starting or p is not None
        starting = starting or self.player_for("warm", i) is not None
        if starting:        # ya se abrió de nuevo: la portada (primer cuadro) mientras arranca
            return None, 0.0
        for j, p in reversed(self.dying):   # el video que se cierra se ve en movimiento hasta el final
            if j == i and p.has_frame and p.texture is not None:
                return p.texture, 1.0
        return None, 0.0

    def video_texture(self, i):
        tex, a = self.video_layer(i, time.monotonic())
        return tex if a >= 1.0 else None

    def update_players(self, dt, now=None):
        for _role, (_i, p) in list(self.players.items()):
            p.update(dt, now)
        self.dying = [(i, p) for i, p in self.dying if p.update(dt, now)]

    def close_all_videos(self):
        for role in list(self.players):
            self.stop_video(role, fade=False)
        for _i, p in self.dying:
            p.close()
        self.dying = []
        VID.wait_all()

    # ------------------------------------------------------------------ modos

    def enter_grid(self, now):
        if self.fade:
            self.finish_fade()
        self.stop_video("frame", fade=False)
        self.stop_video("next", fade=False)
        self.mode = GRID
        self.lvl = PHOTOS
        if len(self.items) <= 64:
            self.zi = self.fitting_zoom()
        s = self.grid_scale()
        cx, cy = cam.clamp(*self.plane.cell_center(self.hero), s, self.plane, self.vw, self.vh)
        self.move_camera(cx, cy, s, C.MORPH_TIME, now)
        self.morph_to(0.0, C.MORPH_TIME, now)
        self.set_anchor()
        self.show_pointer(True)

    def go_frame(self, i, now):
        if self.lvl != PHOTOS:
            # Desde un nivel de grupos: volvemos a las fotos sin animar la capa.
            self.lvl, self.lvl_tween = PHOTOS, None
            s = self.grid_scale()
            self.jump_camera(*cam.clamp(*self.plane.cell_center(i), s, self.plane, self.vw, self.vh), s)
        if self.morph_i != i:
            self.m = 0.0
        self.mode = FRAME
        self.settings_open = False
        self.hero = self.morph_i = i
        self.big_kind = FRAME
        self.kb_start(i, now)
        self.seq_pos = None
        cx, cy = self.plane.cell_center(i)
        self.move_camera(cx, cy, self.frame_scale(), C.MORPH_TIME, now)
        self.morph_to(1.0, C.MORPH_TIME, now)
        self.last_slide = now
        self.frame_since = now
        self.frame_anchor = None
        self.hint_until = now + C.HINT_TIME
        self.anchor = None
        self.stop_video("view")
        self.stop_video("preview", fade=False)
        self.start_video("frame", i)
        self.show_pointer(False)

    def open_viewer(self, i, now):
        self.mode = VIEWER
        self.morph_i = self.hero = i
        self.big_kind = VIEWER
        self.m = 0.0
        cx, cy = self.plane.cell_center(i)
        self.move_camera(cx, cy, self.view_scale(), C.MORPH_TIME, now)
        self.morph_to(1.0, C.MORPH_TIME, now)
        self.last_move = now
        self.stop_video("preview", fade=False)
        warm = self.players.pop("warm", None)
        if warm and warm[0] == i:
            # Ya estaba cargado en pausa (el mouse se quedó encima): suena al instante.
            self.players["view"] = warm
            warm[1].play()
        else:
            if warm:
                warm[1].close()
            self.start_video("view", i, audio=True)   # empieza desde el inicio, con fundido de audio

    def neighbor(self, i, d):
        """Siguiente (d=1) o anterior (d=-1) foto visible con el filtro, o None."""
        j = i + d
        while 0 <= j < len(self.items):
            if self.matches(j):
                return j
            j += d
        return None

    def viewer_step(self, d, now):
        """Flechas (o deslizar) en el visor: las fotos son una tira que se
        desliza con un resorte. Si se presiona varias veces seguidas, la tira
        acelera hacia la foto pedida sin regresar a la que iba; si se cambia de
        dirección, da la vuelta suave desde donde está."""
        if self.mode != VIEWER or self.m_tween:
            return
        self.keys_drove = True
        if self.swipe:
            self.finish_swipe()
        self.drag = None
        gl = self.glide
        if gl is None:
            gl = self.glide = {"items": {0: self.morph_i}, "off": 0.0, "vel": 0.0, "target": 0}
            self.stop_video("view")
            self.stop_video("view_next", fade=False)
        target = gl["target"] + d
        if self.glide_item(target) is None:
            if gl["target"] == 0 and gl["off"] == 0.0 and gl["vel"] == 0.0:
                self.glide = None            # no hay más fotos de ese lado
            return
        gl["target"] = target
        self.gfx.screen(self.items[self.glide_item(target)], force=True)
        self.last_move = now

    def glide_item(self, j):
        """La foto en la posición j de la tira (0 = donde empezó), o None."""
        gl = self.glide
        items = gl["items"]
        if j in items:
            return items[j]
        step = 1 if j > 0 else -1
        k = 0
        while k != j:
            nxt = k + step
            if nxt not in items:
                cur = items[k]
                n = self.neighbor(cur, step) if cur is not None else None
                items[nxt] = n
                if n is None:
                    return None
            if items[nxt] is None:
                return None
            k = nxt
        return items[j]

    def glide_x(self, j):
        """Posición horizontal de la foto j en la tira (la 0 está en 0)."""
        x, step, k = 0.0, (1 if j > 0 else -1), 0
        while k != j:
            a, b = self.glide_item(k), self.glide_item(k + step)
            if a is None or b is None:
                break
            x += step * self.page_width(a, b)
            k += step
        return x

    def update_glide(self, dt, now):
        gl = self.glide
        if not gl:
            return
        # Resorte sin rebote: rápido cuando falta mucho, suave al llegar.
        w = 2 * math.pi / 0.55
        diff = gl["target"] - gl["off"]
        acc = w * w * diff - 2 * w * gl["vel"]
        gl["vel"] += acc * min(dt, 0.05)
        gl["off"] += gl["vel"] * min(dt, 0.05)
        if abs(diff) < 0.002 and abs(gl["vel"]) < 0.02:
            self.finish_glide()

    def finish_glide(self):
        gl = self.glide
        j = round(gl["off"]) if abs(gl["off"] - gl["target"]) > 0.5 else gl["target"]
        i = self.glide_item(j)
        self.glide = None
        if i is None:
            i = gl["items"][0]
        self.morph_i = self.hero = i
        self.jump_camera(*self.plane.cell_center(i), self.view_scale())
        if self.mode == VIEWER:
            self.start_video("view", i, audio=True)

    def draw_glide(self, bg):
        gl = self.glide
        radius = C.RADIUS_VIEW * self.view_scale()
        off = gl["off"]
        lo = math.floor(off)
        x_lo = self.glide_x(lo)
        x_hi = self.glide_x(lo + 1) if self.glide_item(lo + 1) is not None else x_lo
        x_now = lerp(x_lo, x_hi, off - lo)
        for j in range(lo - 1, lo + 3):
            i = self.glide_item(j)
            if i is None:
                continue
            dist = abs(j - off)
            alpha = max(0.0, 1.0 - dist)          # como antes: la que sale se desvanece
            if alpha <= 0.01:
                continue
            x, y, w, h = self.viewer_rect(i)
            dx = self.glide_x(j) - x_now
            if x + dx + w < 0 or x + dx > self.vw:
                continue
            self.draw_tile(self.items[i], x + dx, y, w, h, alpha, radius, bg, True, idx=i)

    def animate_swipe(self, j, d, t0, t1, duration, now):
        self.gfx.screen(self.items[j], force=True)
        self.swipe = {"a": self.morph_i, "b": j, "d": d, "to": t1,
                      "tw": Tween((t0,), (t1,), max(duration, 0.12), SWIPE_EASE, now)}

    def finish_swipe(self):
        sw, self.swipe = self.swipe, None
        if sw["to"] >= 1.0:
            self.morph_i = self.hero = sw["b"]
            self.jump_camera(*self.plane.cell_center(sw["b"]), self.view_scale())
            if self.mode == VIEWER:
                ready = self.players.pop("view_next", None)
                if ready and ready[0] == sw["b"]:
                    self.players["view"] = ready
                    ready[1].play()
                else:
                    if ready:
                        ready[1].close()
                    self.start_video("view", sw["b"], audio=True)
        else:
            self.stop_video("view_next", fade=False)

    def release_drag(self, now):
        """Al soltar: termina el cambio si se arrastró lo suficiente; si no, regresa."""
        p, self.drag = self.drag_vis, None
        vel = self.drag_vel
        self.ignore_swipe_until_gap = True   # la inercia del trackpad ya no mueve nada
        d = 1 if p > 0 else -1
        t = min(abs(p), 1.0)
        j = self.neighbor(self.morph_i, d)
        if j is None:
            if t > 0:
                self.rubber = Tween((p,), (0.0,), 0.4, SWIPE_EASE, now)
            return
        flick = vel * d > 1.2          # soltó con impulso hacia ese lado
        if t > 0.5 or (flick and t > 0.05):
            self.animate_swipe(j, d, t, 1.0, SWIPE_TIME * (1 - t) + 0.15, now)
        elif t > 0:
            self.animate_swipe(j, d, t, 0.0, 0.25 + 0.3 * t, now)

    def page_width(self, a=None, b=None):
        """Distancia entre dos fotos en el visor: juntas, con un espacio corto.
        El desvanecido evita que la que se va se quede asomando."""
        wa = self.viewer_rect(a)[2] if a is not None else self.vw * 0.6
        wb = self.viewer_rect(b)[2] if b is not None else wa
        return (wa + wb) / 2 + 60

    def current_viewer_index(self):
        if self.glide:
            i = self.glide_item(round(self.glide["off"]))
            return i if i is not None else self.morph_i
        if self.swipe and self.swipe["to"] >= 1.0:
            return self.swipe["b"]
        return self.morph_i

    def viewer_rect(self, i):
        s = self.view_scale()
        bw, bh = self.big_dims(self.items[i], VIEWER)
        w, h = bw * s, bh * s
        z = self.immersive_zoom(w, h)
        w, h = w * z, h * z
        return (self.vw - w) / 2, (self.vh - h) / 2, w, h

    def immersive_zoom(self, w, h):
        """Sin controles en pantalla, la foto o el video crece un poco (sin tocar las orillas)."""
        if self.zoom_amt <= 0.001:
            return 1.0
        z_max = min(1.12, (self.vw - 48) / max(w, 1), (self.vh - 28) / max(h, 1))
        return 1.0 + max(0.0, z_max - 1.0) * EASE_IN_OUT(min(1.0, self.zoom_amt))

    def close_viewer(self, now):
        if self.swipe:
            self.finish_swipe()
        if self.glide:                      # se cierra en la foto que se está viendo
            self.glide["target"] = round(self.glide["off"])
            self.glide["off"] = float(self.glide["target"])
            self.finish_glide()
        self.stop_video("view")   # el sonido se desvanece mientras la foto regresa
        self.stop_video("view_next", fade=False)
        self.mode = GRID
        s = self.grid_scale()
        cx, cy = cam.clamp(*self.plane.cell_center(self.morph_i), s, self.plane, self.vw, self.vh)
        self.move_camera(cx, cy, s, C.MORPH_TIME, now)
        self.morph_to(0.0, C.MORPH_TIME, now)
        self.set_anchor()
        self.last_move = now

    # ------------------------------------------------------------------ niveles

    def go_level(self, lvl, now, origin=None):
        if lvl == self.lvl or self.mode != GRID:
            return
        if lvl == YEARS and not self.groups.has_years:
            return
        if lvl == COLLS and not self.groups.coll_list:
            return
        self.lvl_prev, self.lvl = self.lvl, lvl
        self.lvl_tween = Tween((0.0,), (1.0,), LEVEL_TIME, EASE, now)
        self.lvl_origin = origin or (self.vw / 2, self.vh / 2)
        self.level_at = self.edge_at = now
        self.long_until = now + LEVEL_TIME
        self.wheel_acc = 0.0
        self.hover_group = None
        self.hover_i = None
        self.last_move = now

    def to_photos(self, i, now, origin=None, zi=0):
        self.zi = zi
        s = self.grid_scale()
        self.jump_camera(*cam.clamp(*self.plane.cell_center(i), s, self.plane, self.vw, self.vh), s)
        self.hero = i
        self.m = 0.0
        self.go_level(PHOTOS, now, origin)
        self.set_anchor()

    def to_months(self, frac, now, origin=None):
        self.month_frac = self.month_target = frac
        self.month_anchor = cam.Anchor(self.mx, self.my, 0.0, frac)
        self.go_level(MONTHS, now, origin)

    def level_out(self, now, at_mouse=True):
        origin = (self.mx, self.my) if at_mouse and self.inside else None
        if self.lvl == PHOTOS:
            i = self.photo_under_mouse() if at_mouse and self.inside else self.nearest()
            year = self.items[i].date.year
            self.to_months(self.groups.month_scroll_for_year(year, self.vw, self.vh), now, origin)
        elif self.lvl == MONTHS and self.groups.has_years:
            self.go_level(YEARS, now, origin)

    def level_in(self, now, at_mouse=True):
        origin = (self.mx, self.my) if at_mouse and self.inside else None
        g = self.hover_group if at_mouse else None
        if self.lvl == YEARS:
            frac = self.groups.month_scroll_for_year(g.key, self.vw, self.vh) if g else self.month_frac
            self.to_months(frac, now, origin)
        elif self.lvl == MONTHS:
            self.to_photos(g.members[0] if g else self.hero, now, origin)
        elif self.lvl == COLLS:
            if g:
                self.set_filter(g.key)
            self.to_photos(g.members[0] if g else self.hero, now, origin)

    def open_group(self, g, now):
        origin = (self.mx, self.my)
        if g.kind == "year":
            self.to_months(self.groups.month_scroll_for_year(g.key, self.vw, self.vh), now, origin)
        elif g.kind == "month":
            self.to_photos(g.members[0], now, origin)
        elif g.kind == "coll":
            self.set_filter(g.key)
            self.to_photos(g.members[0], now, origin)

    def pick_level(self, lvl, now):
        if lvl == PHOTOS:
            self.to_photos(self.hero, now, zi=self.zi)
        elif lvl == MONTHS:
            year = self.items[self.nearest() if self.lvl == PHOTOS else self.hero].date.year
            self.to_months(self.groups.month_scroll_for_year(year, self.vw, self.vh), now)
        else:
            self.go_level(lvl, now)

    def zoom(self, d, now, at_mouse=True, from_wheel=False):
        if self.mode != GRID:
            return
        can_change_level = not from_wheel or self.gesture_start > self.edge_at
        if self.lvl != PHOTOS:
            if can_change_level:
                (self.level_in if d > 0 else self.level_out)(now, at_mouse)
            return
        zi = min(max(self.zi + d, 0), len(C.ZOOMS) - 1)
        if zi == self.zi:
            if d < 0 and can_change_level:
                self.level_out(now, at_mouse)
            return
        s0, s1 = C.ZOOMS[self.zi], C.ZOOMS[zi]
        self.zi = zi
        if zi == 0:
            self.edge_at = now
        fx, fy = (self.mx, self.my) if at_mouse and self.inside else (self.vw / 2, self.vh / 2)
        nx, ny = cam.zoom_at(self.tcx, self.tcy, s0, s1, fx, fy, self.vw, self.vh)
        nx, ny = cam.clamp(nx, ny, s1, self.plane, self.vw, self.vh)
        self.move_camera(nx, ny, s1, C.ZOOM_TIME, now)
        self.set_anchor()
        self.last_move = now

    # ------------------------------------------------------------------ presentación

    def slide_pool(self):
        pool = [i for i in range(len(self.items)) if self.matches(i)]
        return pool or list(range(len(self.items)))

    def next_index(self):
        pool = self.slide_pool()
        if self.new_keys:          # lo recién subido va primero (en cuanto esté listo)
            idx = {it.key: i for i, it in enumerate(self.items)}
            for k in list(self.new_keys):
                i = idx.get(k)
                if i is None:
                    self.new_keys.remove(k)
                elif self.items[i].ready:
                    self.new_keys.remove(k)
                    if i != self.hero:
                        return i
        if self.settings.memories:
            self.slides_since_memory += 1
            if self.slides_since_memory >= MEM.EVERY:
                mem = self.next_memory(pool)
                if mem is not None:
                    self.slides_since_memory = 0
                    return mem
        if self.settings.shuffle:
            if not self.queue or self.queue[0] not in pool:
                self.queue = [i for i in pool if i != self.hero]
                random.shuffle(self.queue)
            return self.queue.pop(0) if self.queue else self.hero
        # El orden normal sigue su propia cuenta: los recuerdos no lo hacen saltar.
        base = self.seq_pos if self.seq_pos is not None else self.hero
        later = [i for i in pool if i > base]
        self.seq_pos = later[0] if later else pool[0]
        return self.seq_pos

    def next_memory(self, pool):
        """Siguiente foto de "Un día como hoy" (las va rotando sin repetir)."""
        today = date.today()
        if self.memory_day != today:
            self.memory_day, self.memory_queue = today, []
        if not self.memory_queue:
            found = MEM.on_this_day(self.items, pool, today)
            self.memory_queue = [i for i in found if i != self.hero]
            random.shuffle(self.memory_queue)
        while self.memory_queue:
            i = self.memory_queue.pop(0)
            if i in pool and i != self.hero:
                return i
        return None

    def memory_label(self, item):
        if not self.settings.memories:
            return None
        today = date.today()
        if MEM.on_this_day([item], [0], today):
            return MEM.years_ago(item.date, today)
        return None

    # -- Ken Burns ----------------------------------------------------------

    def kb_start(self, i, now):
        style = KB.OFF if self.items[i].is_video else self.settings.kenburns
        self.kb = {k: v for k, v in self.kb.items() if k == self.hero}
        self.kb[i] = (now, KB.Motion(style))

    def kb_active(self, i):
        e = self.kb.get(i)
        return e is not None and e[1].style != KB.OFF

    def kb_rect(self, i, rect, now, amount=1.0):
        e = self.kb.get(i)
        if e is None or e[1].style == KB.OFF:
            return rect
        return KB.apply(rect, *e[1].at(now - e[0]), amount)

    def finish_fade(self):
        if not getattr(self, "_going_back", False):
            self.slide_history = (self.slide_history + [self.hero])[-60:]
        self._going_back = False
        nxt, _ = self.fade
        self.fade = None
        self.hero = self.morph_i = nxt
        self.jump_camera(*self.plane.cell_center(nxt), self.frame_scale())
        self.stop_video("frame", fade=False)
        if "next" in self.players:
            self.players["frame"] = self.players.pop("next")

    def slide_length(self):
        """Las fotos duran SLIDE_TIME; los videos, lo que duran (hasta 1 minuto)."""
        item = self.items[self.hero]
        if item.is_video and self.player_for("frame", self.hero):
            return max(C.SLIDE_TIME, min(item.duration, 60.0)) - 0.6
        return C.SLIDE_TIME

    def frame_step(self, d, now):
        """Flechas en la presentación: siguiente o anterior foto, con su fundido."""
        if self.fade or not self.items:
            return
        if d < 0:
            if not self.slide_history:
                return
            self._next = self.slide_history.pop()
            self._going_back = True
        else:
            self._next = None
        self.last_slide = -1e9      # que cambie ya
        self._next_since = now

    def update_slideshow(self, now):
        if self.fade:
            if self.fade[1].done(now):
                self.finish_fade()
                self.last_slide = now
            return
        current = self.player_for("frame", self.hero)
        ended = current is not None and current.ended
        if self.cam_tween or len(self.items) < 2:
            return
        if now - self.last_slide < self.slide_length() and not ended:
            return
        if self._next is None:
            self._next = self.next_index()
            self._next_since = now
        item = self.items[self._next]
        if not item.ready:
            self._next = None
            return
        if self.gfx.screen(item, force=True) is None:
            return
        self.gfx.backdrop(item, force=True)
        if item.is_video and VID.AVAILABLE:
            if not self.player_for("next", self._next):
                self.start_video("next", self._next)
            p = self.player_for("next", self._next)
            if p and not p.has_frame and now - self._next_since < 1.5:
                return  # espera el primer cuadro para que el fundido no muestre negro
        self.kb_start(self._next, now)
        self.fade = (self._next, Tween((0.0,), (1.0,), C.FADE_TIME, EASE, now))
        self._next = None

    # ------------------------------------------------------------------ eventos

    def debug_event(self, e):
        names = {pygame.MOUSEWHEEL: "rueda", pygame.FINGERDOWN: "DEDO ABAJO", pygame.FINGERUP: "DEDO ARRIBA",
                 pygame.FINGERMOTION: "dedo se mueve", pygame.MOUSEBUTTONDOWN: "clic abajo",
                 pygame.MOUSEBUTTONUP: "clic arriba"}
        if e.type in names:
            extra = ""
            if e.type == pygame.MOUSEWHEEL:
                extra = f" x={getattr(e, 'precise_x', e.x):.2f} y={getattr(e, 'precise_y', e.y):.2f}"
            elif e.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
                extra = f" dedo={e.finger_id} x={e.x:.2f} y={e.y:.2f}"
            print(f"[{time.monotonic():.2f}] {names[e.type]}{extra}", flush=True)

    def handle(self, e, now):
        if self.debug_input:
            self.debug_event(e)
        if e.type == pygame.KEYDOWN and e.key == POWER_KEY:
            self.last_input = now
            if self.dark or self.night > 0.001:
                self.woke = True
            if WIFI.SYSTEM and now - self.resumed_at > 4:   # la tecla que la despertó no cuenta
                if self.power_dlg:
                    self.close_power(now)
                else:
                    self.open_power(now)
            return
        if self.shutting:
            return
        if self.inst:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and self.inst["stage"] in ("info", "confirm", "error"):
                self.inst = None
            elif e.type == pygame.MOUSEMOTION:
                self.mx, self.my = e.pos
                self.show_pointer(True)
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                for rect, fn in reversed(self.hits):
                    if inside(rect, self.mx, self.my):
                        fn(now)
                        break
            return
        if self.scan:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.stop_scan()
            elif e.type == pygame.MOUSEMOTION:
                self.mx, self.my = e.pos
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                for rect, fn in reversed(self.hits):
                    if inside(rect, self.mx, self.my):
                        fn(now)
                        break
            return
        if self.calib:
            if e.type == pygame.KEYDOWN:
                self.finish_calib(now, e.key != pygame.K_ESCAPE)
            elif e.type == pygame.MOUSEBUTTONUP:
                self.finish_calib(now, True)
            return
        if self.power_dlg and e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.close_power(now)
            return
        if e.type == pygame.KEYDOWN and e.key in MEDIA_KEYS:
            self.media_key(MEDIA_KEYS[e.key], now)
            return
        if (self.pw is not None and self.settings_open and self.settings_tab == "wifi"
                and e.type in (pygame.KEYDOWN, pygame.TEXTINPUT)):
            self.type_password(e)       # mientras se escribe la contraseña, las teclas son para eso
            return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_n:
            self.night_force = not self.night_force   # simula la noche (para probar)
            self.woke = False
            return
        if e.type in (pygame.MOUSEMOTION, pygame.MOUSEWHEEL, pygame.MOUSEBUTTONDOWN,
                      pygame.MOUSEBUTTONUP, pygame.KEYDOWN, pygame.FINGERDOWN):
            self.last_input = now
            if self.dark or self.night > 0.001:
                self.woke = True
            if self.night > 0.5:
                # La pantalla está apagada (o casi): el primer toque solo la despierta.
                if e.type == pygame.MOUSEMOTION:
                    self.mx, self.my = e.pos
                self.frame_anchor = None
                self.frame_since = now
                return
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.KEYDOWN:
            self.on_key(e, now)
        elif e.type == pygame.MOUSEMOTION:
            self.on_move(e.pos[0], e.pos[1], now)
        elif e.type == pygame.MOUSEWHEEL:
            if self.mode == VIEWER:
                self.on_swipe(getattr(e, "precise_x", e.x), now)
            else:
                self.on_wheel(getattr(e, "precise_y", e.y), now)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.on_click(now)
        elif e.type == pygame.FINGERDOWN:
            self.touch_seen = True
            self.fingers.add(e.finger_id)
        elif e.type == pygame.FINGERUP:
            self.fingers.discard(e.finger_id)
            if not self.fingers and self.drag is not None:
                self.release_drag(now)
        elif e.type == pygame.WINDOWLEAVE:
            self.inside = False
            self.hover_i = self.hover_group = None
        elif e.type == pygame.WINDOWENTER:
            self.inside = True
        elif e.type in (pygame.WINDOWSIZECHANGED, pygame.WINDOWRESIZED):
            self.fit_to_window()

    def say(self, text, now):
        """Aviso breve arriba al usar un atajo de teclado."""
        self.toast_new = 0
        self.toast = (text, now - 2.0)          # dura menos que los avisos normales

    def shortcut(self, key, now):
        """Atajos de teclado (lista completa con la tecla H). Devuelve True si la tecla era uno."""
        st = self.settings

        def cycle(attr, values, labels, title):
            cur = getattr(st, attr)
            nxt = values[(values.index(cur) + 1) % len(values)] if cur in values else values[0]
            setattr(st, attr, nxt)
            st.save()
            self.say(f"{tr(title)}: {tr(labels[values.index(nxt)])}", now)

        def flip(attr, title):
            setattr(st, attr, not getattr(st, attr))
            st.save()
            self.say(f"{tr(title)}: {tr('Sí') if getattr(st, attr) else tr('No')}", now)

        if key in (pygame.K_b, pygame.K_w, pygame.K_a):
            value, label = {pygame.K_b: ("dark", "Oscuro"), pygame.K_w: ("light", "Claro"),
                            pygame.K_a: ("auto", "Automático")}[key]
            self.set_theme(value)
            st.save()
            self.say(f"{tr('Apariencia')}: {tr(label)}", now)
        elif key == pygame.K_k:
            cycle("kenburns", [KB.OFF, KB.ZOOM, KB.PAN], ["Apagado", "Solo zoom", "Zoom y paneo"], "Ken Burns")
        elif key == pygame.K_r:
            cycle("clock", ["off", "12", "24"], ["Oculto", "12 h", "24 h"], "Reloj")
        elif key == pygame.K_s:
            self.queue = []
            flip("shuffle", "Orden aleatorio")
        elif key == pygame.K_m:
            flip("memories", "Un día como hoy")
        elif key == pygame.K_i:
            flip("show_info", "Fecha y lugar")
        elif key == pygame.K_l:
            flip("auto_brightness", "Brillo automático")
        elif key == pygame.K_e:
            st.language = "en" if st.language == "es" else "es"
            self.apply_language()
            st.save()
            self.say(tr("Idioma") + ": " + dict(I18N.LANGS)[st.language], now)
        elif key == pygame.K_COMMA:
            if self.settings_open:
                self.close_settings(now)
            else:
                self.open_settings(now)
        elif key in (pygame.K_h, pygame.K_SLASH, pygame.K_QUESTION):
            self.help_open = not self.help_open
            self.help_at = now
        elif key == pygame.K_p and self.items:
            if self.mode == FRAME:
                self.enter_grid(now)
            elif self.mode == VIEWER:
                self.go_frame(self.current_viewer_index(), now)
            else:
                self.start_presentation(now)
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4) and self.items:
            lvl = {pygame.K_1: YEARS, pygame.K_2: MONTHS, pygame.K_3: PHOTOS, pygame.K_4: COLLS}[key]
            if self.mode == VIEWER:
                self.close_viewer(now)
            elif self.mode == FRAME:
                self.enter_grid(now)
            if self.mode == GRID:
                if lvl == PHOTOS and self.lvl != PHOTOS:
                    self.level_in(now, at_mouse=False)
                else:
                    self.go_level(lvl, now)
        else:
            return False
        return True

    def on_key(self, e, now):
        if self.help_open:
            self.help_open = False          # cualquier tecla cierra la lista de atajos
            if e.key in (pygame.K_ESCAPE, pygame.K_h, pygame.K_SLASH, pygame.K_QUESTION):
                return
        if not (e.mod & (pygame.KMOD_CTRL | pygame.KMOD_GUI | pygame.KMOD_ALT)) and self.shortcut(e.key, now):
            return
        if e.key == pygame.K_q and not WIFI.SYSTEM:      # en la USB, Q no cierra la app por accidente
            self.running = False
        elif e.key == pygame.K_ESCAPE:
            if self.settings_open:
                self.close_settings(now)
            elif self.mode == VIEWER:
                self.close_viewer(now)
            elif self.mode == GRID and self.lvl != PHOTOS:
                self.level_in(now, at_mouse=False)
            elif self.mode == GRID:
                self.go_frame(self.hover_i if self.hover_i is not None else self.nearest(), now)
        elif e.key == pygame.K_f:
            if self.win.size == pygame.display.get_desktop_sizes()[0]:
                self.win.set_windowed()
            else:
                self.win.set_fullscreen(True)
        elif e.key == pygame.K_SPACE:
            self.toggle_video(now)
        elif e.key == pygame.K_RIGHT:
            if self.mode == FRAME:
                self.frame_step(1, now)
            else:
                self.viewer_step(1, now)
        elif e.key == pygame.K_LEFT:
            if self.mode == FRAME:
                self.frame_step(-1, now)
            else:
                self.viewer_step(-1, now)
        elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.zoom(1, now, at_mouse=False)
        elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom(-1, now, at_mouse=False)

    def on_move(self, x, y, now):
        self.mx, self.my = x, y
        self.inside = True
        self.last_move = now
        self.mouse_at = now                 # el puntero y los controles vuelven a aparecer
        self.keys_drove = False
        if self.mode == FRAME:
            if now - self.frame_since < C.FRAME_MOVE_GRACE:
                return
            if self.frame_anchor is None:
                self.frame_anchor = (x, y)
                return
            if math.hypot(x - self.frame_anchor[0], y - self.frame_anchor[1]) > C.FRAME_MOVE_PX:
                self.enter_grid(now)
            return
        if self.mode != GRID or self.settings_open:
            return
        over_ui = any(inside(r, x, y) for r in self.ui_rects)
        if self.lvl == PHOTOS and self.anchor:
            if self.cam_tween:
                # Mientras la cámara termina su animación (volver del visor, zoom)
                # el mouse no la mueve; al terminar se toma su posición como
                # punto de partida, así no hay salto para "alcanzarlo".
                return
            self.anchor.moved(x, y)
            if now >= self.long_until and not over_ui:
                self.tcx, self.tcy = cam.pan_target(x, y, self.anchor, self.grid_scale(), self.plane, self.vw, self.vh)
        elif self.lvl == MONTHS and self.month_anchor:
            a = self.month_anchor
            a.moved(x, y)
            _x0, _h, ty_max, ty_min = self.groups.months_geometry(self.vw, self.vh)
            if now >= self.long_until and not over_ui and ty_max != ty_min:
                lo, hi = LV.TOP + 82, self.vh - LV.BOTTOM - 82
                self.month_target = cam.pw_map(y, a.my, a.cy, 0.0, 1.0, lo, hi, a.weight, self.vh)

    def on_wheel(self, dy, now):
        if self.mode != GRID or self.settings_open:
            return
        if now - self.wheel_last > GESTURE_GAP:
            self.gesture_start = now
        self.wheel_last = now
        self.last_move = now
        if self.gesture_start <= self.level_at:
            self.wheel_acc = 0.0   # resto de la inercia después de cambiar de nivel
            return
        dy *= self.zoom_sign
        if self.wheel_acc * dy < 0:
            self.wheel_acc = 0.0
        self.wheel_acc += dy
        if self.wheel_acc >= 1.0:
            self.wheel_acc = 0.0
            self.zoom(1, now, from_wheel=True)
        elif self.wheel_acc <= -1.0:
            self.wheel_acc = 0.0
            self.zoom(-1, now, from_wheel=True)

    def on_swipe(self, dx, now):
        """Deslizar con dos dedos en el visor: cada gesto equivale a un clic en
        las flechas (una foto por gesto, con la animación completa)."""
        gap = now - self.wheel_last
        self.wheel_last = now
        self.last_move = now
        if gap > GESTURE_GAP:
            self.ignore_swipe_until_gap = False
            self.swipe_acc = 0.0
        if dx == 0 or self.m_tween or self.ignore_swipe_until_gap:
            return
        if self.swipe_acc * dx < 0:
            self.swipe_acc = 0.0
        self.swipe_acc += dx * self.zoom_sign
        if abs(self.swipe_acc) >= SWIPE_TRIGGER:
            self.viewer_step(1 if self.swipe_acc > 0 else -1, now)
            self.ignore_swipe_until_gap = True   # el resto del gesto (e inercia) no cuenta

    def on_click(self, now):
        self.last_move = now
        for rect, fn in reversed(self.hits):
            if inside(rect, self.mx, self.my):
                fn(now)
                return
        if self.power_dlg:
            self.close_power(now)
            return
        if self.inst:
            return
        if self.settings_open:
            self.close_settings(now)
            return
        if not self.items:
            return
        if self.mode == FRAME:
            self.enter_grid(now)
        elif self.mode == VIEWER:
            self.close_viewer(now)
        elif self.mode == GRID and now >= self.long_until - 0.2:
            if self.lvl == PHOTOS and self.hover_i is not None:
                self.open_viewer(self.hover_i, now)
            elif self.lvl != PHOTOS and self.hover_group is not None:
                self.open_group(self.hover_group, now)

    def set_theme(self, value):
        self.settings.theme = value
        self.apply_theme()

    def apply_language(self):
        I18N.set_lang(self.settings.language)

    def apply_theme(self):
        """Cambia de tema con un fundido gradual de todos los colores."""
        pal = TH.resolve(self.settings.theme)
        if pal.name != self.theme_target:
            self.theme_target = pal.name
            self.theme_anim = (TH.Palette(**dict(T.__dict__)), pal, self.last_t)

    def toggle_video(self, now):
        p = self.player_for("view", self.morph_i)
        if not p or self.mode != VIEWER:
            return
        if p.ended:
            p.restart()
        else:
            p.set_paused(p.is_playing)
        self.last_move = now

    def open_settings(self, now=None):
        now = time.monotonic() if now is None else now
        self.settings_open = True
        self.settings_tw = Tween((self.settings_amt,), (1.0,), SETTINGS_IN, EASE, now)

    def close_settings(self, now=None):
        now = time.monotonic() if now is None else now
        self.settings_open = False
        self.settings_tw = Tween((self.settings_amt,), (0.0,), SETTINGS_OUT, EASE, now)
        self.settings.save()
        if self.pw is not None:      # si se quedó a medio escribir una contraseña
            self.close_password()

    # ------------------------------------------------------------------ biblioteca en vivo

    def poll_events(self, now):
        """Atiende lo que pidió el celular (en este hilo, el de la interfaz)."""
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind, data = event[0], event[1]
            try:
                self.handle_event(kind, data, now)
            finally:
                if len(event) > 2:
                    event[2].set()     # el servidor web espera a que se haya aplicado
        if self.lib and self.lib.version != self.lib_version:
            # Se aplica cuando no estorba: en la presentación, sin fundido en curso.
            if not self.items or (self.mode == FRAME and not self.fade and not self.cam_tween):
                self.lib_version = self.lib.version
                self.set_items(list(self.lib.snapshot), now)

    def handle_event(self, kind, data, now):
        if kind == "added" and self.lib:
            new = self.lib.add_paths(data)
            if new:
                self.new_keys.extend(it.key for it in new)
                # Varias subidas seguidas suman en el mismo aviso.
                recent = self.toast and self.toast_new and now - self.toast[1] < 3.5
                self.toast_new = (self.toast_new if recent else 0) + len(new)
                n = self.toast_new
                text = tr("1 foto nueva") if n == 1 else tr("{n} fotos nuevas", n=n)
                self.toast = (text, now - 0.4 if recent else now)   # si ya se veía, no vuelve a aparecer
        elif kind == "removed" and self.lib:
            self.lib.remove_paths(data)
        elif kind == "moved" and self.lib:
            self.lib.moved(data)
        elif kind == "renamed" and self.lib:
            self.lib.renamed_collection(*data)
        elif kind == "settings":
            self.apply_settings(data, now)
        elif kind == "tzset":
            time.tzset()            # la hora del reloj ya sale en la zona nueva

    def apply_settings(self, changes, now):
        st = self.settings
        for k, v in changes.items():
            setattr(st, k, v)
        if "theme" in changes:
            self.apply_theme()
        if "language" in changes:
            self.apply_language()
        if "shuffle" in changes:
            self.queue = []
        st.save()

    def set_items(self, items, now):
        """Cambia la lista de fotos conservando lo que se está viendo."""
        old = self.items
        key = lambda i: old[i].key if i is not None and 0 <= i < len(old) else None  # noqa: E731
        hero_key = key(self.hero)
        players = [(role, key(i), p) for role, (i, p) in self.players.items()]
        kb = {key(i): v for i, v in self.kb.items()}
        self.items = items
        idx = {it.key: i for i, it in enumerate(items)}
        self.players = {}
        for role, k, p in players:
            if k in idx:
                self.players[role] = (idx[k], p)
            else:
                p.close()
        self.kb = {idx[k]: v for k, v in kb.items() if k in idx}
        self.plane = cam.Plane(*cam.grid_shape(max(1, len(items))), len(items))
        self.groups = LV.Groups(items)
        self.queue, self.memory_queue, self.seq_pos, self._next = [], [], None, None
        self.slide_history = []
        self.hover_i = self.hover_group = None
        if self.coll_filter and not any(it.collection == self.coll_filter for it in items):
            self.coll_filter = None
        if not items:
            self.hero = self.morph_i = 0
            return
        if hero_key in idx:
            self.hero = self.morph_i = idx[hero_key]
            if self.mode == FRAME:
                self.jump_camera(*self.plane.cell_center(self.hero), self.frame_scale())
        else:
            # La foto en pantalla ya no está (o no había ninguna): empieza con otra.
            first = next((i for i, it in enumerate(items) if it.key in self.new_keys), 0)
            self.hero = self.morph_i = first
            if first in self.kb:
                del self.kb[first]
            self.go_frame(first, now)
            self.m, self.m_tween = 1.0, None
            self.jump_camera(*self.plane.cell_center(first), self.frame_scale())

    # ------------------------------------------------------------------ actualización

    def update_idle(self, now):
        """Sin fotos: solo lo que hace falta para Ajustes y el tema."""
        dt = max(0.0, min(0.1, now - self.last_t))
        self.last_t = now
        self.update_brightness(dt, now)
        if self.theme_anim:
            src, dst, t0 = self.theme_anim
            p = min(1.0, (now - t0) / THEME_TIME)
            T.set(TH.blend(src, dst, EASE_IN_OUT(p)) if p < 1 else dst)
            if p >= 1:
                self.theme_anim = None
        if self.settings_tw:
            self.settings_amt = self.settings_tw.value(now)[0]
            if self.settings_tw.done(now):
                self.settings_tw = None
        self.show_pointer(True)

    def update(self, now):
        dt = min(now - self.last_t, 0.1)
        self.last_t = now
        if now - getattr(self, "_theme_check", 0.0) > 30:   # el automático cambia con la hora
            self._theme_check = now
            self.apply_theme()
        if self.theme_anim:
            src, dst, t0 = self.theme_anim
            p = min(1.0, (now - t0) / THEME_TIME)
            T.set(TH.blend(src, dst, EASE_IN_OUT(p)) if p < 1 else dst)
            if p >= 1:
                self.theme_anim = None
        if self.settings_tw:
            self.settings_amt = self.settings_tw.value(now)[0]
            if self.settings_tw.done(now):
                self.settings_tw = None
        if self.cam_tween:
            tx, ty, s = self.cam_tween.value(now)
            self.cx, self.cy, self.s = cam.from_screen(tx, ty, s, self.vw, self.vh)
            if self.cam_tween.done(now):
                self.jump_camera(self.tcx, self.tcy, self.target_s)
                if self.mode == GRID and self.lvl == PHOTOS:
                    self.set_anchor()   # el mouse retoma desde donde está ahora
        elif self.mode == GRID:
            tau = (0.45 + 0.13 * self.zi) / 3.5  # más inercia con zoom alto
            k = 1 - math.exp(-dt / tau)
            self.cx += (self.tcx - self.cx) * k
            self.cy += (self.tcy - self.cy) * k
        self.month_frac += (self.month_target - self.month_frac) * (1 - math.exp(-dt / 0.16))
        if self.m_tween:
            self.m = self.m_tween.value(now)[0]
            if self.m_tween.done(now):
                self.m_tween = None
        if self.lvl_tween and self.lvl_tween.done(now):
            self.lvl_tween = None
        if self.swipe and self.swipe["tw"].done(now):
            self.finish_swipe()
        self.update_glide(dt, now)
        if self.drag is not None:
            prev = self.drag_vis
            self.drag_vis += (self.drag - self.drag_vis) * (1 - math.exp(-dt / 0.035))
            if dt > 0:
                self.drag_vel = 0.7 * self.drag_vel + 0.3 * (self.drag_vis - prev) / dt
            # Sin reporte de dedos (por ejemplo en Linux) se toma como soltado tras una pausa.
            if not self.touch_seen and now - self.wheel_last > RELEASE_PAUSE:
                self.release_drag(now)
        if self.rubber and self.rubber.done(now):
            self.rubber = None

        over_ui = any(inside(r, self.mx, self.my) for r in self.ui_rects)
        can_hover = self.mode == GRID and self.inside and not over_ui and not self.settings_open
        if can_hover and self.lvl == PHOTOS:
            px = self.cx + (self.mx - self.vw / 2) / self.s
            py = self.cy + (self.my - self.vh / 2) / self.s
            hi = self.plane.index_at(px, py, len(self.items))
            if hi != self.hover_i:
                self.hover_i = hi
                self.hover_since = now
        else:
            self.hover_i = None
        # Cada foto crece al entrar el mouse y regresa suave al salir.
        amts = self.hover_amts
        if self.hover_i is not None:
            amts.setdefault(self.hover_i, 0.0)
        for i in list(amts):
            target = 1.0 if i == self.hover_i else 0.0
            tau = 0.08 if target else 0.14
            amts[i] += (target - amts[i]) * (1 - math.exp(-dt / tau))
            if not target and amts[i] < 0.003:
                del amts[i]
        self.hover_amt = amts.get(self.hover_i, 0.0) if self.hover_i is not None else 0.0
        # Vista previa de video al dejar el mouse encima un momento.
        hv = self.hover_i
        want_preview = (hv is not None and self.items[hv].is_video and self.items[hv].ready
                        and now - self.hover_since >= C.PREVIEW_DELAY and now >= self.long_until)
        # Con el mouse encima de un video, se carga en pausa (con sonido) para que
        # al abrirlo empiece de inmediato, sin esperar a que arranque el audio.
        if self.mode == GRID:
            want_warm = (hv is not None and self.items[hv].is_video and self.items[hv].video_ready
                         and now - self.hover_since >= 0.25 and now >= self.long_until)
            if want_warm and not self.player_for("warm", hv):
                self.start_video("warm", hv, audio=True, start_paused=True)
            elif not want_warm and "warm" in self.players:
                self.stop_video("warm", fade=False)
        elif "warm" in self.players:
            self.stop_video("warm", fade=False)
        if want_preview and not self.player_for("preview", hv):
            it = self.items[hv]
            self.start_video("preview", hv, path=it.preview_path, loop=True, max_w=360)
        elif not want_preview and "preview" in self.players:
            self.stop_video("preview", fade=False)
        self.update_players(dt, now)
        self.update_viewer_idle(dt, now)
        if can_hover and self.lvl != PHOTOS:
            self.hover_group = next((g for g, r in reversed(self.cluster_rects) if inside(r, self.mx, self.my)), None)
        else:
            self.hover_group = None

        if self.settings_open:
            self.last_move = now
        vp = self.player_for("view", self.morph_i)
        if self.mode == VIEWER and vp and vp.is_playing:
            self.last_move = now   # no regresa a la presentación mientras se ve un video
        if self.mode == VIEWER and not self.swipe and not self.glide:
            for d in (1, -1):
                j = self.neighbor(self.morph_i, d)
                if j is not None:
                    self.gfx.screen(self.items[j])
        self.update_drift(dt, now)
        self.update_night(dt, now)
        idle_limit = C.VIEWER_IDLE if self.mode == VIEWER else self.settings.idle_seconds
        if self.mode == FRAME:
            if not self.sleeping:
                self.update_slideshow(now)
        elif now - self.last_move > idle_limit:
            if self.mode == VIEWER:
                target = self.morph_i
            elif self.lvl == PHOTOS:
                target = self.hover_i if self.hover_i is not None else self.nearest()
            else:
                target = self.hover_group.members[0] if self.hover_group else self.hero
            self.go_frame(target, now)

    def media_key(self, action, now):
        """Teclas de volumen y brillo, con su píldora arriba a la derecha (como en macOS)."""
        if action.startswith("vol") or action == "mute":
            v = self.volume
            if not v.available:
                return
            if action == "mute":
                v.toggle_mute()
            else:
                v.change(v.STEP if action == "vol_up" else -v.STEP)
            self.show_hud("volume", v.level / 100, v.muted, now)
        else:
            if not self.backlight.available:
                return
            st = self.settings
            step = 1 / 16 if action == "bright_up" else -1 / 16
            if self.auto_brightness_active():
                # Con brillo automático, las teclas ajustan "más o menos" sobre lo automático.
                st.bright_offset = max(-1.0, min(1.0, st.bright_offset + step))
            else:
                st.brightness = max(0.0, min(1.0, st.brightness + step))
            st.save()
            self.bright_fast_until = now + 0.5
            self.show_hud("brightness", self.target_brightness(), False, now)

    def show_hud(self, kind, level, muted, now):
        h = self.hud
        if h and h["kind"] == kind and now - h["last"] < HUD_HOLD + HUD_OUT:
            # Ya se ve: solo se mueve la barra (no vuelve a aparecer).
            if now - h["last"] > HUD_HOLD:      # ya se estaba yendo: vuelve completa, sin animar
                h["start"] = now - HUD_IN
            h.update(level=level, muted=muted, last=now)
        else:
            self.hud = {"kind": kind, "level": level, "muted": muted, "start": now, "last": now,
                        "shown": 0.0 if muted else level}

    def draw_hud(self, now):
        h = self.hud
        if not h:
            return
        if now - h["last"] > HUD_HOLD + HUD_OUT:
            self.hud = None
            return
        a = min(1.0, (now - h["start"]) / HUD_IN, (HUD_HOLD + HUD_OUT - (now - h["last"])) / HUD_OUT)
        a = max(0.0, a)
        target = 0.0 if h["muted"] else h["level"]
        h["shown"] += (target - h["shown"]) * (1 - math.exp(-self.gfx.dt / 0.07))
        g = self.gfx
        w, hh = 250, 46
        x = self.vw - 16 - w
        y = (BAR_H + 10 if self.mode == GRID else 16) - (1 - EASE(a)) * 8
        g.round_rect(x, y, w, hh, (28, 28, 30, 225), a)
        if h["kind"] == "volume":
            name = "speaker_mute" if h["muted"] or h["level"] <= 0 else "speaker"
        else:
            name = "sun"
        g.draw_icon(name, x + 14, y + (hh - 22) / 2, 22, (255, 255, 255), a)
        bx, bw = x + 50, w - 50 - 18
        by = y + hh / 2 - 3
        g.round_rect(bx, by, bw, 6, (255, 255, 255, 60), a, 3)
        if h["shown"] > 0.005:
            g.round_rect(bx, by, max(6, bw * min(1.0, h["shown"])), 6, (255, 255, 255, 255), a, 3)

    def update_viewer_idle(self, dt, now):
        """En el visor la pantalla se queda limpia: al avanzar con flechas o
        deslizando, o tras unos segundos sin mover el mouse, se esconden el
        puntero y los controles (fecha, volver, flechas, barra del video) y la
        foto crece un poco. Moviendo el mouse todo vuelve."""
        if self.mode != VIEWER:
            self.chrome_amt, self.zoom_amt = 1.0, 0.0
            if self.mode == GRID:
                self.show_pointer(True)
            return
        vp = self.player_for("view", self.morph_i)
        paused_video = bool(vp and not vp.is_playing)
        idle = now - self.mouse_at > (2.5 if not paused_video else 1e9)
        clean = (self.keys_drove or idle) and not self.settings_open and self.m >= 0.999
        target = 0.0 if clean else 1.0
        self.chrome_amt += (target - self.chrome_amt) * (1 - math.exp(-dt / (0.10 if not clean else 0.22)))
        # El acercamiento va un poco detrás de los controles: primero se van, luego crece.
        ztarget = 1.0 if clean and self.chrome_amt < 0.5 else 0.0
        self.zoom_amt += (ztarget - self.zoom_amt) * (1 - math.exp(-dt / 0.22))
        self.show_pointer(not clean)

    def update_drift(self, dt, now):
        if now >= self.drift_at:
            self.drift_at = now + 180
            self.drift_target = (random.uniform(-6, 6), random.uniform(-6, 6))
        k = 1 - math.exp(-dt / 3.0)
        self.drift[0] += (self.drift_target[0] - self.drift[0]) * k
        self.drift[1] += (self.drift_target[1] - self.drift[1]) * k

    def update_night(self, dt, now):
        st = self.settings
        if not self.sensor.available and now - getattr(self, "_sensor_check", -1e9) > 10:
            self._sensor_check = now       # la cámara puede aparecer después de arrancar
            self.sensor = NIGHT.light_sensor()
        if self.night_force:
            self.forced_recent = True
        self.dark = self.night_force or (st.night == NIGHT.SCHEDULE and NIGHT.in_schedule(st.night_hours))
        if not self.dark:
            self.woke = False
            target = 0.0
            fast = st.night == NIGHT.NEVER or self.forced_recent
            duration = NIGHT.WAKE_TIME if fast else NIGHT.DIM_TIME   # amanece poco a poco
        elif self.woke and now - self.last_input < NIGHT.STAY_AWAKE:
            target, duration = 0.0, NIGHT.WAKE_TIME
        else:
            target = 1.0
            duration = NIGHT.REDIM_TIME if self.woke else NIGHT.DIM_TIME
            if self.night_force:
                duration = 8.0                  # la simulación pasa en segundos
        step = dt / duration
        if self.night < target:
            self.night = min(target, self.night + step)
        elif self.night > target:
            self.night = max(target, self.night - step)
        if self.night <= 0.0 and not self.night_force:
            self.forced_recent = False
        self.update_brightness(dt, now)
        sleeping = self.night >= 0.999 and st.night_style == "off" and self.mode == FRAME
        if sleeping != self.sleeping:
            self.sleeping = sleeping
            p = self.player_for("frame", self.hero)
            if p:
                p.set_paused(sleeping)
            if not sleeping:
                self.last_slide = now

    # ------------------------------------------------------------------ brillo

    def auto_brightness_active(self):
        return self.settings.auto_brightness and self.sensor.available and self.sensor.ambient() is not None

    def target_brightness(self):
        st = self.settings
        if self.auto_brightness_active():
            # Cuarto oscuro: muy bajo (pero visible); bien iluminado: casi al máximo.
            return max(0.0, min(1.0, 0.06 + 0.9 * self.sensor.ambient() + st.bright_offset))
        return st.brightness

    def update_brightness(self, dt, now):
        st = self.settings
        if st.auto_brightness and self.sensor.available:
            live = self.settings_open and self.settings_tab == "screen"
            self.sensor.update(now, fast=live)
        if self.calib:
            self.update_calib(now)
            return
        target = self.target_brightness()
        tau = 0.06 if now < self.bright_fast_until else 1.5      # lo automático cambia suave
        self.bright += (target - self.bright) * (1 - math.exp(-dt / tau))
        n = self.night
        # De noche baja al mínimo visible de la luz de fondo (sin oscurecer la imagen);
        # con "Apagada", al final la luz de fondo se apaga.
        level = lerp(self.bright, min(self.bright, NIGHT.Backlight.SOFT), n)
        off = max(0.0, (n - 0.7) / 0.3) if st.night_style == "off" else 0.0
        self.backlight.apply(level, off)

    def start_calib(self, now):
        if not self.backlight.available:
            return
        self.close_settings(now)
        self.calib = {"start": now, "hist": []}
        self.show_pointer(False)

    def update_calib(self, now):
        """La luz de fondo baja poco a poco; la persona avisa cuando deja de verse."""
        c, b = self.calib, self.backlight
        t = now - c["start"]
        top, wait, length = 0.30, 2.5, 16.0
        frac = top if t < wait else max(0.0, top * (1 - (t - wait) / length))
        raw = round(b.max * frac)
        b.dim = 0.0
        b.write_raw(raw)
        c["hist"].append((now, raw))
        c["frac"] = frac
        if t > wait + length + 3:
            self.finish_calib(now, False)      # nadie avisó: se deja como estaba

    def finish_calib(self, now, picked):
        c, b, st = self.calib, self.backlight, self.settings
        self.calib = None
        self.bright_fast_until = now + 0.6
        if not picked or now - c["start"] < 2.5:
            return
        # Lo que tarda uno en reaccionar: se toma el valor de un momento antes, y un poquito más.
        earlier = [r for tt, r in c["hist"] if tt <= now - 0.7]
        raw = (earlier[-1] if earlier else c["hist"][-1][1]) + max(1, round(b.max * 0.01))
        st.min_brightness = round(min(0.5, raw / b.max), 4)
        b.floor = st.min_brightness
        st.save()
        self.toast = (tr("Brillo mínimo calibrado"), now)

    def draw_calib(self, now):
        g = self.gfx
        self.ren.draw_color = (128, 128, 128, 255)
        self.ren.clear()
        cx, cy = self.vw / 2, self.vh / 2
        g.label_centered(tr("Calibrar brillo mínimo"), cx, cy - 70, 30, bold=True, color=(255, 255, 255))
        g.label_centered(tr("La pantalla se irá oscureciendo poco a poco."), cx, cy - 10, 17, color=(255, 255, 255))
        g.label_centered(tr("Haz clic o presiona una tecla en cuanto deje de verse."), cx, cy + 18, 17,
                         color=(255, 255, 255))
        g.label_centered(tr("Esc para cancelar"), cx, cy + 70, 13, color=(230, 230, 230))

    # ------------------------------------------------------------------ dibujo

    def layer_state(self, lvl, now):
        """(alpha, escala) de la capa `lvl` durante una transición de nivel."""
        if not self.lvl_tween:
            return (1.0, 1.0) if lvl == self.lvl else (0.0, 1.0)
        t = EASE(self.lvl_tween.progress(now))
        new, old = self.lvl, self.lvl_prev
        if lvl not in (new, old):
            return 0.0, 1.0
        other = old if lvl == new else new
        if RANK[lvl] < RANK[other]:
            k_away = 0.45      # más particular: está "dentro" de la otra
        elif RANK[lvl] > RANK[other]:
            k_away = 2.2       # más general: pasa junto a la cámara
        else:
            k_away = 0.92
        if lvl == new:
            return t, lerp(k_away, 1.0, t)
        return 1.0 - t, lerp(1.0, k_away, t)

    def draw(self, now):
        self._now = now
        g = self.gfx
        if self.sleeping:          # pantalla apagada: nada que dibujar
            self.ren.draw_color = (0, 0, 0, 255)
            self.ren.clear()
            return
        g.begin_frame(now=now)
        self.hits = []
        self.ui_rects = []
        if self.shutting:
            if now - self.shutting["at"] < SHUT_SHRINK:
                self.draw_scene(now)           # la ventana se cierra sobre lo que se veía
            self.draw_shutting(now)
            return
        if self.calib:
            self.draw_calib(now)
            return
        if self.scan:
            self.draw_scan(now)
            return
        amt = self.settings_amt
        if self.night >= 0.999 and amt <= 0.001 and self.items:
            # Noche completa: solo el reloj sobre negro (la escena no se ve).
            self.ren.draw_color = (0, 0, 0, 255)
            self.ren.clear()
            self.draw_night(now)
            self.draw_power(now)
            self.draw_dim()
            return
        if amt > 0.001:
            # Ajustes: la escena se dibuja aparte para desenfocarla detrás del panel.
            scene = self.offscreen("scene", pygame.BLENDMODE_NONE)
            self._blur_n = getattr(self, "_blur_n", 0) + 1
            fresh = amt < 0.999 or self._blur_n % 3 == 0 or "blur4" not in self.offscreen_tex
            if fresh:   # ya abierto, el fondo desenfocado se renueva uno de cada 3 cuadros
                self.ren.target = scene
                self.ren.logical_size = (self.vw, self.vh)
                self.draw_scene(now)
                self.ren.target = None
                self.hits, self.ui_rects = [], []      # con Ajustes abierto, solo cuenta el panel
            scene.alpha = 255
            scene.draw(dstrect=(0, 0, self.vw, self.vh))
            blur = self.blurred(scene) if fresh else self.offscreen_tex["blur4"]
            blur.alpha = int(255 * min(1.0, amt))
            blur.draw(dstrect=(0, 0, self.vw, self.vh))
            g.rect(0, 0, self.vw, self.vh, T.bg, 0.45 * amt)
            self.draw_settings_animated(now, amt)
        else:
            self.draw_scene(now)
        self.draw_night(now)
        self.draw_help(now)
        self.draw_power(now)
        if self.inst:
            self.draw_install(now)
        if self.intro:
            self.draw_intro(now)
        self.draw_dim()

    # ------------------------------------------------------------------ instalar

    def open_install(self, now):
        self.close_settings(now)
        ins = INST.Installer()
        ins.detect()
        self.inst = {"stage": "info", "at": now, "ins": ins, "disk": None}
        self.show_pointer(True)

    def wrap(self, text, size, width, bold=False):
        g = self.gfx
        lines, cur = [], ""
        for word in text.split():
            t = (cur + " " + word).strip()
            if cur and g.tsize(g.text(t, size, T.text, bold))[0] > width:
                lines.append(cur)
                cur = word
            else:
                cur = t
        if cur:
            lines.append(cur)
        return lines

    def draw_install(self, now):
        """Instalar Vitrina en el disco: aviso, confirmación (con cuenta atrás),
        avance y listo. Mientras instala no se puede cerrar."""
        g, it = self.gfx, self.inst
        ins, stage = it["ins"], it["stage"]
        if stage == "run":
            if ins.done:
                it["stage"], it["at"] = "done", now
            elif ins.error and not ins.running:
                it["stage"], it["at"] = "error", now
            stage = it["stage"]
        self.hits, self.ui_rects = [], []
        g.rect(0, 0, self.vw, self.vh, (0, 0, 0), 0.55)
        w = 560
        cx = self.vw / 2
        red = (255, 69, 58)
        body = []           # (texto, tamaño, color, negrita)
        buttons = []        # (texto, acción, estilo)
        title = ""
        if stage == "info":
            title = tr("Instalar Vitrina en esta Mac")
            body.append((tr("Vitrina quedará en el disco de la Mac y arrancará sola, sin la USB. "
                            "Las fotos, el WiFi y los ajustes de ahora se pasan a la instalación."),
                         14, T.text_secondary, False))
            if ins.disks is None:
                body.append((tr("Buscando el disco…"), 14, T.text, True))
            elif not ins.disks:
                body.append((tr("No se encontró un disco interno donde instalar."), 14, red, True))
            else:
                dev, size, model, keep = ins.disks[0]
                it["disk"] = ins.disks[0]
                body.append((tr("Disco: {m} · {s}", m=model or dev, s=INST.human_size(size)), 14, T.text, True))
                if keep:
                    body.append((tr("Se borrará macOS con todos sus programas, documentos y fotos. "
                                    "No se puede deshacer."), 14, red, True))
                    body.append((tr("Se conserva la recuperación de macOS (⌘R al prender) por si algún día "
                                    "quieres volver a instalarlo."), 13, T.text_secondary, False))
                else:
                    body.append((tr("Se borrará TODO lo que tiene este disco: macOS, programas, documentos y fotos. "
                                    "No se puede deshacer."), 14, red, True))
            buttons.append((tr("Cancelar"), "close", "normal"))
            if ins.disks:
                buttons.append((tr("Continuar"), "confirm", "active"))
        elif stage == "confirm":
            title = tr("¿Borrar el disco e instalar?")
            dev, size, model, _keep = it["disk"]
            body.append((tr("Último aviso: se borrará {m} ({s}) y no habrá forma de recuperar lo que tiene.",
                            m=model or dev, s=INST.human_size(size)), 14, T.text_secondary, False))
            body.append((tr("Deja la Mac conectada a la corriente. Tarda unos minutos."), 14, T.text_secondary, False))
            left = 5 - int(now - it["at"])
            buttons.append((tr("Cancelar"), "close", "normal"))
            if left > 0:
                buttons.append((tr("Borrar e instalar ({n})", n=left), None, "disabled"))
            else:
                buttons.append((tr("Borrar e instalar"), "go", "danger"))
        elif stage == "run":
            title = tr("Instalando Vitrina…")
            step = tr("Paso {n} de {t} · {s}", n=max(1, ins.step), t=ins.total, s=tr(ins.step_text) if ins.step_text
                      else tr("Empezando"))
            body.append((step, 14, T.text, True))
            body.append(("__bar__", 0, None, False))
            body.append((tr("No apagues la Mac ni quites la USB."), 13, T.text_secondary, False))
        elif stage == "done":
            title = tr("Listo")
            body.append((tr("Vitrina quedó instalada. Quita la USB y reinicia: arrancará sola desde el disco."),
                         14, T.text_secondary, False))
            buttons.append((tr("Reiniciar"), "reboot", "active"))
        else:
            title = tr("No se pudo instalar")
            body.append((ins.error or "?", 14, red, True))
            body.append((tr("Puedes intentarlo otra vez. Los detalles están en el Diagnóstico del celular."),
                         13, T.text_secondary, False))
            buttons.append((tr("Cerrar"), "close", "normal"))
        # Medidas
        laid = []
        for text, size, color, bold in body:
            if text == "__bar__":
                laid.append(("__bar__", 0, None, False, 34))
                continue
            for ln in self.wrap(text, size, w - 64, bold):
                laid.append((ln, size, color, bold, size + 8))
            laid.append(("", 0, None, False, 10))
        logo_h = 70 if stage == "run" else 0
        h = 32 + logo_h + 34 + 16 + sum(r[4] for r in laid) + (84 if buttons else 18)
        x, y = cx - w / 2, (self.vh - h) / 2
        g.round_rect(x, y, w, h, T.panel, 1.0, 22)
        self.hits.append(((x, y, w, h), lambda now: None))
        yy = y + 32
        if stage == "run":                  # el logo respirando mientras instala
            sq = g.shape(round(SPL.SQ * 2), round(SPL.SQ * 2), 14)
            k = 0.6
            for sx, sy, size in SPL.square_rects(self.vw, self.vh, now - it["at"]):
                wx, wy = SPL.logo_origin(self.vw, self.vh)
                px = cx - 42 * k + (sx - wx) * k
                py = yy + (sy - wy) * k
                sq.color = T.text
                sq.alpha = 255
                sq.draw(dstrect=(px, py, size * k, size * k))
            yy += logo_h
        g.label_centered(title, cx, yy, 20, bold=True)
        yy += 50
        for text, size, color, bold, lh in laid:
            if text == "__bar__":
                bw = w - 64
                g.round_rect(x + 32, yy + 8, bw, 8, T.button, 1.0, 4)
                p = ins.progress
                shown = it.setdefault("shown", 0.0)
                it["shown"] = shown + (p - shown) * (1 - math.exp(-g.dt / 0.4))
                if it["shown"] > 0.005:
                    g.round_rect(x + 32, yy + 8, max(8, bw * it["shown"]), 8, T.text, 1.0, 4)
            elif text:
                g.label_centered(text, cx, yy, size, bold=bold, color=color)
            yy += lh
        if buttons:
            bw = (w - 64 - 12 * (len(buttons) - 1)) / len(buttons)
            bx = x + 32
            by = y + h - 32 - 44
            for label, action, style in buttons:
                bg = {"active": T.active_bg, "danger": red + (255,), "disabled": T.button}.get(style, T.button)
                fg = {"active": T.active_fg, "danger": (255, 255, 255), "disabled": T.text_secondary}.get(style, T.text)
                g.round_rect(bx, by, bw, 44, bg, 1.0)
                g.label_centered(label, bx + bw / 2, by + 13, 14, bold=True, color=fg)
                if action:
                    self.hit((bx, by, bw, 44), lambda now, a=action: self.install_action(a, now))
                bx += bw + 12

    def install_action(self, action, now):
        it = self.inst
        if action == "close":
            self.inst = None
        elif action == "confirm":
            it["stage"], it["at"] = "confirm", now
        elif action == "go":
            it["stage"], it["at"] = "run", now
            self.close_all_videos()
            it["ins"].start(it["disk"][0])
        elif action == "reboot":
            self.inst = None
            self.power_action("reboot", now)

    # ------------------------------------------------------------------ arranque

    LOGO_SQ, LOGO_STEP = SPL.SQ, SPL.STEP

    def logo_origin(self):
        """Esquina de la ventana del logo: el mismo lugar que en el arranque de Linux."""
        return SPL.logo_origin(self.vw, self.vh)

    def logo_scale(self, k, t):
        return SPL.logo_scale(k, t)

    def draw_shutting(self, now):
        """Apagar: el arranque al revés. La pantalla se cierra en una ventanita
        blanca, se separa en los 4 cuadros, aparece "Vitrina OS" y los cuadros
        siguen respirando hasta que la Mac se apaga."""
        sh, g = self.shutting, self.gfx
        t = now - sh["at"]
        S = SPL.SQ
        wx, wy = SPL.logo_origin(self.vw, self.vh)
        cx, cy = wx + 42, wy + 42
        sq = g.shape(round(S * 2), round(S * 2), 14)
        white, black = (255, 255, 255), (0, 0, 0)
        if t < SHUT_SHRINK:
            p = t / SHUT_SHRINK
            big = math.hypot(self.vw, self.vh) * 1.15
            size = lerp(big, S, ENTER_EASE(p))
            x0, y0 = math.floor(cx - size / 2), math.floor(cy - size / 2)
            x1, y1 = math.ceil(cx + size / 2), math.ceil(cy + size / 2)
            g.rect(0, 0, self.vw, max(0, y0), black)
            g.rect(0, y1, self.vw, max(0, self.vh - y1), black)
            g.rect(0, y0, max(0, x0), y1 - y0, black)
            g.rect(x1, y0, max(0, self.vw - x1), y1 - y0, black)
            wa = max(0.0, (p - 0.65) / 0.35)          # al final ya es la ventanita blanca
            if wa > 0.003:
                g.rect(x0, y0, x1 - x0, y1 - y0, black, wa)
                sq.color, sq.alpha = white, int(255 * wa)
                sq.draw(dstrect=(x0, y0, x1 - x0, y1 - y0))
            return
        self.ren.draw_color = (0, 0, 0, 255)
        self.ren.clear()
        t2 = t - SHUT_SHRINK
        homes = SPL.square_rects(self.vw, self.vh, max(0.0, t2 - SHUT_SPLIT))
        if t2 < SHUT_SPLIT:                           # se separa en 4
            e = EASE_IN_OUT(t2 / SHUT_SPLIT)
            for x, y, size in homes:
                hx = lerp(cx - S / 2, x, e)
                hy = lerp(cy - S / 2, y, e)
                hs = lerp(S, size, e)
                sq.color, sq.alpha = white, 255
                sq.draw(dstrect=(hx, hy, hs, hs))
            name_a = max(0.0, (t2 / SHUT_SPLIT - 0.45) / 0.55)
        else:                                         # y respira hasta apagarse
            for x, y, size in homes:
                sq.color, sq.alpha = white, 255
                sq.draw(dstrect=(x, y, size, size))
            name_a = 1.0
        if name_a > 0.01:
            title = g.text("Vitrina", 22, white, True)
            sub = g.text("OS", 22, (142, 142, 147), False)
            w1, h1 = g.tsize(title)
            w2, _ = g.tsize(sub)
            xx = self.vw / 2 - (w1 + 6 + w2) / 2
            for tex, px, ww in ((title, xx, w1), (sub, xx + w1 + 6, w2)):
                tex.alpha = int(255 * name_a)
                tex.draw(dstrect=(px, wy + 84 + 28, ww, h1))
        # Dos vueltas completas del logo antes de pedirle a la Mac que se apague.
        if not sh["sent"] and t > SHUT_SHRINK + SHUT_SPLIT + 2 * SPL.PERIOD:
            sh["sent"] = True
            WIFI.power(sh["action"])

    def draw_intro(self, now):
        """Logo de Vitrina: los 4 cuadros "respiran" mientras carga; al estar
        lista, se juntan al centro en una sola ventanita que crece hasta llenar
        la pantalla y deja ver la galería (o el código para el celular)."""
        it, g = self.intro, self.gfx
        t = now - it["start"]
        if it["phase"] == "load":
            # Al menos dos vueltas completas (aunque ya haya cargado), y la entrada
            # empieza justo al terminar una vuelta, para que no se corte a la mitad.
            ready = not self.items or self.items[self.hero].ready or t > 10
            if ready and "end" not in it:
                it["end"] = max(2, math.ceil(t / SPL.PERIOD)) * SPL.PERIOD
            if "end" in it and t >= it["end"]:
                it["phase"], it["at"] = "merge", now
                it["scales"] = [self.logo_scale(k, t) for k in range(4)]
        sq = g.shape(round(self.LOGO_SQ * 2), round(self.LOGO_SQ * 2), 14)
        wx, wy = self.logo_origin()
        S, D = self.LOGO_SQ, self.LOGO_STEP
        homes = [(wx, wy), (wx + D, wy), (wx + D, wy + D), (wx, wy + D)]
        center = (wx + 42 - S / 2, wy + 42 - S / 2)
        white = (255, 255, 255)
        if it["phase"] in ("load", "merge"):
            self.ren.draw_color = (0, 0, 0, 255)
            self.ren.clear()                       # todo negro: el logo va solo
            m = 0.0 if it["phase"] == "load" else min(1.0, (now - it["at"]) / 0.7)
            e = EASE_IN_OUT(m)
            for k in range(4):
                sc = self.logo_scale(k, t) if it["phase"] == "load" else lerp(it["scales"][k], 1.0, e)
                size = S * sc
                hx, hy = homes[k]                  # cada cuadro crece desde su propio centro
                x, y = hx + (S - size) / 2, hy + (S - size) / 2
                if it["phase"] == "merge":
                    x = lerp(x, center[0], e)
                    y = lerp(y, center[1], e)
                sq.color = white
                sq.alpha = 255
                sq.draw(dstrect=(x, y, size, size))
            name_a = 1.0 if it["phase"] == "load" else max(0.0, 1 - m / 0.55)
            if name_a > 0.01:
                title = g.text("Vitrina", 22, white, True)
                sub = g.text("OS", 22, (142, 142, 147), False)
                w1, h1 = g.tsize(title)
                w2, _ = g.tsize(sub)
                x0 = self.vw / 2 - (w1 + 6 + w2) / 2
                for tex, xx, ww in ((title, x0, w1), (sub, x0 + w1 + 6, w2)):
                    tex.alpha = int(255 * name_a)
                    tex.draw(dstrect=(xx, wy + 84 + 28, ww, h1))
            if it["phase"] == "merge" and m >= 1.0:
                it["phase"], it["at"] = "enter", now
            return
        # Entrar: la ventanita crece hasta cubrir la pantalla; por dentro se ve la app.
        p = min(1.0, (now - it["at"]) / 1.0)
        e = ENTER_EASE(p)
        big = math.hypot(self.vw, self.vh) * 1.15
        size = lerp(S, big, e)
        cx, cy = center[0] + S / 2, center[1] + S / 2
        x, y = cx - size / 2, cy - size / 2
        black = (0, 0, 0)
        # Fuera de la ventanita: negro (en píxeles enteros, sin rendijas entre piezas).
        x0, y0 = math.floor(x), math.floor(y)
        x1, y1 = math.ceil(x + size), math.ceil(y + size)
        g.rect(0, 0, self.vw, max(0, y0), black)
        g.rect(0, y1, self.vw, max(0, self.vh - y1), black)
        g.rect(0, y0, max(0, x0), y1 - y0, black)
        g.rect(x1, y0, max(0, self.vw - x1), y1 - y0, black)
        x, y, size = x0, y0, x1 - x0
        # Dentro: primero blanca (como el logo) y se vuelve transparente.
        wa = max(0.0, 1 - p / 0.35)
        if wa > 0.003:
            g.rect(x, y, size, size, black, wa)
            sq.color = white
            sq.alpha = int(255 * wa)
            sq.draw(dstrect=(x, y, size, size))
        if p >= 1.0:
            self.intro = None

    HELP = [
        ("Presentación", [("P", "Empezar o salir de la presentación"), ("← →", "Foto anterior o siguiente"),
                          ("Espacio", "Pausar o seguir el video"), ("Esc", "Volver")]),
        ("Fotos", [("1 2 3 4", "Años, Meses, Fotos, Colecciones"), ("+ −", "Acercar o alejar")]),
        ("Ajustes rápidos", [("B · W · A", "Apariencia: oscuro, claro o automático"),
                             ("K", "Ken Burns"), ("R", "Reloj"), ("I", "Fecha y lugar"),
                             ("M", "Un día como hoy"), ("S", "Orden aleatorio"),
                             ("L", "Brillo automático"), ("N", "Modo noche ahora"),
                             ("E", "Español o inglés"), (",", "Ajustes"), ("H", "Esta lista")]),
    ]

    def draw_help(self, now):
        target = 1.0 if self.help_open else 0.0
        self.help_amt += (target - self.help_amt) * (1 - math.exp(-self.gfx.dt / 0.07))
        if self.help_amt < 0.01:
            self.help_amt = 0.0 if not self.help_open else self.help_amt
            return
        a = self.help_amt
        g = self.gfx
        g.rect(0, 0, self.vw, self.vh, (0, 0, 0), 0.4 * a)
        rows = sum(len(items) + 1 for _, items in self.HELP)
        w, h = 520, 70 + rows * 27 + 20
        sc = lerp(0.95, 1.0, EASE(a))
        x, y = (self.vw - w * sc) / 2, (self.vh - h * sc) / 2
        g.round_rect(x, y, w * sc, h * sc, T.panel, a, 22)
        if a < 0.6:
            return
        ta = (a - 0.6) / 0.4
        x, y = (self.vw - w) / 2, (self.vh - h) / 2
        g.label(tr("Atajos de teclado"), x + 28, y + 24, 20, ta, bold=True)
        yy = y + 70
        for title, items in self.HELP:
            g.label(tr(title).upper(), x + 28, yy, 11, ta, bold=True, color=T.text_secondary)
            yy += 27
            for keys, what in items:
                kt = g.text(keys, 13, T.text, True)
                kw, _ = g.tsize(kt)
                g.round_rect(x + 28, yy - 4, kw + 18, 24, T.button, ta, 7)
                g.label(keys, x + 37, yy, 13, ta, bold=True)
                g.label(tr(what), x + 150, yy, 14, ta)
                yy += 27
        self.hits = [((0, 0, self.vw, self.vh), lambda now: setattr(self, "help_open", False))]

    def draw_dim(self):
        """Brillo por debajo del mínimo de la luz de fondo: se oscurece la imagen."""
        d = self.backlight.dim
        if d > 0.003:
            self.gfx.rect(0, 0, self.vw, self.vh, (0, 0, 0), d)

    # ------------------------------------------------------------------ apagar

    def open_power(self, now):
        if self.pw is not None:
            self.close_password()
        self.power_dlg = {"start": now}
        self.show_pointer(True)

    def close_power(self, now):
        self.power_dlg = None

    def power_action(self, action, now):
        self.power_dlg = None
        self.power_amt = 0.0
        if action in ("poweroff", "reboot"):
            # La app se queda mostrando el logo hasta el final (sin textos de Linux).
            self.close_all_videos()
            self.shutting = {"at": now, "action": action, "sent": False}
            self.show_pointer(False)
            return
        if action == "suspend":
            for _i, p in list(self.players.values()):
                try:
                    p.set_paused(True)
                except Exception:      # noqa: BLE001
                    pass
        WIFI.power(action)

    def draw_power(self, now):
        """¿Apagar la Vitrina? Reposo, apagar, reiniciar o cancelar. Aparece
        creciendo un poco, como las ventanas de Apple."""
        target = 1.0 if self.power_dlg else 0.0
        self.power_amt += (target - self.power_amt) * (1 - math.exp(-self.gfx.dt / 0.07))
        if target == 0.0 and self.power_amt < 0.01:
            self.power_amt = 0.0
            return
        a = self.power_amt
        g = self.gfx
        self.hits, self.ui_rects = [], []           # mientras se ve, solo cuenta esta ventana
        g.rect(0, 0, self.vw, self.vh, (0, 0, 0), 0.45 * a)
        w = 340
        title, sub = tr("¿Apagar la Vitrina?"), tr("En reposo, la pantalla se apaga y gasta casi nada. Despierta al abrir la tapa o con cualquier tecla.")
        lines, cur = [], ""
        for word in sub.split():
            t = (cur + " " + word).strip()
            if cur and g.tsize(g.text(t, 13, T.text_secondary))[0] > w - 56:
                lines.append(cur)
                cur = word
            else:
                cur = t
        lines.append(cur)
        bh, gap = 44, 10
        h = 28 + 26 + 10 + len(lines) * 18 + 22 + 4 * bh + 3 * gap + 24
        sc = lerp(0.94, 1.0, EASE(a))
        cx, cy = self.vw / 2, self.vh / 2
        w2, h2 = w * sc, h * sc
        x, y = cx - w2 / 2, cy - h2 / 2
        g.round_rect(x, y, w2, h2, T.panel, a, 22)
        if a < 0.6 or not self.power_dlg:
            return
        ta = (a - 0.6) / 0.4
        x, y = cx - w / 2, cy - h / 2
        self.hits.append(((x, y, w, h), lambda now: None))     # clic dentro: no cierra
        yy = y + 28
        g.label_centered(title, cx, yy, 18, ta, bold=True)
        yy += 36
        for ln in lines:
            g.label_centered(ln, cx, yy, 13, ta, color=T.text_secondary)
            yy += 18
        yy += 22
        for label, action, active in ((tr("Reposo"), "suspend", False), (tr("Apagar"), "poweroff", True),
                                      (tr("Reiniciar"), "reboot", False), (tr("Cancelar"), None, False)):
            bx = x + 28
            g.round_rect(bx, yy, w - 56, bh, T.active_bg if active else T.button, ta)
            g.label_centered(label, cx, yy + (bh - 18) / 2, 14, ta, bold=True,
                             color=T.active_fg if active else T.text)
            fn = (lambda now: self.close_power(now)) if action is None else \
                (lambda now, act=action: self.power_action(act, now))
            self.hit((bx, yy, w - 56, bh), fn)
            yy += bh + gap

    def offscreen(self, name, blend, scale=1):
        """Textura de dibujo fuera de pantalla, al tamaño real de la ventana / scale."""
        size = (max(1, round(self.vw * self.gfx.dpi / scale)), max(1, round(self.vh * self.gfx.dpi / scale)))
        tex = self.offscreen_tex.get(name)
        if tex is None or (tex.width, tex.height) != size:
            tex = Texture(self.ren, size, target=True)
            tex.blend_mode = blend
            self.offscreen_tex[name] = tex
        return tex

    def blurred(self, scene, name="blur", steps=4, smooth_up=False):
        """Desenfoque barato: la escena se reduce a la mitad varias veces
        (cada paso promedia píxeles) y luego se estira suave. Con smooth_up se
        vuelve a agrandar en pasos (más parejo: manchas de color sin cuadritos)."""
        src = scene
        for k in range(1, steps + 1):
            dst = self.offscreen(f"{name}{k}", pygame.BLENDMODE_NONE, 2 ** k)
            self.ren.target = dst
            src.alpha = 255
            src.draw(dstrect=(0, 0, dst.width, dst.height))
            src = dst
        if smooth_up:
            for k in range(steps - 1, max(1, steps - 3), -1):
                dst = self.offscreen(f"{name}up{k}", pygame.BLENDMODE_NONE, 2 ** k)
                self.ren.target = dst
                src.alpha = 255
                src.draw(dstrect=(0, 0, dst.width, dst.height))
                src = dst
        self.ren.target = None
        src.blend_mode = pygame.BLENDMODE_BLEND
        return src

    def draw_settings_animated(self, now, amt):
        """El panel aparece creciendo un poco y se desvanece al cerrarse, como
        las ventanas de Apple."""
        n_hits, n_rects = len(self.hits), len(self.ui_rects)
        if amt >= 0.999:
            self.draw_settings(now)
        else:
            panel = self.offscreen("panel", pygame.BLENDMODE_BLEND)
            self.ren.target = panel
            self.ren.logical_size = (self.vw, self.vh)
            self.ren.draw_color = (0, 0, 0, 0)
            self.ren.clear()
            self.draw_settings(now)
            self.ren.target = None
            sc = lerp(0.92 if self.settings_open else 0.96, 1.0, amt)
            cx, cy = self.vw / 2, self.vh / 2
            panel.alpha = int(255 * min(1.0, amt * 1.3))
            panel.draw(dstrect=(cx - cx * sc, cy - cy * sc, self.vw * sc, self.vh * sc))
        if not self.settings_open:     # cerrándose: ya no recibe clics
            del self.hits[n_hits:]
            del self.ui_rects[n_rects:]

    def draw_scene(self, now):
        g = self.gfx
        frame_amt = self.m if self.big_kind == FRAME else 0.0
        bg = tuple(round(lerp(a, b, frame_amt)) for a, b in zip(T.bg, C.BG_FRAME))
        self.ren.draw_color = (*bg, 255)
        self.ren.clear()
        if not self.items:
            self.draw_empty_library()
            with TH.using(TH.DARK):
                self.draw_toast(now)
            return
        hero = self.items[self.morph_i]
        if frame_amt > 0 and hero.ready and hero.vertical:
            back = g.backdrop(hero, force=True)
            if back:
                g.image(back, -40, -40, self.vw + 80, self.vh + 80, alpha=frame_amt)

        alpha, k = self.layer_state(PHOTOS, now)
        if alpha > 0.003:
            ox, oy = self.lvl_origin
            tx, ty, s = cam.to_screen(self.cx, self.cy, self.s, self.vw, self.vh)
            tx, ty, s = ox + (tx - ox) * k, oy + (ty - oy) * k, s * k
            others = (1.0 - self.m) if self.big_kind in (FRAME, VIEWER) else 1.0
            if others * alpha > 0.003:
                self.draw_tiles(tx, ty, s, others * alpha, bg)
            if self.glide:
                self.draw_glide(bg)
            elif self.swipe or self.drag is not None or self.rubber:
                self.draw_swipe(now, bg)
            elif self.lvl == PHOTOS and not self.lvl_tween:
                self.draw_morph(tx, ty, s, bg)
        self.cluster_rects = []
        for lvl in (MONTHS, YEARS, COLLS):
            alpha, k = self.layer_state(lvl, now)
            if alpha > 0.003:
                self.draw_level(lvl, now, alpha, LV.View(k, *self.lvl_origin), bg)
        if self.fade:
            self.draw_fade(now)
        self.draw_chrome(now)
        self.draw_toast(now)
        self.draw_hud(now)

    def draw_tiles(self, tx, ty, s, alpha, bg):
        g = self.gfx
        pitch = C.CELL + C.GAP
        c0 = max(0, int((-tx / s) // pitch) - 2)
        c1 = min(self.plane.cols - 1, int(((self.vw - tx) / s) // pitch) + 1)
        r0 = max(0, int((-ty / s) // pitch) - 1)
        r1 = min(self.plane.rows - 1, int(((self.vh - ty) / s) // pitch) + 1)
        n = len(self.items)
        radius = C.RADIUS_GRID * s
        skip_morph = self.m > 0.001 and self.lvl == PHOTOS and not self.lvl_tween
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                i = row * self.plane.cols + col
                if i >= n or (i == self.morph_i and skip_morph):
                    continue
                if i in self.hover_amts:
                    continue            # las levantadas van encima, después
                a = alpha * (1.0 if self.matches(i) else 0.14)
                cx, cy = self.plane.cell_center(i)
                x, y = tx + s * (cx - C.CELL / 2), ty + s * (cy - C.CELL / 2)
                self.draw_tile(self.items[i], x, y, C.CELL * s, C.CELL * s, a, radius, bg, idx=i, badge=True)
        for i, amt in sorted(self.hover_amts.items(), key=lambda kv: kv[1]):
            if i >= n or (i == self.morph_i and skip_morph):
                continue
            cx, cy = self.plane.cell_center(i)
            k = 1 + 0.07 * amt
            w = C.CELL * s * k
            x = tx + s * cx - w / 2
            y = ty + s * cy - w / 2
            a = alpha * (1.0 if self.matches(i) else 0.14)
            self.draw_tile(self.items[i], x, y, w, w, a, radius * k, bg, idx=i, badge=True)

    def draw_tile(self, item, x, y, w, h, alpha, radius, bg, prefer_screen=False, idx=None, badge=False, snap=True):
        g = self.gfx
        vtex, va = self.video_layer(idx, self._now) if idx is not None and item.is_video else (None, 0.0)
        tex = vtex if va >= 1.0 else None
        if tex is None and prefer_screen:
            tex = g.screen(item, force=True)
        if tex is None:
            tex = g.thumb(item)
        if tex is None:
            g.rect(x, y, w, h, T.placeholder, alpha)
            g.corners(x, y, w, h, radius, bg, alpha)
            return
        g.image(tex, x, y, w, h, alpha, radius, bg, snap)
        if vtex is not None and 0 < va < 1.0:   # el video aparece suave sobre su portada
            g.image(vtex, x, y, w, h, alpha * va, radius, bg, snap)
        if badge and item.is_video and w > 90:
            self.draw_video_badge(item, x, y, w, h, alpha, idx)

    def draw_video_badge(self, item, x, y, w, h, alpha, idx):
        g = self.gfx
        p = self.player_for("preview", idx)
        if p and p.has_frame:
            dur = p.duration or 0
            frac = (p.position / dur) if dur else 0
            g.rect(x, y + h - 3, w, 3, (255, 255, 255), 0.25 * alpha)
            g.rect(x, y + h - 3, w * min(frac, 1.0), 3, (255, 255, 255), alpha)
            return
        t = g.text(item.duration_text, 11, C.TEXT, True)
        tw, th = g.tsize(t)
        bw, bh = tw + 28, 20
        bx, by = x + 9, y + h - 9 - bh
        g.round_rect(bx, by, bw, bh, (0, 0, 0, 150), alpha)
        cy = by + bh / 2
        g.triangle(((bx + 8, cy - 4), (bx + 8, cy + 4), (bx + 15, cy)), C.TEXT, alpha)
        t.alpha = int(255 * alpha)
        t.draw(dstrect=(bx + 20, by + (bh - th) / 2, tw, th))

    def draw_morph(self, tx, ty, s, bg):
        if self.m <= 0.001 and self.mode == GRID:
            return
        item = self.items[self.morph_i]
        bw, bh = self.big_dims(item, self.big_kind)
        w, h = lerp(C.CELL, bw, self.m), lerp(C.CELL, bh, self.m)
        pcx, pcy = self.plane.cell_center(self.morph_i)
        x, y = tx + s * (pcx - w / 2), ty + s * (pcy - h / 2)
        big_r = 0.0 if self.big_kind == FRAME else C.RADIUS_VIEW
        radius = lerp(C.RADIUS_GRID, big_r, self.m) * s
        rect, snap = (x, y, w * s, h * s), True
        if self.big_kind == VIEWER and self.mode == VIEWER and self.zoom_amt > 0.001:
            rx, ry, rw, rh = rect
            z = self.immersive_zoom(rw, rh)
            rect = (rx + rw / 2 - rw * z / 2, ry + rh / 2 - rh * z / 2, rw * z, rh * z)
            snap = False
        if self.big_kind == FRAME and self.kb_active(self.morph_i):
            rect = self.kb_rect(self.morph_i, rect, self._now, amount=self.m)
            snap = self.m < 0.999       # quieto en pantalla: posiciones finas, sin saltitos
        self.draw_tile(item, *rect, 1.0, radius, bg, rect[2] > C.THUMB_SHORT_SIDE * 1.3,
                       idx=self.morph_i, badge=self.m < 0.3, snap=snap)

    def draw_swipe(self, now, bg):
        """Las fotos van una junto a otra como páginas (como en Fotos del iPhone):
        la que se va sale completa por un lado y la nueva entra por el otro."""
        radius = C.RADIUS_VIEW * self.view_scale()
        if self.swipe:
            a, b, d = self.swipe["a"], self.swipe["b"], self.swipe["d"]
            t = self.swipe["tw"].value(now)[0]
        else:
            p = self.drag_vis if self.drag is not None else self.rubber.value(now)[0]
            a, d = self.morph_i, (1 if p > 0 else -1)
            b = self.neighbor(a, d)
            t = abs(p)
            if b is None:  # sin foto de ese lado: se mueve con resistencia
                x, y, w, h = self.viewer_rect(a)
                self.draw_tile(self.items[a], x - p * self.page_width(a), y, w, h, 1.0, radius, bg, True, idx=a)
                return
        page = self.page_width(a, b)
        # La que sale se desvanece y la que entra aparece conforme avanzan.
        for i, off, alpha in ((a, -d * t * page, 1.0 - t), (b, d * (1 - t) * page, t)):
            x, y, w, h = self.viewer_rect(i)
            if alpha <= 0.01 or x + off + w < 0 or x + off > self.vw:
                continue
            self.draw_tile(self.items[i], x + off, y, w, h, alpha, radius, bg, True, idx=i)

    def draw_level(self, lvl, now, alpha, view, bg):
        g, items = self.gfx, self.items
        interactive = lvl == self.lvl and not self.lvl_tween
        hover = self.hover_group
        if lvl == MONTHS:
            labels, tiles, empty = self.groups.month_layout(self.month_frac, self.vw, self.vh)
            for title, sub, x, y in labels:
                LV.draw_year_label(g, title, sub, x, y, alpha, view)
            for label, x, y, size in empty:
                LV.draw_empty(g, label, x, y, size, alpha, view)
            title_size, folder = 16, False
        elif lvl == YEARS:
            tiles = self.groups.year_tiles(self.vw, self.vh)
            title_size, folder = 38, False
        else:
            tiles = self.groups.coll_tiles(self.vw, self.vh)
            title_size, folder = 24, True
        for t in tiles:
            h = 1.0 if interactive and hover is t.group else 0.0
            r = LV.draw_tile(g, items, t, now, alpha, bg, h, title_size, folder, view)
            if interactive and r:
                self.cluster_rects.append((t.group, (t.x, t.y, t.size, t.size)))

    def frame_rect(self, item):
        if item.vertical:
            w = self.vh * item.aspect
            return (self.vw - w) / 2, 0, w, self.vh
        return 0, 0, self.vw, self.vh

    def draw_fade(self, now):
        g = self.gfx
        nxt, tw = self.fade
        a = tw.value(now)[0]
        item = self.items[nxt]
        g.rect(0, 0, self.vw, self.vh, C.BG_FRAME, a)
        if item.vertical:
            back = g.backdrop(item, force=True)
            if back:
                g.image(back, -40, -40, self.vw + 80, self.vh + 80, alpha=a)
        vtex, va = self.video_layer(nxt, now)
        tex = (vtex if va >= 1.0 else None) or g.screen(item, force=True)
        if tex:
            g.image(tex, *self.kb_rect(nxt, self.frame_rect(item), now), alpha=a, snap=not self.kb_active(nxt))

    # ------------------------------------------------------------------ controles

    def draw_chrome(self, now):
        g = self.gfx
        in_frame = self.mode == FRAME
        frame_amt = self.m if self.big_kind == FRAME and in_frame else 0.0
        frame_amt *= 1.0 - self.night     # de noche se apagan la fecha y el reloj de la esquina
        item = self.items[self.fade[0] if self.fade else self.hero]
        with TH.using(TH.DARK):   # sobre fotos, siempre en oscuro
            st = self.settings
            memory = self.memory_label(item)
            if frame_amt > 0.01 and (st.show_info or st.clock != "off" or memory):
                g.gradient.alpha = int(150 * frame_amt)
                g.gradient.draw(dstrect=(0, self.vh - 260, self.vw, 260))
            dx, dy = self.drift
            if frame_amt > 0.01:
                top = self.vh - 104
                if st.show_info:
                    # Con ubicación: el lugar de título y la colección junto a la fecha.
                    place = place_of(item)
                    title = place or item.collection or tr("Fotos")
                    sub = item.date_text + (f"  ·  {item.collection}" if place and item.collection else "")
                    g.label(title, 56 + dx, self.vh - 104 + dy, 26, frame_amt, bold=True)
                    g.label(sub, 56 + dx, self.vh - 68 + dy, 16, frame_amt)
                else:
                    top = self.vh - 68
                if memory:
                    self.draw_memory_tag(memory, 56 + dx, top - 38 + dy, frame_amt)
                if st.clock != "off":
                    self.draw_clock(self.vw - 56 + dx, self.vh - 50 + dy, frame_amt)
            if in_frame:
                left = self.hint_until - now
                a = min(1.0, max(0.0, left / 0.8)) * min(1.0, max(0.0, (now - self.frame_since - 1.0) / 0.6))
                g.pill(tr("Mueve el mouse para explorar"), self.vw / 2, self.vh - 84, 14, a)
        if self.mode == GRID:
            self.draw_grid_chrome(now, 1.0 - self.m)
        if self.mode == VIEWER and self.m > 0.01:
            self.draw_viewer_chrome(now)
        if self.mode == GRID:
            self.draw_background_work(now, 1.0 - self.m)

    def draw_toast(self, now):
        if not self.toast:
            return
        text, t0 = self.toast
        age = now - t0
        if age > 4.5:
            self.toast = None
            return
        a = min(1.0, age / 0.35, (4.5 - age) / 0.6)
        with TH.using(TH.DARK if self.mode == FRAME else T):
            g = self.gfx
            w = g.tsize(g.text(text, 14, T.text, True))[0] + 36
            g.pill(text, self.vw / 2, 24 + (1 - EASE(min(1.0, age / 0.35))) * -12, 14, a)

    def draw_background_work(self, now, a):
        """Lo que se está haciendo en segundo plano, abajo al centro de la cuadrícula:
        "Preparando fotos 35 de 40 · Preparando videos 1 de 3". Mientras se
        preparan videos, la Mac vieja va más lenta: así se sabe por qué."""
        p = self.processor
        if not p or a <= 0.01:
            return
        parts = []
        if p.busy:
            parts.append(tr("Preparando fotos {done} de {total}", done=min(p.done + 1, p.total), total=p.total))
        if p.videos_done < p.videos_total:
            parts.append(tr("Preparando videos {done} de {total}", done=min(p.videos_done + 1, p.videos_total),
                            total=p.videos_total))
        if not parts:
            return
        g = self.gfx
        label = "  ·  ".join(parts)
        w = g.tsize(g.text(label, 13, T.text, True))[0] + 36 + 26
        x, y, h = self.vw / 2 - w / 2, self.vh - 64, 40
        g.round_rect(x, y, w, h, T.pill, a)
        # Un circulito que gira, para que se note que está trabajando.
        cx, cy = x + 24, y + h / 2
        for k in range(8):
            ang = now * 6 + k * math.pi / 4
            g.rect(cx + 6 * math.cos(ang) - 1.25, cy + 6 * math.sin(ang) - 1.25, 2.5, 2.5, T.text, a * (0.2 + 0.8 * k / 7))
        t = g.text(label, 13, T.text, True)
        tw, th = g.tsize(t)
        t.alpha = int(255 * a)
        t.draw(dstrect=(x + 40, y + (h - th) / 2, tw, th))

    def clock_text(self):
        t = time.localtime()
        if self.settings.clock == "12":
            return f"{t.tm_hour % 12 or 12}:{t.tm_min:02d}", I18N.ampm(t.tm_hour)
        return f"{t.tm_hour}:{t.tm_min:02d}", None

    def draw_clock(self, right, bottom, alpha, size=48):
        """Hora alineada a la derecha, con su orilla de abajo en `bottom`."""
        g = self.gfx
        hhmm, ampm = self.clock_text()
        tw, th = g.tsize(g.text(hhmm, size, (255, 255, 255)))
        aw = ah = 0
        if ampm:
            aw, ah = g.tsize(g.text(ampm, round(size * 0.36), (255, 255, 255), True))
            aw += size * 0.16
        x, y = right - tw - aw, bottom - th
        g.label_shadow(hhmm, x, y, size, alpha)
        if ampm:
            g.label_shadow(ampm, x + tw + size * 0.16, y + th - ah - th * 0.16, round(size * 0.36), alpha * 0.85, bold=True)

    def draw_memory_tag(self, label, x, y, alpha):
        """Etiqueta pequeña de "Un día como hoy"."""
        g = self.gfx
        t = g.text(tr("Un día como hoy  ·  {label}", label=label), 13, (255, 255, 255), True)
        tw, th = g.tsize(t)
        w, h = tw + 28, 28
        g.round_rect(x, y, w, h, (255, 255, 255, 46), alpha, h / 2)
        t.alpha = int(255 * alpha)
        t.draw(dstrect=(x + 14, y + (h - th) / 2, tw, th))

    def draw_night(self, now):
        st = self.settings
        n = self.night
        if n <= 0.001:
            return
        g = self.gfx
        if st.night_style == "window" and self.items:
            self.draw_window_clock(now, n)
            return
        g.rect(0, 0, self.vw, self.vh, (0, 0, 0), min(1.0, n))
        if st.night_style == "classic":
            NC.draw_classic(g, self.glyphs, NC.time_text(st.clock), self.vw, self.vh, g.dpi,
                            st.night_color, n * 0.9, (self.drift[0] * 3, self.drift[1] * 3))

    def draw_window_clock(self, now, amount):
        """Reloj ventana: negro, y por dentro de los números la presentación,
        desenfocada, tenue y con poco color (para que no distraiga)."""
        g, st = self.gfx, self.settings
        parts, _dot = NC.window_layout(self.glyphs, NC.time_text(st.clock), self.vw, self.vh, g.dpi)
        dx, dy = self.drift[0] * 3, self.drift[1] * 3
        parts = [(t, x + dx, y + dy, w, h) for t, x, y, w, h in parts]
        # 1) La presentación, casi en blanco y negro.
        scene = self.offscreen("nightscene", pygame.BLENDMODE_NONE)
        self.ren.target = scene
        self.ren.logical_size = (self.vw, self.vh)
        self.ren.draw_color = (0, 0, 0, 255)
        self.ren.clear()
        # Cada foto llena toda la pantalla (las verticales también), para que se
        # vea a través de todos los números y no solo en una franja.
        shown = [(self.hero, 1.0)]
        if self.fade:
            shown.append((self.fade[0], self.fade[1].value(now)[0]))
        full = (0, 0, self.vw, self.vh)
        for i, a in shown:
            item = self.items[i]
            vtex, va = self.video_layer(i, now) if item.is_video else (None, 0.0)
            tex = vtex if va >= 1.0 else g.screen(item, force=True)
            if tex is None:
                continue
            rect = self.kb_rect(i, full, now)
            g.image(tex, *rect, alpha=a, snap=False)
        self.ren.target = None
        # 2) Desenfocada y tenue.
        # Muy desenfocado: casi manchas de color, sin detalle (ni pixeles de fotos estiradas).
        blur = self.blurred(scene, "nightblur", 6, smooth_up=True)
        win = self.offscreen("nightwin", pygame.BLENDMODE_BLEND)
        self.ren.target = win
        self.ren.logical_size = (self.vw, self.vh)
        blur.blend_mode = pygame.BLENDMODE_NONE
        blur.alpha = 255
        blur.draw(dstrect=(0, 0, self.vw, self.vh))
        # Colores vivos: el desenfoque los apaga, así que se multiplican por sí
        # mismos (c²: separa más los canales) y se suman dos veces (2·c²).
        blur.blend_mode = pygame.BLENDMODE_MOD
        blur.draw(dstrect=(0, 0, self.vw, self.vh))
        sat = self.offscreen("nightsat", pygame.BLENDMODE_NONE)
        self.ren.target = sat
        self.ren.logical_size = (self.vw, self.vh)
        win_src = self.offscreen_tex["nightwin"]
        win_src.blend_mode = pygame.BLENDMODE_NONE
        win_src.alpha = 255
        win_src.draw(dstrect=(0, 0, self.vw, self.vh))
        self.ren.target = win
        self.ren.logical_size = (self.vw, self.vh)
        sat.blend_mode = pygame.BLENDMODE_ADD
        sat.alpha = 255
        sat.draw(dstrect=(0, 0, self.vw, self.vh))
        blur.blend_mode = pygame.BLENDMODE_ADD        # y un poco del color original, para que no quede oscuro
        blur.alpha = 90
        blur.draw(dstrect=(0, 0, self.vw, self.vh))
        blur.alpha = 255
        win_src.blend_mode = pygame.BLENDMODE_BLEND
        blur.blend_mode = pygame.BLENDMODE_BLEND
        # 3) Se recorta con la forma de los números.
        mask = self.offscreen("nightmask", pygame.BLENDMODE_MOD)
        self.ren.target = mask
        self.ren.logical_size = (self.vw, self.vh)
        self.ren.draw_color = (0, 0, 0, 255)
        self.ren.clear()
        NC.draw_window_mask(g, parts)
        self.ren.target = win
        self.ren.logical_size = (self.vw, self.vh)
        mask.alpha = 255
        mask.draw(dstrect=(0, 0, self.vw, self.vh))
        self.ren.target = None
        win.alpha = int(255 * min(1.0, amount))
        win.draw(dstrect=(0, 0, self.vw, self.vh))

    def hit(self, rect, fn):
        if rect:
            self.hits.append((rect, fn))
            self.ui_rects.append(rect)

    def start_presentation(self, now):
        if self.lvl != PHOTOS:
            i = self.hover_group.members[0] if self.hover_group else self.hero
        else:
            i = self.nearest()
        if not self.matches(i):
            i = self.slide_pool()[0]
        self.go_frame(i, now)

    def draw_grid_chrome(self, now, a):
        g = self.gfx
        if a <= 0.01:
            return
        g.rect(0, 0, self.vw, BAR_H, T.bar, T.bar_alpha * a)
        g.rect(0, BAR_H - 1, self.vw, 1, T.hairline, T.hairline_alpha * a)
        self.ui_rects.append((0, 0, self.vw, BAR_H))
        y = (BAR_H - 44) / 2
        # Derecha: presentación y ajustes, solo con íconos.
        sr = g.icon_button("gear", self.vw - 24 - 44, y, alpha=a, icon_size=24)
        self.hit(sr, self.open_settings)
        r = g.icon_button("play", sr[0] - 10 - 44, y, alpha=a, icon_size=22)
        self.hit(r, self.start_presentation)
        # Izquierda: el nivel (años, meses, fotos, colecciones).
        options = [(YEARS, tr("Años")), (MONTHS, tr("Meses")), (PHOTOS, tr("Fotos"))]
        if self.groups.coll_list:
            options.append((COLLS, tr("Colecciones")))
        disabled = () if self.groups.has_years else (YEARS,)
        seg_x = 24
        segs, total = g.segmented(options, self.lvl, seg_x, y, alpha=a, disabled=disabled)
        for key, rect in segs:
            if key not in disabled:
                self.hit(rect, lambda now, k=key: self.pick_level(k, now))
        if self.coll_filter:
            fr = g.button(f"{self.coll_filter}  ×", seg_x + total + 12, y + 6, h=32, alpha=a, active=True, size=13, pad=14)
            self.hit(fr, lambda now: self.set_filter(None))
        # Abajo: contador y zoom
        if self.lvl == PHOTOS:
            n = sum(1 for i in range(len(self.items)) if self.matches(i))
            main = tr("{n} fotos en {c}", n=n, c=self.coll_filter) if self.coll_filter else tr("{n} fotos", n=n)
            sub = None
        elif self.lvl == MONTHS:
            main, sub = tr("Meses"), tr("· {n} con fotos", n=len(self.groups.months))
        elif self.lvl == YEARS:
            main, sub = tr("Años"), f"· {len(self.groups.year_list)}"
        else:
            main, sub = tr("Colecciones"), f"· {len(self.groups.coll_list)}"
        g.pill(main, 24, self.vh - 64, 13, a, anchor="left", sublabel=sub)
        bx, by = self.vw - 24 - 104, self.vh - 68
        g.round_rect(bx, by, 104, 44, T.pill, a)
        g.rect(bx + 52, by + 12, 1, 20, T.hairline, 2 * T.hairline_alpha * a)
        g.rect(bx + 18, by + 21, 16, 2, T.text, a)
        g.rect(bx + 70, by + 21, 16, 2, T.text, a)
        g.rect(bx + 77, by + 14, 2, 16, T.text, a)
        self.ui_rects.append((bx, by, 104, 44))
        self.hit((bx, by, 52, 44), lambda now: self.zoom(-1, now, at_mouse=False))
        self.hit((bx + 52, by, 52, 44), lambda now: self.zoom(1, now, at_mouse=False))

    def draw_video_controls(self, p, a):
        """Barra de pausa, progreso y tiempo, sobre la parte baja del video."""
        with TH.using(TH.DARK):
            self._draw_video_controls(p, a)

    def _draw_video_controls(self, p, a):
        g = self.gfx
        w, h = 440, 48
        x, y = (self.vw - w) / 2, self.vh - 66 - 12 - h
        g.round_rect(x, y, w, h, (44, 44, 48, 215), a)
        self.ui_rects.append((x, y, w, h))
        bx, cy = x + 10, y + h / 2
        playing = p.is_playing
        if playing:
            g.rect(bx + 10, cy - 8, 5, 16, C.TEXT, a)
            g.rect(bx + 20, cy - 8, 5, 16, C.TEXT, a)
        else:
            g.triangle(((bx + 11, cy - 9), (bx + 11, cy + 9), (bx + 26, cy)), C.TEXT, a)
        self.hit((x, y, 48, h), self.toggle_video)
        dur = p.duration or self.items[self.morph_i].duration
        pos = p.position
        label = f"{VID.fmt_time(pos)} / {VID.fmt_time(dur)}"
        t = g.text(label, 13, (229, 229, 234))
        tw, th = g.tsize(t)
        t.alpha = int(255 * a)
        t.draw(dstrect=(x + w - 18 - tw, cy - th / 2, tw, th))
        px, pw = x + 52, w - 52 - 30 - tw
        g.round_rect(px, cy - 2, pw, 4, (255, 255, 255, 56), a)
        frac = min(pos / dur, 1.0) if dur else 0.0
        if frac > 0:
            g.round_rect(px, cy - 2, max(4, pw * frac), 4, (255, 255, 255, 255), a)

        def seek(now, px=px, pw=pw, dur=dur):
            p.seek(max(0.0, (self.mx - px) / pw) * dur)
            p.play()
            self.last_move = now
        self.hit((px, y, pw, h), seek)

    def draw_viewer_chrome(self, now):
        g = self.gfx
        a = self.m * self.chrome_amt
        if a <= 0.01:
            return
        vp = self.player_for("view", self.morph_i)
        if vp and not self.swipe and not self.glide:
            self.draw_video_controls(vp, a)
        sel = self.items[self.current_viewer_index()]
        where = place_of(sel) or sel.collection
        sub = f"· {where}" if where else None
        g.pill(sel.date_text, self.vw / 2, self.vh - 66, 14, a, sublabel=sub)
        if sel.is_video and not sel.video_ready and VID.AVAILABLE:
            g.pill(tr("Preparando video…"), self.vw / 2, self.vh - 122, 13, a)
        r = g.pill(tr("‹  Volver"), 24, (BAR_H - 40) / 2, 14, a, anchor="left")
        self.hit(r, self.close_viewer)
        y = (BAR_H - 44) / 2
        r2 = g.icon_button("play_here", self.vw - 24 - 44 - 10 - 44, y, alpha=a, icon_size=22)
        self.hit(r2, lambda now: self.go_frame(self.current_viewer_index(), now))
        cur = self.current_viewer_index()
        for d, x in ((-1, 24), (1, self.vw - 24 - 48)):
            if self.neighbor(cur, d) is None:
                continue
            y = self.vh / 2 - 24
            g.round_rect(x, y, 48, 48, T.pill, a)
            cx, cy = x + 24, y + 24
            if d < 0:
                g.triangle(((cx + 4, cy - 9), (cx + 4, cy + 9), (cx - 7, cy)), T.text, a)
            else:
                g.triangle(((cx - 4, cy - 9), (cx - 4, cy + 9), (cx + 7, cy)), T.text, a)
            self.hit((x, y, 48, 48), lambda now, d=d: self.viewer_step(d, now))

    def draw_settings(self, now):
        g = self.gfx
        w, h = 620, 680
        h = min(h, self.vh - 40)
        x, y = (self.vw - w) / 2, (self.vh - h) / 2
        g.round_rect(x, y, w, h, T.panel, 1.0, 28)
        self.ui_rects.append((x, y, w, h))
        self.hits.append(((x, y, w, h), lambda now: None))  # clics dentro del panel no lo cierran
        g.label(tr("Ajustes"), x + 28, y + 24, 22, bold=True)
        done = g.button(tr("Listo"), x + w - 28 - 76, y + 20, h=36, active=True, size=14, pad=18)
        self.hit(done, lambda now: self.close_settings(now))
        tabs = [("show", tr("Presentación")), ("screen", tr("Pantalla")), ("night", tr("Noche")),
                ("phone", tr("Celular"))]
        if self.wifi.available:
            tabs.append(("wifi", "WiFi"))
        tw_ = sum(g.tsize(g.text(lbl, 13, T.text, True))[0] + 28 for _, lbl in tabs) + 6
        tsegs, _ = g.segmented(tabs, self.settings_tab, x + (w - tw_) / 2, y + 74, h=36)
        for val, rect in tsegs:
            self.hit(rect, lambda now, v=val: self.pick_tab(v))
        st = self.settings
        ry = [y + 146]
        right = x + w - 28

        def row(title, sub):
            g.rect(x + 28, ry[0] - 14, w - 56, 1, T.hairline, T.hairline_alpha)
            g.label(tr(title), x + 28, ry[0], 15, bold=True)
            g.label(tr(sub), x + 28, ry[0] + 22, 13, color=T.text_secondary)

        def choice(title, sub, attr, opts, enabled=True, on_change=None):
            row(title, sub)
            opts = [(k, tr(lbl)) for k, lbl in opts]
            seg_w = sum(g.tsize(g.text(lbl, 13, T.text, True))[0] + 28 for _, lbl in opts) + 6
            segs, _ = g.segmented(opts, getattr(st, attr), right - seg_w, ry[0], h=40,
                                  alpha=1.0 if enabled else 0.35)
            if enabled:
                for val, rect in segs:
                    def pick(now, v=val):
                        setattr(st, attr, v)
                        if on_change:
                            on_change()
                    self.hit(rect, pick)
            ry[0] += 70

        def switch(title, sub, attr, on_change=None):
            row(title, sub)
            tr = g.toggle(getattr(st, attr), right - 52, ry[0] + 4, key=attr)

            def flip(now):
                setattr(st, attr, not getattr(st, attr))
                if on_change:
                    on_change()
            self.hit(tr, flip)
            ry[0] += 70

        if self.settings_tab == "show":
            choice("Ken Burns", "Movimiento lento de las fotos", "kenburns",
                   [(KB.OFF, "Apagado"), (KB.ZOOM, "Solo zoom"), (KB.PAN, "Zoom y paneo")])
            switch("Un día como hoy", "Fotos de estas fechas de otros años", "memories")
            switch("Fecha y lugar", "Abajo a la izquierda", "show_info")
            choice("Reloj", "Abajo a la derecha", "clock", [("off", "Oculto"), ("12", "12 h"), ("24", "24 h")])

            def reset_queue():
                self.queue = []
            switch("Orden aleatorio", "Mezcla las fotos", "shuffle", reset_queue)
            choice("Volver a la presentación", "Sin mover el mouse", "idle_seconds",
                   [(10, "10 s"), (15, "15 s"), (30, "30 s"), (60, "1 min")])
        elif self.settings_tab == "screen":
            choice("Idioma", "Español o inglés", "language", I18N.LANGS, on_change=self.apply_language)
            choice("Apariencia", "Automático: claro de día", "theme",
                   [("light", "Claro"), ("dark", "Oscuro"), ("auto", "Automático")], on_change=self.apply_theme)
            kind = getattr(self.sensor, "kind", "") if self.sensor.available else ""
            if kind == "camera":
                level = self.sensor.level
                auto_sub = tr("Cámara: luz {n} de 255", n=level) if st.auto_brightness and level is not None \
                    else "Con la cámara: el foquito verde parpadea"
            elif kind:
                auto_sub = "Con el sensor de luz de la Mac"
            else:
                auto_sub = "Esta computadora no tiene sensor ni cámara"
            switch("Brillo automático", auto_sub, "auto_brightness")
            if UPD.available():
                up = self.updater
                if up.checked_at is None or (time.monotonic() - up.checked_at > 600 and up.state in ("current", "error")):
                    if up.state not in ("checking", "applying", "done"):
                        up.check()
                subs = {"idle": tr("Versión {v}", v=__version__), "checking": tr("Buscando…"),
                        "current": tr("Versión {v} · al día", v=__version__),
                        "new": tr("Hay una versión nueva: {v}", v=up.latest),
                        "applying": tr("Paso {n} de {t} · {s}", n=max(1, up.step), t=up.total, s=tr(up.step_text or "Empezando")),
                        "done": tr("Listo: versión {v}. Reiniciando…", v=up.latest),
                        "error": up.error or ""}
                row("Actualizaciones", subs.get(up.state, ""))
                label = tr("Actualizar") if up.state == "new" else tr("Buscar")
                if up.state not in ("applying", "done", "checking"):
                    r = g.button(label, 0, -1000, h=36, size=13, pad=16)
                    r = g.button(label, right - r[2], ry[0] + 2, h=36, size=13, pad=16, active=up.state == "new")
                    self.hit(r, lambda now: up.apply() if up.state == "new" else up.check())
                ry[0] += 70
            if self.backlight.available:
                row("Brillo mínimo", "Calibrado" if st.min_brightness > 0 else "Para que nunca se vaya a negro")
                r = g.button(tr("Calibrar"), 0, -1000, h=36, size=13, pad=16)     # se mide primero
                r = g.button(tr("Calibrar"), right - r[2], ry[0] + 2, h=36, size=13, pad=16)
                self.hit(r, lambda now: self.start_calib(now))
                ry[0] += 70
            if WIFI.SYSTEM:
                r = g.button(tr("Apagar…"), x + 28, ry[0] - 10, h=36, size=13, pad=16)
                self.hit(r, lambda now: self.open_power(now))
                if INST.running_live():
                    r2 = g.button(tr("Instalar en esta Mac…"), r[0] + r[2] + 10, ry[0] - 10, h=36, size=13, pad=16)
                    self.hit(r2, lambda now: self.open_install(now))
        elif self.settings_tab == "night":
            choice("Modo noche", "Reloj o pantalla apagada a cierta hora", "night",
                   [(NIGHT.NEVER, "Nunca"), (NIGHT.SCHEDULE, "Por horario")])
            choice("Horario", "De noche a mañana", "night_hours",
                   [("22-7", "22:00–7:00"), ("23-7", "23:00–7:00"), ("0-6", "0:00–6:00")],
                   enabled=st.night == NIGHT.SCHEDULE)
            choice("De noche", "Qué se ve en la pantalla", "night_style",
                   [("off", "Apagada"), ("window", "Reloj ventana"), ("classic", "Reloj clásico")],
                   enabled=st.night != NIGHT.NEVER)
            choice("Color del reloj clásico", "Rojo: el que menos molesta", "night_color",
                   [("white", "Blanco"), ("blue", "Azul"), ("red", "Rojo")],
                   enabled=st.night != NIGHT.NEVER and st.night_style == "classic")
            g.label(tr("Tecla N: la noche ahora · H: todos los atajos"), x + 28, ry[0] - 4, 12, color=T.text_secondary)
        elif self.settings_tab == "wifi":
            self.draw_wifi_tab(x, y + 130, w, now)
        else:
            self.draw_phone_tab(x, y + 130, w)

        g.rect(x + 28, y + h - 64, w - 56, 1, T.hairline, T.hairline_alpha)
        g.label(f"Vitrina {__version__}  ·  github.com/Danzelote/Vitrina", x + 28, y + h - 48, 12, color=T.text_secondary)
        g.label(tr("Apoya el proyecto en ko-fi.com/danzelot"), x + 28, y + h - 30, 12, color=T.text_secondary)

    # ------------------------------------------------------------------ WiFi

    def pick_tab(self, tab):
        if tab != "wifi" and self.pw is not None:
            self.close_password()
        self.settings_tab = tab
        if tab == "wifi" and not self.wifi.scanning:
            self.wifi.scan()

    def open_wifi(self, now):
        self.open_settings(now)
        self.pick_tab("wifi")

    def type_password(self, e):
        pw = self.pw
        if e.type == pygame.TEXTINPUT:
            if len(pw["text"]) < 63:
                pw["text"] += e.text
        elif e.key == pygame.K_BACKSPACE:
            pw["text"] = pw["text"][:-1]
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.wifi_connect()
        elif e.key == pygame.K_ESCAPE:
            self.close_password()

    def close_password(self):
        self.pw = None
        pygame.key.stop_text_input()

    def wifi_connect(self):
        if self.pw and len(self.pw["text"]) >= 8:
            self.join_wifi(self.pw["ssid"], self.pw["text"])

    def join_wifi(self, ssid, password="", hidden=False):
        """Conectarse desde la Vitrina. Al lograrlo se cierra Ajustes y se avisa
        arriba (y si aún no hay fotos, se ve el código para el celular)."""
        self.wifi_joining = ssid
        self.wifi.connect(ssid, password, hidden)

    def check_wifi_joined(self, now):
        ssid = getattr(self, "wifi_joining", None)
        if not ssid or self.wifi.connecting:
            return
        self.wifi_joining = None
        if self.wifi.message == "ok":
            if self.pw is not None:
                self.close_password()
            if self.settings_open:
                self.close_settings(now)
            self.toast_new = 0
            self.toast = ("✓  " + tr("Conectada a {ssid}", ssid=ssid), now)

    def choose_network(self, net):
        ssid, _signal, secure, in_use = net
        if in_use:
            return
        if secure:
            self.pw = {"ssid": ssid, "text": "", "show": False}
            self.wifi.message = ""
            pygame.key.start_text_input()
        else:
            self.join_wifi(ssid)

    def draw_wifi_tab(self, x, y, w, now):
        """Ajustes → WiFi: redes cercanas, contraseña y estado de la conexión."""
        g, wf = self.gfx, self.wifi
        left, right = x + 28, x + w - 28
        if wf.wired:
            status = tr("Conectada por cable")
        elif wf.current:
            status = tr("Conectada a {ssid}", ssid=wf.current)
        else:
            status = tr("Sin conexión")
        g.label(status, left, y + 4, 17, bold=True)
        msg = wf.message
        note = ""
        if wf.connecting:
            note = tr("Conectando…")
        elif msg == "error:password":
            note = tr("Contraseña incorrecta")
        elif msg.startswith("error:"):
            note = tr("No se pudo conectar") + "  ·  " + msg[6:][:70]
        if note:
            g.label(note, left, y + 30, 13, color=T.text_secondary)
        if msg == "ok" and self.pw:
            self.close_password()
        if self.pw:
            pw = self.pw
            top = y + 64
            g.label(tr("Contraseña de {ssid}", ssid=pw["ssid"]), left, top, 15, bold=True)
            g.label(tr("Escribe con el teclado de la Mac"), left, top + 22, 13, color=T.text_secondary)
            bx, by, bw, bh = left, top + 52, right - left, 46
            g.round_rect(bx, by, bw, bh, T.button, 1.0, 12)
            shown = pw["text"] if pw["show"] else "•" * len(pw["text"])
            t = g.text(shown or " ", 17, T.text)
            tw, th = g.tsize(t)
            t.draw(dstrect=(bx + 16, by + (bh - th) / 2, tw, th))
            if int(now * 2) % 2 == 0:         # cursor que parpadea
                g.rect(bx + 17 + (tw if pw["text"] else 0), by + 12, 2, bh - 24, T.text)
            ry = by + bh + 18
            ok = g.button(tr("Conectar"), left, ry, h=40, active=len(pw["text"]) >= 8, size=14)
            self.hit(ok, lambda now: self.wifi_connect())
            cancel = g.button(tr("Cancelar"), left + ok[2] + 10, ry, h=40, size=14)
            self.hit(cancel, lambda now: self.close_password())
            sh = g.button(tr("Ocultar") if pw["show"] else tr("Mostrar"), right - 110, ry, h=40, size=14)
            self.hit(sh, lambda now: pw.__setitem__("show", not pw["show"]))
            return
        b = g.button(tr("Buscando…") if wf.scanning else tr("Buscar redes"), right - 150, y, h=36, size=13, pad=16)
        self.hit(b, lambda now: wf.scan())
        if QR.AVAILABLE and self.camera_device():
            qb = g.button(tr("Escanear código"), 0, -1000, h=36, size=13, pad=16)       # se mide primero
            qb = g.button(tr("Escanear código"), b[0] - 10 - qb[2], y, h=36, size=13, pad=16)
            self.hit(qb, lambda now: self.start_scan(now))
        top = y + 64
        if not wf.networks:
            if not wf.scanning:
                g.label(tr("No se encontraron redes"), left, top, 14, color=T.text_secondary)
            return
        for k, net in enumerate(wf.networks[:7]):
            ssid, signal, secure, in_use = net
            ry = top + k * 52
            g.rect(left, ry - 8, right - left, 1, T.hairline, T.hairline_alpha)
            g.label(ssid, left, ry, 15, bold=True)
            sub = tr("Conectada") if in_use else (tr("Con contraseña") if secure else tr("Abierta"))
            g.label(sub, left, ry + 21, 12, color=T.text_secondary)
            for bar in range(4):                       # intensidad de la señal
                on = signal >= 15 + bar * 22
                hgt = 6 + bar * 4
                g.rect(right - 40 + bar * 9, ry + 26 - hgt, 6, hgt, T.text, 1.0 if on else 0.2)
            self.hit((left, ry - 8, right - left, 52), lambda now, n=net: self.choose_network(n))

    # ------------------------------------------------------------------ QR del WiFi

    def camera_device(self):
        if self.sensor.available and getattr(self.sensor, "kind", "") == "camera":
            return self.sensor.device
        if time.monotonic() - getattr(self, "_cam_checked", -1e9) > 5:
            self._cam_checked = time.monotonic()
            self._cam_dev = NIGHT.CameraLight.find()
        return getattr(self, "_cam_dev", None)

    def start_scan(self, now):
        dev = self.camera_device()
        if not dev:
            return
        if self.pw is not None:
            self.close_password()
        if getattr(self.sensor, "kind", "") == "camera":
            self.sensor.paused = True           # la cámara no se puede usar para dos cosas a la vez
            deadline = time.monotonic() + 3
            while self.sensor._busy and time.monotonic() < deadline:
                time.sleep(0.05)
        self.scan = {"scanner": QR.Scanner(dev), "start": now, "tex": None, "shown": -1}
        self.show_pointer(True)

    def stop_scan(self):
        if not self.scan:
            return
        self.scan["scanner"].close()
        self.scan = None
        if getattr(self.sensor, "kind", "") == "camera":
            self.sensor.paused = False

    def draw_scan(self, now):
        g, sc = self.gfx, self.scan
        scanner = sc["scanner"]
        if scanner.result:
            wifi = scanner.result
            self.stop_scan()
            self.join_wifi(wifi["ssid"], wifi["password"], wifi["hidden"])
            self.toast = (tr("Conectando a {ssid}…", ssid=wifi["ssid"]), now)
            return
        if now - sc["start"] > 180:          # nadie lo usó: se apaga la cámara
            self.stop_scan()
            return
        self.ren.draw_color = (0, 0, 0, 255)
        self.ren.clear()
        cx = self.vw / 2
        pw_, ph = min(560, self.vw - 80), min(420, self.vh - 300)
        pw_ = min(pw_, ph * 4 / 3)
        ph = pw_ * 3 / 4
        px, py = cx - pw_ / 2, (self.vh - ph) / 2 + 10
        white, soft = (255, 255, 255), (190, 190, 196)
        g.label_centered(tr("Muestra el código QR de tu WiFi"), cx, py - 84, 24, bold=True, color=white)
        g.label_centered(tr("Acerca el celular a la cámara (unos 20–30 cm)."), cx, py - 46, 14, color=soft)
        frame = scanner.frame
        if frame is not None:
            if sc["tex"] is None:
                sc["tex"] = Texture(self.ren, (QR.W, QR.H), streaming=True)
            if sc["shown"] != scanner.frame_n:
                sc["shown"] = scanner.frame_n
                sc["tex"].update(pygame.image.frombuffer(frame, (QR.W, QR.H), "RGB"))
            sc["tex"].draw(dstrect=(px, py, pw_, ph), flip_x=True)       # como espejo
        else:
            g.round_rect(px, py, pw_, ph, (28, 28, 30), 1.0, 18)
            msg = tr("No se pudo abrir la cámara") if scanner.error else \
                tr("La cámara no manda imagen") if scanner.stalled else tr("Abriendo la cámara…")
            g.label_centered(msg, cx, py + ph / 2 - 10, 15, color=soft)
        # Esquinas de guía
        k, t_ = 34, 4
        for left_side in (True, False):
            for top_side in (True, False):
                hx = px if left_side else px + pw_ - k
                vx = px if left_side else px + pw_ - t_
                hy = py if top_side else py + ph - t_
                vy = py if top_side else py + ph - k
                g.rect(hx, hy, k, t_, white)
                g.rect(vx, vy, t_, k, white)
        y2 = py + ph + 22
        if scanner.seen_other:
            g.label_centered(tr("Ese código no es de una red WiFi"), cx, y2, 14, color=(255, 159, 10))
            y2 += 26
        g.label_centered(tr("iPhone: app Contraseñas → Wi-Fi → tu red → Mostrar código QR de la red"), cx, y2, 13,
                         color=soft)
        g.label_centered(tr("Android: Ajustes → Wi-Fi → tu red → Compartir"), cx, y2 + 22, 13, color=soft)
        with TH.using(TH.DARK):
            r = g.button(tr("Cancelar"), 0, -1000, h=40, size=14)
            r = g.button(tr("Cancelar"), cx - r[2] / 2, y2 + 58, h=40, size=14)
        self.hit(r, lambda now: self.stop_scan())

    def draw_empty_library(self):
        with TH.using(TH.DARK):      # el fondo aquí es negro: textos claros
            self._draw_empty_library()

    def _draw_empty_library(self):
        g = self.gfx
        if not hasattr(self, "ambient"):
            self.ambient = AMB.Ambient()
        self.ambient.draw(self.ren, self.vw, self.vh, g.dt)     # ventanas borrosas que se asoman
        url = self.web.pair_url() if self.web else None
        qr = self.qr_texture(url) if url else None
        if qr:
            size = 220
            qx, qy = self.vw / 2 - size / 2, self.vh / 2 - 210
            g.round_rect(qx - 14, qy - 14, size + 28, size + 28, (255, 255, 255, 255), 1.0, 22)
            qr.draw(dstrect=(qx, qy, size, size))
            top = qy + size + 44
            sub = tr("Escanea el código con el celular para agregar fotos")
        else:
            top = self.vh / 2 - 40
            sub = tr("Conecta la Mac al WiFi para usar el celular.") if self.web else \
                "python app/main.py --folder ~/Pictures/Vitrina"
        g.label_centered(tr("No hay fotos todavía"), self.vw / 2, top, 28, bold=True)
        g.label_centered(sub, self.vw / 2, top + 46, 16, color=T.text_dim)
        if self.wifi.available and not self.wifi.online:
            label = tr("Configurar WiFi")
            bw = g.tsize(g.text(label, 14, T.text, True))[0] + 36
            r = g.button(label, self.vw / 2 - bw / 2, top + 110, h=40, size=14)
            self.hit(r, self.open_wifi)
        if qr:
            g.label_centered(tr("El celular y la Mac deben estar en el mismo WiFi."), self.vw / 2, top + 72, 14,
                             color=T.text_secondary)

    def qr_texture(self, url):
        """El código QR de `url` como textura (se genera una vez por dirección)."""
        cache = getattr(self, "_qr", None)
        if cache and cache[0] == url:
            return cache[1]
        try:
            import segno
        except ImportError:
            self._qr = (url, None)
            return None
        rows = [list(r) for r in segno.make(url, error="m", boost_error=False).matrix]
        n = len(rows)
        cell = max(4, 600 // n)
        surf = pygame.Surface((n * cell, n * cell))
        surf.fill((255, 255, 255))
        for yy, row in enumerate(rows):
            for xx, on in enumerate(row):
                if on:
                    surf.fill((17, 17, 17), (xx * cell, yy * cell, cell, cell))
        tex = Texture.from_surface(self.ren, surf)
        self._qr = (url, tex)
        return tex

    def draw_phone_tab(self, x, y, w):
        """Ajustes → Celular: el código para emparejar y los celulares conectados."""
        g = self.gfx
        if not self.web:
            g.label(tr("Sin conexión a la red"), x + 28, y + 20, 15, bold=True)
            return
        url = self.web.pair_url()
        qr = self.qr_texture(url) if url else None
        size = 184
        qx, qy = x + 28, y + 6
        if qr:
            g.round_rect(qx, qy, size, size, (255, 255, 255, 255), 1.0, 16)
            qr.draw(dstrect=(qx + 12, qy + 12, size - 24, size - 24))
        else:
            g.round_rect(qx, qy, size, size, T.button, 1.0, 16)
        tx = qx + size + 24
        g.label(tr("Agregar fotos desde el celular"), tx, qy + 16, 17, bold=True)
        if url and not qr:
            msg = [tr("Falta instalar segno (pip install -r requirements.txt)")]
        elif url:
            msg = [tr("Escanea el código con la cámara del celular"),
                   tr("El celular y la Mac deben estar en el mismo WiFi.")]
        else:
            msg = [tr("Sin conexión a la red"), tr("Conecta la Mac al WiFi para usar el celular.")]
        for k, line in enumerate(msg):
            g.label(line, tx, qy + 50 + k * 22, 13, color=T.text_secondary)
        if url:
            g.label(url.split("/p/")[0].replace("http://", ""), tx, qy + size - 26, 13, color=T.text_dim)
        # Celulares conectados
        ly = qy + size + 34
        g.label(tr("Celulares conectados"), x + 28, ly, 15, bold=True)
        devices = self.web.devices.listing()
        ly += 34
        if not devices:
            g.label(tr("Ninguno todavía"), x + 28, ly, 13, color=T.text_secondary)
        for h, name, added in devices[:4]:
            g.rect(x + 28, ly - 10, w - 56, 1, T.hairline, T.hairline_alpha)
            g.label(name, x + 28, ly + 2, 14, bold=True)
            g.label(I18N.long_date(datetime.fromtimestamp(added)), x + 28 + 110, ly + 4, 13, color=T.text_secondary)
            r = g.button(tr("Quitar"), x + w - 28 - 90, ly - 4, h=32, size=13, pad=14)
            self.hit(r, lambda now, h=h: self.web.devices.remove(h))
            ly += 46

    # ------------------------------------------------------------------ ciclo

    def step(self, now=None):
        now = time.monotonic() if now is None else now
        wall = time.time()
        if (wall - self.wall_ref[0]) - (now - self.wall_ref[1]) > 5:
            self.on_resume(now)            # el reloj de pared avanzó y el monótono no: hubo reposo
        self.wall_ref = (wall, now)
        for e in pygame.event.get():
            self.handle(e, now)
        self.poll_events(now)
        if self.items:
            self.update(now)
        else:
            self.update_idle(now)
        self.check_wifi_joined(now)
        if self.updater.state == "done":     # actualizada: la app se cierra y run.sh la abre ya nueva
            if self.update_done_at is None:
                self.update_done_at = now
                self.toast_new = 0
                self.toast = (tr("Listo: versión {v}. Reiniciando…", v=self.updater.latest), now)
            elif now - self.update_done_at > 2.5:
                self.running = False
        if now - self.wifi_checked > 5:      # estado de la red, cada 5 s
            self.wifi_checked = now
            self.wifi.refresh_status()
        self.draw(now)
        self.ren.present()

    def on_resume(self, now):
        """La Mac despertó (se abrió la tapa): sigue donde se quedó."""
        self.resumed_at = now
        self.last_input = now
        self.frame_since = now
        self.wifi_checked = now - 10
        self.woke = True
        print("Vitrina: despertó del reposo", flush=True)

    def run(self):
        clock = pygame.time.Clock()
        self.frame_at = time.monotonic()
        WATCH.start(lambda: self.frame_at)
        while self.running:
            self.frame_at = time.monotonic()
            self.step()
            if self.sleeping:
                fps = 5                 # apagada: casi sin gastar
            elif self.night >= 0.999:
                fps = 24 if self.settings.night_style == "window" else 4
            else:
                fps = 60
            clock.tick(fps)
        self.shutdown()

    def shutdown(self):
        """Cierra en orden: videos, texturas y al final la ventana. (Si Python
        libera las texturas después que la ventana, puede cerrarse con error.)"""
        self.stop_scan()
        self.close_all_videos()
        self.backlight.restore()
        self.settings.save()
        g = self.gfx
        for cache in (g.thumbs, g.screens, g.backdrops, g.texts, g.pills):
            cache.clear()
        g.white = g.corner = g.gradient = g.circle = None
        g.grays.clear()
        self.glyphs.cache.clear()
        self.offscreen_tex.clear()
        import gc
        gc.collect()
        self.ren = None
        self.win = None
        gc.collect()
        pygame.quit()
