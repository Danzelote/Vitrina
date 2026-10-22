"""La interfaz de Vitrina: presentación, cuadrícula, niveles y visor.

Un solo espacio continuo: la presentación es la cuadrícula vista de muy cerca.
Al mover el mouse la cámara se aleja y la foto se encoge hasta su lugar; al
alejarse más, las fotos se agrupan por meses y por años (zoom semántico).
"""

import math
import os
import random
import time

os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")  # escalado suave (lineal)

import pygame  # noqa: E402
from pygame._sdl2.video import Renderer, Window  # noqa: E402

from . import __version__  # noqa: E402
from . import camera as cam  # noqa: E402
from . import config as C  # noqa: E402
from . import levels as LV  # noqa: E402
from .easing import EASE, Tween, cubic_bezier, lerp  # noqa: E402
from .gfx import Gfx  # noqa: E402
from .settings import Settings  # noqa: E402

FRAME, GRID, VIEWER = "frame", "grid", "viewer"
PHOTOS, MONTHS, YEARS, COLLS = "photos", "months", "years", "colls"
RANK = {PHOTOS: 0, MONTHS: 1, COLLS: 1, YEARS: 2}
LEVEL_TIME = 0.75
SWIPE_TIME = 0.5
SWIPE_EASE = cubic_bezier(0.32, 0.72, 0.0, 1.0)   # suave al llegar, como en iOS
SWIPE_UNIT = 40        # puntos que avanza la foto por cada unidad de desplazamiento del trackpad
GESTURE_GAP = 0.25     # segundos sin eventos de rueda = gesto nuevo
BAR_H = 72


def inside(rect, x, y):
    return rect is not None and rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]


class App:
    def __init__(self, items, processor=None, fullscreen=False, invert_zoom=False, size=(1280, 800)):
        pygame.display.init()
        pygame.font.init()
        self.win = Window("Vitrina", size=size, resizable=True, allow_high_dpi=True)
        if fullscreen:
            self.win.set_fullscreen(True)
        self.ren = Renderer(self.win, accelerated=-1, vsync=True)
        self.gfx = Gfx(self.ren)
        self.fit_to_window()
        self.items = items
        self.processor = processor
        self.settings = Settings.load()
        self.zoom_sign = -1 if invert_zoom else 1
        self.plane = cam.Plane(*cam.grid_shape(max(1, len(items))))
        self.groups = LV.Groups(items)

        now = time.monotonic()
        self.mode = FRAME
        self.lvl = PHOTOS
        self.lvl_prev = None
        self.lvl_tween = None
        self.lvl_origin = (self.vw / 2, self.vh / 2)
        self.zi = C.DEFAULT_ZOOM
        self.hero = min(len(items) - 1, 4 * self.plane.cols + 6) if items else 0
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
        self.swipe = None          # animación de cambio de foto en el visor
        self.drag = None           # arrastre con dos dedos en curso (progreso con signo)
        self.rubber = None         # rebote al arrastrar en la primera o la última foto
        self.drag_vis = 0.0        # posición dibujada (sigue a self.drag suavemente)
        self.drag_vel = 0.0
        self.fingers = set()       # dedos sobre el trackpad (si el sistema los reporta)
        self.touch_seen = False
        self.ignore_swipe_until_gap = False
        self.hits = []
        self.ui_rects = []
        self.running = True
        self.last_t = now
        pygame.mouse.set_visible(False)

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

    # ------------------------------------------------------------------ modos

    def enter_grid(self, now):
        if self.fade:
            self.finish_fade()
        self.mode = GRID
        self.lvl = PHOTOS
        s = self.grid_scale()
        cx, cy = cam.clamp(*self.plane.cell_center(self.hero), s, self.plane, self.vw, self.vh)
        self.move_camera(cx, cy, s, C.MORPH_TIME, now)
        self.morph_to(0.0, C.MORPH_TIME, now)
        self.set_anchor()
        pygame.mouse.set_visible(True)

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
        cx, cy = self.plane.cell_center(i)
        self.move_camera(cx, cy, self.frame_scale(), C.MORPH_TIME, now)
        self.morph_to(1.0, C.MORPH_TIME, now)
        self.last_slide = now
        self.frame_since = now
        self.frame_anchor = None
        self.hint_until = now + C.HINT_TIME
        self.anchor = None
        pygame.mouse.set_visible(False)

    def open_viewer(self, i, now):
        self.mode = VIEWER
        self.morph_i = self.hero = i
        self.big_kind = VIEWER
        self.m = 0.0
        cx, cy = self.plane.cell_center(i)
        self.move_camera(cx, cy, self.view_scale(), C.MORPH_TIME, now)
        self.morph_to(1.0, C.MORPH_TIME, now)
        self.last_move = now

    def neighbor(self, i, d):
        """Siguiente (d=1) o anterior (d=-1) foto visible con el filtro, o None."""
        j = i + d
        while 0 <= j < len(self.items):
            if self.matches(j):
                return j
            j += d
        return None

    def viewer_step(self, d, now):
        if self.mode != VIEWER or self.m_tween:
            return
        if self.swipe:
            self.finish_swipe()
        self.drag = None
        j = self.neighbor(self.morph_i, d)
        if j is None:
            return
        self.animate_swipe(j, d, 0.0, 1.0, SWIPE_TIME, now)
        self.last_move = now

    def animate_swipe(self, j, d, t0, t1, duration, now):
        self.gfx.screen(self.items[j], force=True)
        self.swipe = {"a": self.morph_i, "b": j, "d": d, "to": t1,
                      "tw": Tween((t0,), (t1,), max(duration, 0.12), SWIPE_EASE, now)}

    def finish_swipe(self):
        sw, self.swipe = self.swipe, None
        if sw["to"] >= 1.0:
            self.morph_i = self.hero = sw["b"]
            self.jump_camera(*self.plane.cell_center(sw["b"]), self.view_scale())

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
        """Distancia entre dos fotos en el visor. Suficiente para que la que se va
        salga completa de la pantalla, y la nueva asome desde el primer momento."""
        widths = [self.viewer_rect(i)[2] for i in (a, b) if i is not None]
        w = max(widths) if widths else self.vw * 0.6
        return self.vw / 2 + w / 2 + 40

    def current_viewer_index(self):
        if self.swipe and self.swipe["to"] >= 1.0:
            return self.swipe["b"]
        return self.morph_i

    def viewer_rect(self, i):
        s = self.view_scale()
        bw, bh = self.big_dims(self.items[i], VIEWER)
        w, h = bw * s, bh * s
        return (self.vw - w) / 2, (self.vh - h) / 2, w, h

    def close_viewer(self, now):
        if self.swipe:
            self.finish_swipe()
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
        if self.settings.shuffle:
            if not self.queue or self.queue[0] not in pool:
                self.queue = [i for i in pool if i != self.hero]
                random.shuffle(self.queue)
            return self.queue.pop(0) if self.queue else self.hero
        later = [i for i in pool if i > self.hero]
        return later[0] if later else pool[0]

    def finish_fade(self):
        nxt, _ = self.fade
        self.fade = None
        self.hero = self.morph_i = nxt
        self.jump_camera(*self.plane.cell_center(nxt), self.frame_scale())

    def update_slideshow(self, now):
        if self.fade:
            if self.fade[1].done(now):
                self.finish_fade()
                self.last_slide = now
            return
        if self.cam_tween or now - self.last_slide < C.SLIDE_TIME or len(self.items) < 2:
            return
        if self._next is None:
            self._next = self.next_index()
        item = self.items[self._next]
        if not item.ready:
            self._next = None
            return
        if self.gfx.screen(item, force=True) is None:
            return
        self.gfx.backdrop(item, force=True)
        self.fade = (self._next, Tween((0.0,), (1.0,), C.FADE_TIME, EASE, now))
        self._next = None

    # ------------------------------------------------------------------ eventos

    def handle(self, e, now):
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

    def on_key(self, e, now):
        if e.key == pygame.K_q:
            self.running = False
        elif e.key == pygame.K_ESCAPE:
            if self.settings_open:
                self.close_settings()
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
        elif e.key == pygame.K_i:
            self.settings.show_info = not self.settings.show_info
            self.settings.save()
        elif e.key == pygame.K_RIGHT:
            self.viewer_step(1, now)
        elif e.key == pygame.K_LEFT:
            self.viewer_step(-1, now)
        elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.zoom(1, now, at_mouse=False)
        elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom(-1, now, at_mouse=False)

    def on_move(self, x, y, now):
        self.mx, self.my = x, y
        self.inside = True
        self.last_move = now
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
        """Arrastre con dos dedos en el visor: la foto sigue a los dedos y al
        soltar termina el cambio o regresa."""
        gap = now - self.wheel_last
        self.wheel_last = now
        self.last_move = now
        if gap > GESTURE_GAP:
            self.ignore_swipe_until_gap = False
        if dx == 0 or self.m_tween or self.ignore_swipe_until_gap:
            return
        if self.swipe:
            return  # deja terminar la animación anterior
        if self.drag is None:
            self.drag = 0.0
            self.drag_vis = 0.0
            self.drag_vel = 0.0
            self.rubber = None
        step = dx * self.zoom_sign * SWIPE_UNIT / self.page_width(self.morph_i)
        p = self.drag + step
        if self.neighbor(self.morph_i, 1 if p > 0 else -1) is None:
            p = self.drag + step * 0.3  # resistencia en la primera y la última
        self.drag = max(-1.0, min(1.0, p))

    def on_click(self, now):
        self.last_move = now
        for rect, fn in reversed(self.hits):
            if inside(rect, self.mx, self.my):
                fn(now)
                return
        if self.settings_open:
            self.close_settings()
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

    def close_settings(self):
        self.settings_open = False
        self.settings.save()

    # ------------------------------------------------------------------ actualización

    def update(self, now):
        dt = min(now - self.last_t, 0.1)
        self.last_t = now
        if self.cam_tween:
            tx, ty, s = self.cam_tween.value(now)
            self.cx, self.cy, self.s = cam.from_screen(tx, ty, s, self.vw, self.vh)
            if self.cam_tween.done(now):
                self.jump_camera(self.tcx, self.tcy, self.target_s)
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
        if self.drag is not None:
            prev = self.drag_vis
            self.drag_vis += (self.drag - self.drag_vis) * (1 - math.exp(-dt / 0.035))
            if dt > 0:
                self.drag_vel = 0.7 * self.drag_vel + 0.3 * (self.drag_vis - prev) / dt
            # Sin reporte de dedos (por ejemplo en Linux) se toma como soltado tras una pausa.
            if not self.touch_seen and now - self.wheel_last > 0.35:
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
                self.hover_i, self.hover_amt = hi, 0.0
            self.hover_amt += (1.0 - self.hover_amt) * (1 - math.exp(-dt / 0.08))
        else:
            self.hover_i = None
        if can_hover and self.lvl != PHOTOS:
            self.hover_group = next((g for g, r in reversed(self.cluster_rects) if inside(r, self.mx, self.my)), None)
        else:
            self.hover_group = None

        if self.settings_open:
            self.last_move = now
        if self.mode == VIEWER and not self.swipe:
            for d in (1, -1):
                j = self.neighbor(self.morph_i, d)
                if j is not None:
                    self.gfx.screen(self.items[j])
        if self.mode == FRAME:
            self.update_slideshow(now)
        elif now - self.last_move > self.settings.idle_seconds:
            if self.mode == VIEWER:
                target = self.morph_i
            elif self.lvl == PHOTOS:
                target = self.hover_i if self.hover_i is not None else self.nearest()
            else:
                target = self.hover_group.members[0] if self.hover_group else self.hero
            self.go_frame(target, now)

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
        g = self.gfx
        g.begin_frame()
        self.hits = []
        self.ui_rects = []
        frame_amt = self.m if self.big_kind == FRAME else 0.0
        bg = tuple(round(lerp(a, b, frame_amt)) for a, b in zip(C.BG_GRID, C.BG_FRAME))
        self.ren.draw_color = (*bg, 255)
        self.ren.clear()
        if not self.items:
            self.draw_empty_library()
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
            if self.swipe or self.drag is not None or self.rubber:
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

    def draw_tiles(self, tx, ty, s, alpha, bg):
        g = self.gfx
        pitch = C.CELL + C.GAP
        c0 = max(0, int((-tx / s) // pitch) - 1)
        c1 = min(self.plane.cols - 1, int(((self.vw - tx) / s) // pitch) + 1)
        r0 = max(0, int((-ty / s) // pitch) - 1)
        r1 = min(self.plane.rows - 1, int(((self.vh - ty) / s) // pitch) + 1)
        n = len(self.items)
        radius = C.RADIUS_GRID * s
        hovered = None
        skip_morph = self.m > 0.001 and self.lvl == PHOTOS and not self.lvl_tween
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                i = row * self.plane.cols + col
                if i >= n or (i == self.morph_i and skip_morph):
                    continue
                if i == self.hover_i:
                    hovered = i
                    continue
                a = alpha * (1.0 if self.matches(i) else 0.14)
                x, y = tx + s * col * pitch, ty + s * row * pitch
                self.draw_tile(self.items[i], x, y, C.CELL * s, C.CELL * s, a, radius, bg)
        if hovered is not None:
            col, row = hovered % self.plane.cols, hovered // self.plane.cols
            k = 1 + 0.07 * self.hover_amt
            w = C.CELL * s * k
            x = tx + s * (col * pitch + C.CELL / 2) - w / 2
            y = ty + s * (row * pitch + C.CELL / 2) - w / 2
            a = alpha * (1.0 if self.matches(hovered) else 0.14)
            if self.hover_amt > 0.05:
                g.round_rect(x + 6, y + 12 * self.hover_amt, w - 12, w, (0, 0, 0, 255), 0.35 * self.hover_amt * a, radius)
            self.draw_tile(self.items[hovered], x, y, w, w, a, radius * k, bg)

    def draw_tile(self, item, x, y, w, h, alpha, radius, bg, prefer_screen=False):
        g = self.gfx
        tex = g.screen(item, force=True) if prefer_screen else None
        if tex is None:
            tex = g.thumb(item)
        if tex is None:
            g.rect(x, y, w, h, C.PLACEHOLDER, alpha)
            g.corners(x, y, w, h, radius, bg, alpha)
            return
        g.image(tex, x, y, w, h, alpha, radius, bg)

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
        self.draw_tile(item, x, y, w * s, h * s, 1.0, radius, bg, w * s > C.THUMB_SHORT_SIDE * 1.3)

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
                self.draw_tile(self.items[a], x - p * self.page_width(a), y, w, h, 1.0, radius, bg, True)
                return
        page = self.page_width(a, b)
        for i, off in ((a, -d * t * page), (b, d * (1 - t) * page)):
            x, y, w, h = self.viewer_rect(i)
            if x + off + w < 0 or x + off > self.vw:
                continue
            self.draw_tile(self.items[i], x + off, y, w, h, 1.0, radius, bg, True)

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
        tex = g.screen(item, force=True)
        if tex:
            g.image(tex, *self.frame_rect(item), alpha=a)

    # ------------------------------------------------------------------ controles

    def draw_chrome(self, now):
        g = self.gfx
        in_frame = self.mode == FRAME
        frame_amt = self.m if self.big_kind == FRAME and in_frame else 0.0
        item = self.items[self.fade[0] if self.fade else self.hero]
        if self.settings.show_info and frame_amt > 0.01:
            g.gradient.alpha = int(150 * frame_amt)
            g.gradient.draw(dstrect=(0, self.vh - 260, self.vw, 260))
            g.label(item.collection or "Fotos", 56, self.vh - 104, 26, frame_amt, bold=True)
            g.label(item.date_text, 56, self.vh - 68, 16, frame_amt)
        if in_frame:
            left = self.hint_until - now
            a = min(1.0, max(0.0, left / 0.8)) * min(1.0, max(0.0, (now - self.frame_since - 1.0) / 0.6))
            g.pill("Mueve el mouse para explorar", self.vw / 2, self.vh - 84, 14, a)
        if self.mode == GRID:
            self.draw_grid_chrome(now, 1.0 - self.m)
        if self.mode == VIEWER and self.m > 0.01:
            self.draw_viewer_chrome(now)
        p = self.processor
        if p and p.done < len(self.items) and not in_frame:
            label = f"Preparando fotos {p.done}/{len(self.items)}"
            w = g.tsize(g.text(label, 13, C.TEXT, True))[0] + 36
            g.pill(label, self.vw - 24 - w, self.vh - 128, 13, 1.0, anchor="left")
        if self.settings_open:
            self.draw_settings(now)

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
        g.rect(0, 0, self.vw, BAR_H, (12, 12, 14), 0.94 * a)
        g.rect(0, BAR_H - 1, self.vw, 1, (255, 255, 255), 0.07 * a)
        self.ui_rects.append((0, 0, self.vw, BAR_H))
        y = (BAR_H - 44) / 2
        r = g.button("Presentación", 24, y, alpha=a, icon="play")
        self.hit(r, self.start_presentation)
        options = [(YEARS, "Años"), (MONTHS, "Meses"), (PHOTOS, "Fotos")]
        if self.groups.coll_list:
            options.append((COLLS, "Colecciones"))
        disabled = () if self.groups.has_years else (YEARS,)
        seg_x = r[0] + r[2] + 12
        segs, total = g.segmented(options, self.lvl, seg_x, y, alpha=a, disabled=disabled)
        for key, rect in segs:
            if key not in disabled:
                self.hit(rect, lambda now, k=key: self.pick_level(k, now))
        if self.coll_filter:
            fr = g.button(f"{self.coll_filter}  ×", seg_x + total + 12, y + 6, h=32, alpha=a, active=True, size=13, pad=14)
            self.hit(fr, lambda now: self.set_filter(None))
        label = "Ajustes"
        w = g.tsize(g.text(label, 14, C.TEXT, True))[0] + 36
        sr = g.button(label, self.vw - 24 - w, y, alpha=a)
        self.hit(sr, lambda now: setattr(self, "settings_open", True))
        # Abajo: contador y zoom
        if self.lvl == PHOTOS:
            n = sum(1 for i in range(len(self.items)) if self.matches(i))
            cols = self.vw / ((C.CELL + C.GAP) * C.ZOOMS[self.zi])
            cols_txt = f"{cols:.0f}" if abs(cols - round(cols)) < 0.05 else f"{cols:.1f}"
            main = f"{n} fotos" + (f" en {self.coll_filter}" if self.coll_filter else "")
            sub = f"· {cols_txt} columnas"
        elif self.lvl == MONTHS:
            main, sub = "Meses", f"· {len(self.groups.months)} con fotos"
        elif self.lvl == YEARS:
            main, sub = "Años", f"· {len(self.groups.year_list)}"
        else:
            main, sub = "Colecciones", f"· {len(self.groups.coll_list)}"
        g.pill(main, 24, self.vh - 64, 13, a, anchor="left", sublabel=sub)
        bx, by = self.vw - 24 - 104, self.vh - 68
        g.round_rect(bx, by, 104, 44, (44, 44, 48, 210), a)
        g.rect(bx + 52, by + 12, 1, 20, (255, 255, 255), 0.16 * a)
        g.rect(bx + 18, by + 21, 16, 2, C.TEXT, a)
        g.rect(bx + 70, by + 21, 16, 2, C.TEXT, a)
        g.rect(bx + 77, by + 14, 2, 16, C.TEXT, a)
        self.ui_rects.append((bx, by, 104, 44))
        self.hit((bx, by, 52, 44), lambda now: self.zoom(-1, now, at_mouse=False))
        self.hit((bx + 52, by, 52, 44), lambda now: self.zoom(1, now, at_mouse=False))

    def draw_viewer_chrome(self, now):
        g = self.gfx
        a = self.m
        sel = self.items[self.current_viewer_index()]
        sub = f"· {sel.collection}" if sel.collection else None
        g.pill(sel.date_text, self.vw / 2, self.vh - 66, 14, a, sublabel=sub)
        r = g.pill("‹  Volver", 24, 24, 14, a, anchor="left")
        self.hit(r, self.close_viewer)
        label = "Presentación desde aquí"
        w = g.tsize(g.text(label, 14, C.TEXT, True))[0] + 36 + 22
        r2 = g.button(label, self.vw - 24 - w, 24, h=40, alpha=a, icon="play")
        self.hit(r2, lambda now: self.go_frame(self.current_viewer_index(), now))
        cur = self.current_viewer_index()
        for d, x in ((-1, 24), (1, self.vw - 24 - 48)):
            if self.neighbor(cur, d) is None:
                continue
            y = self.vh / 2 - 24
            g.round_rect(x, y, 48, 48, (44, 44, 48, 210), a)
            cx, cy = x + 24, y + 24
            if d < 0:
                g.triangle(((cx + 4, cy - 9), (cx + 4, cy + 9), (cx - 7, cy)), C.TEXT, a)
            else:
                g.triangle(((cx - 4, cy - 9), (cx - 4, cy + 9), (cx + 7, cy)), C.TEXT, a)
            self.hit((x, y, 48, 48), lambda now, d=d: self.viewer_step(d, now))

    def draw_settings(self, now):
        g = self.gfx
        g.rect(0, 0, self.vw, self.vh, (0, 0, 0), 0.45)
        w, h = 560, 400
        x, y = (self.vw - w) / 2, (self.vh - h) / 2
        g.round_rect(x, y, w, h, (30, 30, 34, 245), 1.0, 28)
        self.ui_rects.append((x, y, w, h))
        self.hits.append(((x, y, w, h), lambda now: None))  # clics dentro del panel no lo cierran
        g.label("Ajustes", x + 28, y + 24, 22, bold=True)
        done = g.button("Listo", x + w - 28 - 76, y + 20, h=36, active=True, size=14, pad=18)
        self.hit(done, lambda now: self.close_settings())
        st = self.settings
        rows_y = y + 96

        def row(ry, title, sub):
            g.rect(x + 28, ry - 16, w - 56, 1, (255, 255, 255), 0.08)
            g.label(title, x + 28, ry, 15, bold=True)
            g.label(sub, x + 28, ry + 22, 13, color=(161, 161, 166))

        row(rows_y, "Volver a la presentación", "Tras este tiempo sin mover el mouse")
        opts = [(10, "10 s"), (15, "15 s"), (30, "30 s"), (60, "1 min")]
        seg_w = sum(g.tsize(g.text(lbl, 13, C.TEXT, True))[0] + 28 for _, lbl in opts) + 6
        segs, _ = g.segmented(opts, st.idle_seconds, x + w - 28 - seg_w, rows_y, h=40)
        for val, rect in segs:
            self.hit(rect, lambda now, v=val: setattr(st, "idle_seconds", v))

        rows_y += 76
        row(rows_y, "Mostrar fecha y lugar", "En la esquina, durante la presentación")
        tr = g.toggle(st.show_info, x + w - 28 - 52, rows_y + 4)
        self.hit(tr, lambda now: setattr(st, "show_info", not st.show_info))

        rows_y += 76
        row(rows_y, "Orden aleatorio", "Mezcla las fotos en la presentación")
        tr2 = g.toggle(st.shuffle, x + w - 28 - 52, rows_y + 4)

        def flip_shuffle(now):
            st.shuffle = not st.shuffle
            self.queue = []
        self.hit(tr2, flip_shuffle)

        g.rect(x + 28, y + h - 64, w - 56, 1, (255, 255, 255), 0.08)
        g.label(f"Vitrina {__version__}  ·  github.com/Danzelote/Vitrina", x + 28, y + h - 48, 12, color=(161, 161, 166))
        g.label("Apoya el proyecto en ko-fi.com/danzelot", x + 28, y + h - 30, 12, color=(161, 161, 166))

    def draw_empty_library(self):
        g = self.gfx
        g.label_centered("No hay fotos todavía", self.vw / 2, self.vh / 2 - 40, 28, bold=True)
        g.label_centered("Corre Vitrina con --folder y una carpeta de fotos, o con --demo",
                         self.vw / 2, self.vh / 2 + 6, 16, color=C.TEXT_DIM)

    # ------------------------------------------------------------------ ciclo

    def step(self, now=None):
        now = time.monotonic() if now is None else now
        for e in pygame.event.get():
            self.handle(e, now)
        if self.items:
            self.update(now)
        self.draw(now)
        self.ren.present()

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            self.step()
            clock.tick(60)
        self.settings.save()
        pygame.quit()
