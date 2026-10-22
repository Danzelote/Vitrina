"""La interfaz de Vitrina: modo marco, cuadrícula y visor.

Un solo espacio continuo: la presentación es la cuadrícula vista de muy cerca.
Al mover el mouse la cámara se aleja y la foto se encoge hasta su lugar; al
abrir una foto la cámara se acerca y la miniatura se despliega a su proporción
real.
"""

import math
import os
import time

os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")  # escalado suave (lineal)

import pygame
from pygame._sdl2.video import Renderer, Window

from . import camera as cam
from . import config as C
from .easing import EASE, Tween, lerp
from .gfx import Gfx

FRAME, GRID, VIEWER = "frame", "grid", "viewer"


class App:
    def __init__(self, items, processor=None, fullscreen=False, invert_zoom=False, size=(1280, 800)):
        pygame.display.init()
        pygame.font.init()
        self.win = Window("Vitrina", size=size, resizable=True)
        if fullscreen:
            self.win.set_fullscreen(True)
        self.ren = Renderer(self.win, accelerated=-1, vsync=True)
        self.gfx = Gfx(self.ren)
        self.items = items
        self.processor = processor
        self.zoom_sign = -1 if invert_zoom else 1
        self.vw, self.vh = self.win.size
        self.plane = cam.Plane(*cam.grid_shape(max(1, len(items))))

        now = time.monotonic()
        self.mode = FRAME
        self.zi = C.DEFAULT_ZOOM
        self.hero = min(len(items) - 1, 4 * self.plane.cols + 6) if items else 0
        self.morph_i = self.hero
        self.big_kind = FRAME
        cx, cy = self.plane.cell_center(self.hero)
        self.cx, self.cy, self.s = cx, cy, self.frame_scale()
        self.tcx, self.tcy = cx, cy
        self.cam_tween = None
        self.m = 1.0
        self.m_tween = None
        self.fade = None             # (siguiente índice, Tween) durante el fundido
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
        self.wheel_acc = 0.0
        self.show_info = True
        self.running = True
        self.last_t = now
        pygame.mouse.set_visible(False)

    # ------------------------------------------------------------------ escalas

    def frame_scale(self):
        return self.vh / C.CELL

    def view_scale(self):
        return C.VIEW_FILL * self.vh / C.CELL

    def grid_scale(self):
        return C.ZOOMS[self.zi]

    def big_dims(self, item, kind):
        """Tamaño en el plano de la foto desplegada."""
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

    # ------------------------------------------------------------------ cámara

    def move_camera(self, cx, cy, s, duration, now, ease=EASE):
        start = cam.to_screen(self.cx, self.cy, self.s, self.vw, self.vh)
        end = cam.to_screen(cx, cy, s, self.vw, self.vh)
        self.cam_tween = Tween(start, end, duration, ease, now)
        self.tcx, self.tcy = cx, cy
        self.target_s = s
        self.long_until = now + duration

    def morph_to(self, value, duration, now):
        self.m_tween = Tween((self.m,), (value,), duration, EASE, now)

    def set_anchor(self):
        self.anchor = cam.Anchor(self.mx, self.my, self.tcx, self.tcy)

    def nearest(self):
        pitch = C.CELL + C.GAP
        col = min(max(round((self.cx - C.CELL / 2) / pitch), 0), self.plane.cols - 1)
        row = min(max(round((self.cy - C.CELL / 2) / pitch), 0), self.plane.rows - 1)
        return min(row * self.plane.cols + col, len(self.items) - 1)

    # ------------------------------------------------------------------ modos

    def enter_grid(self, now):
        if self.fade:
            self.finish_fade()
        self.mode = GRID
        s = self.grid_scale()
        cx, cy = cam.clamp(*self.plane.cell_center(self.hero), s, self.plane, self.vw, self.vh)
        self.move_camera(cx, cy, s, C.MORPH_TIME, now)
        self.morph_to(0.0, C.MORPH_TIME, now)
        self.set_anchor()
        pygame.mouse.set_visible(True)

    def go_frame(self, i, now):
        if self.morph_i != i:
            self.m = 0.0
        self.mode = FRAME
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

    def close_viewer(self, now):
        self.mode = GRID
        s = self.grid_scale()
        cx, cy = cam.clamp(*self.plane.cell_center(self.morph_i), s, self.plane, self.vw, self.vh)
        self.move_camera(cx, cy, s, C.MORPH_TIME, now)
        self.morph_to(0.0, C.MORPH_TIME, now)
        self.set_anchor()
        self.last_move = now

    def zoom(self, d, now, at_mouse=True):
        if self.mode != GRID:
            return
        zi = min(max(self.zi + d, 0), len(C.ZOOMS) - 1)
        if zi == self.zi:
            return
        s0, s1 = C.ZOOMS[self.zi], C.ZOOMS[zi]
        self.zi = zi
        fx, fy = (self.mx, self.my) if at_mouse and self.inside else (self.vw / 2, self.vh / 2)
        nx, ny = cam.zoom_at(self.tcx, self.tcy, s0, s1, fx, fy, self.vw, self.vh)
        nx, ny = cam.clamp(nx, ny, s1, self.plane, self.vw, self.vh)
        self.move_camera(nx, ny, s1, C.ZOOM_TIME, now)
        self.set_anchor()
        self.last_move = now

    # ------------------------------------------------------------------ presentación

    def next_index(self):
        return (self.hero + 1) % len(self.items)

    def finish_fade(self):
        nxt, _ = self.fade
        self.fade = None
        self.hero = self.morph_i = nxt
        self.cx, self.cy = self.plane.cell_center(nxt)
        self.tcx, self.tcy = self.cx, self.cy
        self.cam_tween = None

    def update_slideshow(self, now):
        if self.fade:
            nxt, tw = self.fade
            if tw.done(now):
                self.finish_fade()
                self.last_slide = now
            return
        if self.cam_tween or now - self.last_slide < C.SLIDE_TIME or len(self.items) < 2:
            return
        nxt = self.next_index()
        item = self.items[nxt]
        if not item.ready:
            self.hero = nxt  # todavía procesándose: sigue con la siguiente
            return
        if self.gfx.screen(item, force=True) is None:
            return
        self.gfx.backdrop(item, force=True)
        self.fade = (nxt, Tween((0.0,), (1.0,), C.FADE_TIME, EASE, now))

    # ------------------------------------------------------------------ eventos

    def handle(self, e, now):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_q:
                self.running = False
            elif e.key == pygame.K_ESCAPE:
                if self.mode == VIEWER:
                    self.close_viewer(now)
                elif self.mode == GRID:
                    self.go_frame(self.hover_i if self.hover_i is not None else self.nearest(), now)
            elif e.key == pygame.K_f:
                self.win.set_fullscreen(True) if not self._is_fullscreen() else self.win.set_windowed()
            elif e.key == pygame.K_i:
                self.show_info = not self.show_info
            elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.zoom(1, now, at_mouse=False)
            elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.zoom(-1, now, at_mouse=False)
        elif e.type == pygame.MOUSEMOTION:
            self.on_move(e.pos[0], e.pos[1], now)
        elif e.type == pygame.MOUSEWHEEL:
            self.on_wheel(getattr(e, "precise_y", e.y), now)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.on_click(now)
        elif e.type == pygame.WINDOWLEAVE:
            self.inside = False
        elif e.type == pygame.WINDOWENTER:
            self.inside = True
        elif e.type in (pygame.WINDOWSIZECHANGED, pygame.WINDOWRESIZED):
            self.vw, self.vh = self.win.size

    def _is_fullscreen(self):
        return bool(pygame.display.get_init() and self.win.size == pygame.display.get_desktop_sizes()[0])

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
        if self.mode != GRID or self.anchor is None:
            return
        self.anchor.moved(x, y)
        if now < self.long_until:
            return
        self.tcx, self.tcy = cam.pan_target(x, y, self.anchor, self.grid_scale(), self.plane, self.vw, self.vh)

    def on_wheel(self, dy, now):
        if self.mode != GRID:
            return
        self.last_move = now
        dy *= self.zoom_sign
        if self.wheel_acc * dy < 0:
            self.wheel_acc = 0.0
        self.wheel_acc += dy
        if self.wheel_acc >= 1.0:
            self.wheel_acc = 0.0
            self.zoom(1, now)
        elif self.wheel_acc <= -1.0:
            self.wheel_acc = 0.0
            self.zoom(-1, now)

    def on_click(self, now):
        if self.mode == FRAME:
            self.enter_grid(now)
        elif self.mode == VIEWER:
            self.close_viewer(now)
        elif self.mode == GRID and self.hover_i is not None and now >= self.long_until - 0.2:
            self.open_viewer(self.hover_i, now)

    # ------------------------------------------------------------------ actualización

    def update(self, now):
        dt = min(now - self.last_t, 0.1)
        self.last_t = now
        if self.cam_tween:
            tx, ty, s = self.cam_tween.value(now)
            self.cx, self.cy, self.s = cam.from_screen(tx, ty, s, self.vw, self.vh)
            if self.cam_tween.done(now):
                self.cam_tween = None
                self.cx, self.cy, self.s = self.tcx, self.tcy, self.target_s
        elif self.mode == GRID:
            tau = (0.45 + 0.13 * self.zi) / 3.5  # más inercia con zoom alto
            k = 1 - math.exp(-dt / tau)
            self.cx += (self.tcx - self.cx) * k
            self.cy += (self.tcy - self.cy) * k
        if self.m_tween:
            self.m = self.m_tween.value(now)[0]
            if self.m_tween.done(now):
                self.m_tween = None

        if self.mode == GRID:
            px = self.cx + (self.mx - self.vw / 2) / self.s
            py = self.cy + (self.my - self.vh / 2) / self.s
            hi = self.plane.index_at(px, py, len(self.items)) if self.inside else None
            if hi != self.hover_i:
                self.hover_i, self.hover_amt = hi, 0.0
            self.hover_amt += (1.0 - self.hover_amt) * (1 - math.exp(-dt / 0.08))
        else:
            self.hover_i = None

        if self.mode == FRAME:
            self.update_slideshow(now)
        elif now - self.last_move > C.IDLE_TIME:
            self.go_frame(self.hover_i if self.hover_i is not None else
                          (self.morph_i if self.mode == VIEWER else self.nearest()), now)

    # ------------------------------------------------------------------ dibujo

    def draw(self, now):
        g = self.gfx
        g.begin_frame()
        frame_amt = self.m if self.big_kind == FRAME else 0.0
        bg = tuple(round(lerp(a, b, frame_amt)) for a, b in zip(C.BG_GRID, C.BG_FRAME))
        self.ren.draw_color = (*bg, 255)
        self.ren.clear()
        if not self.items:
            self.draw_empty()
            return

        hero = self.items[self.morph_i]
        if frame_amt > 0 and hero.ready and hero.vertical:
            back = g.backdrop(hero, force=True)
            if back:
                pad = 40
                g.image(back, -pad, -pad, self.vw + 2 * pad, self.vh + 2 * pad, alpha=frame_amt)

        tx, ty, s = cam.to_screen(self.cx, self.cy, self.s, self.vw, self.vh)
        others = 1.0 - self.m if self.big_kind in (FRAME, VIEWER) else 1.0
        if others > 0.003:
            self.draw_tiles(tx, ty, s, others, bg)
        self.draw_morph(tx, ty, s, bg)
        if self.fade:
            self.draw_fade(now)
        self.draw_chrome(now, others)

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
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                i = row * self.plane.cols + col
                if i >= n or i == self.morph_i and self.m > 0.001:
                    continue
                if i == self.hover_i:
                    hovered = i
                    continue
                x, y = tx + s * col * pitch, ty + s * row * pitch
                self.draw_tile(self.items[i], x, y, C.CELL * s, C.CELL * s, alpha, radius, bg)
        if hovered is not None:
            col, row = hovered % self.plane.cols, hovered // self.plane.cols
            k = 1 + 0.07 * self.hover_amt
            w = C.CELL * s * k
            x = tx + s * (col * pitch + C.CELL / 2) - w / 2
            y = ty + s * (row * pitch + C.CELL / 2) - w / 2
            if self.hover_amt > 0.05:
                g.rect(x + 4, y + 10 * self.hover_amt, w - 8, w, (0, 0, 0), 0.35 * self.hover_amt * alpha)
            self.draw_tile(self.items[hovered], x, y, w, w, alpha, radius * k, bg)

    def draw_tile(self, item, x, y, w, h, alpha, radius, bg, prefer_screen=False):
        g = self.gfx
        tex = None
        if prefer_screen:
            tex = g.screen(item, force=True)
        if tex is None:
            tex = g.thumb(item)
        if tex is None:
            g.rect(x, y, w, h, C.PLACEHOLDER, alpha)
            if alpha > 0.98:
                g.corners(x, y, w, h, radius, bg)
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
        prefer_screen = w * s > C.THUMB_SHORT_SIDE * 1.3
        self.draw_tile(item, x, y, w * s, h * s, 1.0, radius, bg, prefer_screen)

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

    def draw_chrome(self, now, grid_alpha):
        g = self.gfx
        frame_amt = self.m if self.big_kind == FRAME and self.mode == FRAME else 0.0
        item = self.items[self.fade[0] if self.fade else self.hero]
        # Descripción en la presentación
        if self.show_info and frame_amt > 0.01:
            g.gradient.alpha = int(150 * frame_amt)
            g.gradient.draw(dstrect=(0, self.vh - 260, self.vw, 260))
            title = item.collection or "Fotos"
            g.label(title, 56, self.vh - 104, 26, frame_amt, bold=True)
            g.label(item.date_text, 56, self.vh - 68, 16, frame_amt)
        # Aviso inicial
        if self.mode == FRAME:
            left = self.hint_until - now
            a = min(1.0, max(0.0, left / 0.8)) * min(1.0, max(0.0, (now - self.frame_since - 1.0) / 0.6))
            g.pill("Mueve el mouse para explorar", self.vw / 2, self.vh - 84, 14, a)
        # Cuadrícula
        if self.mode == GRID:
            cols = self.vw / ((C.CELL + C.GAP) * C.ZOOMS[self.zi])
            cols_txt = f"{cols:.0f}" if abs(cols - round(cols)) < 0.05 else f"{cols:.1f}"
            g.pill(f"{len(self.items)} fotos", 24, self.vh - 64, 13, grid_alpha, anchor="left",
                   sublabel=f"· {cols_txt} columnas")
        # Visor
        if self.mode == VIEWER and self.m > 0.01:
            sel = self.items[self.morph_i]
            sub = f"· {sel.collection}" if sel.collection else None
            g.pill(sel.date_text, self.vw / 2, self.vh - 66, 14, self.m, sublabel=sub)
            g.pill("‹  Volver", 24, 24, 14, self.m, anchor="left")
        # Progreso del procesamiento
        p = self.processor
        if p and p.done < len(self.items) and self.mode != FRAME:
            g.pill(f"Preparando fotos {p.done}/{len(self.items)}", self.vw - 24 - 240, 24, 13, 1.0, anchor="left")

    def draw_empty(self):
        g = self.gfx
        t = g.text("No hay fotos todavía", 28, bold=True)
        t.draw(dstrect=((self.vw - t.width) / 2, self.vh / 2 - 40, t.width, t.height))
        t2 = g.text("Corre Vitrina con --folder y una carpeta de fotos, o con --demo", 16, C.TEXT_DIM)
        t2.draw(dstrect=((self.vw - t2.width) / 2, self.vh / 2 + 6, t2.width, t2.height))

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
        pygame.quit()
