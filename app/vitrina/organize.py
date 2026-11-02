"""Organizar desde la Vitrina: menús "···", ventanas (confirmar, escribir un
nombre), modo Seleccionar, "Agregar fotos" a una colección y la papelera
("Eliminadas recientemente").

Es una parte de App (ver ui.py) separada en su propio archivo. Todo lo que
cambia la biblioteca pasa por LiveLibrary (self.lib).
"""

import math

import pygame

from . import livelib
from .i18n import tr
from .theme import T

RED = (255, 69, 58)
BLUE = (10, 132, 255)
MENU_W = 300
MENU_ROW = 44


def inside(r, x, y):
    return r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]


class OrganizeMixin:

    def init_organize(self):
        self.menu = None        # {"x", "y", "items": [(texto, fn, estilo)], "sel"}
        self.dialog = None      # {"title", "text", "buttons": [(texto, fn, estilo)], "input"}
        self.select = None      # {"keys": set, "mode": "pick"|"collection", "name", "orig": set}
        self.trash_ui = None    # {"items": [(Item, registro)], "keys": set, "scroll"}

    def organize_open(self):
        return bool(self.menu or self.dialog or self.trash_ui)

    def close_organize(self):
        """Al volver a la presentación: nada de esto se queda abierto."""
        if self.dialog and self.dialog.get("input") is not None:
            pygame.key.stop_text_input()
        self.menu = self.dialog = self.select = self.trash_ui = None

    # -- biblioteca ------------------------------------------------------------------

    def lib_refresh(self, now, items_changed=False):
        """Aplica ya un cambio hecho desde la Mac (sin esperar a la presentación)."""
        if not self.lib:
            return
        self.lib_version = self.lib.version
        if items_changed:
            self.set_items(list(self.lib.snapshot), now)
        else:
            self.regroup(now)

    def user_collections(self):
        return [n for n, _ in self.lib.collections()] if self.lib else []

    def trash_keys(self, keys, now):
        """Manda fotos a "Eliminadas recientemente"."""
        keys = set(keys)
        if not keys or not self.lib:
            return
        if self.mode == "viewer":
            # La foto en pantalla se va: el visor sigue con la de al lado.
            cur = self.current_viewer_index()
            nxt = self.neighbor(cur, 1)
            if nxt is None:
                nxt = self.neighbor(cur, -1)
            for role in ("view", "view_next", "warm"):
                self.stop_video(role, fade=False)
            self.glide = None
            if nxt is not None and self.items[nxt].key not in keys:
                self.hero = self.morph_i = nxt
            else:
                self.close_viewer(now)
        n = self.lib.trash_keys(keys)
        self.lib_refresh(now, items_changed=True)
        self.say(tr("Se movió a Eliminadas recientemente") if n == 1
                 else tr("{n} se movieron a Eliminadas recientemente", n=n), now)

    # -- menús ---------------------------------------------------------------------

    def open_menu(self, x, y, items, now, title=None):
        """items: [(texto, fn(now), estilo)] con estilo "" | "danger" | "check"."""
        h = len(items) * MENU_ROW + 16 + (34 if title else 0)
        x = min(max(12, x), self.vw - MENU_W - 12)
        y = min(max(12, y), self.vh - h - 12)
        self.menu = {"x": x, "y": y, "items": items, "sel": None, "title": title, "at": now}

    def menu_pick(self, k, now):
        m = self.menu
        self.menu = None
        if m and 0 <= k < len(m["items"]):
            m["items"][k][1](now)

    def draw_menu(self, now):
        m = self.menu
        if not m:
            return
        g = self.gfx
        a = min(1.0, (now - m["at"]) / 0.12)
        self.hits.append(((0, 0, self.vw, self.vh), lambda now: setattr(self, "menu", None)))
        h = len(m["items"]) * MENU_ROW + 16 + (34 if m["title"] else 0)
        x, y = m["x"], m["y"] - 6 * (1 - a)
        g.round_rect(x - 1, y + 3, MENU_W + 2, h + 2, (0, 0, 0, 60), a, 15)      # sombra
        g.round_rect(x, y, MENU_W, h, T.panel, a, 14)
        self.hits.append(((x, y, MENU_W, h), lambda now: None))
        yy = y + 8
        if m["title"]:
            g.label(m["title"], x + 16, yy + 8, 12, a, color=T.text_secondary)
            yy += 34
        for k, (label, _fn, style) in enumerate(m["items"]):
            r = (x + 6, yy, MENU_W - 12, MENU_ROW)
            hover = inside(r, self.mx, self.my) or m["sel"] == k
            if hover:
                g.round_rect(*r, T.button, a, 9)
            color = RED if style == "danger" else T.text
            g.label(label, x + 18 + (22 if style in ("check", "nocheck") else 0), yy + 13, 15, a, color=color)
            if style == "check":
                g.draw_icon("check", x + 16, yy + 13, 18, BLUE, a)
            self.hits.append((r, lambda now, k=k: self.menu_pick(k, now)))
            yy += MENU_ROW

    # -- ventanas --------------------------------------------------------------------

    def open_dialog(self, title, text, buttons, now, input_text=None, placeholder=""):
        """buttons: [(texto, fn(now, valor), estilo)]; el último es el principal."""
        self.menu = None
        self.dialog = {"title": title, "text": text, "buttons": buttons, "input": input_text,
                       "placeholder": placeholder, "at": now}
        if input_text is not None:
            pygame.key.start_text_input()

    def dialog_press(self, k, now):
        d = self.dialog
        if not d:
            return
        value = (d["input"] or "").strip() if d["input"] is not None else None
        label, fn, style = d["buttons"][k]
        if style == "primary" and d["input"] is not None and not value:
            return                                  # sin nombre no se puede
        if d["input"] is not None:
            pygame.key.stop_text_input()
        self.dialog = None
        if fn:
            fn(now, value)

    def draw_dialog(self, now):
        d = self.dialog
        if not d:
            return
        g = self.gfx
        a = min(1.0, (now - d["at"]) / 0.15)
        g.rect(0, 0, self.vw, self.vh, (0, 0, 0), 0.45 * a)
        self.hits.append(((0, 0, self.vw, self.vh), lambda now: None))
        w = 460
        lines = wrap(g, d["text"], 14, w - 56) if d["text"] else []
        h = 70 + len(lines) * 21 + (60 if d["input"] is not None else 0) + 74
        x, y = (self.vw - w) / 2, (self.vh - h) / 2 - 20 * (1 - a)
        g.round_rect(x, y, w, h, T.panel, a, 22)
        self.hits.append(((x, y, w, h), lambda now: None))
        g.label(d["title"], x + 28, y + 26, 18, a, bold=True)
        yy = y + 62
        for line in lines:
            g.label(line, x + 28, yy, 14, a, color=T.text_secondary)
            yy += 21
        if d["input"] is not None:
            yy += 6
            g.round_rect(x + 28, yy, w - 56, 44, T.button, a, 12)
            text = d["input"]
            if text:
                t = g.text(text, 15, T.text)
                tw, th = g.tsize(t)
                t.alpha = int(255 * a)
                t.draw(dstrect=(x + 42, yy + (44 - th) / 2, tw, th))
            else:
                tw = 0
                g.label(d["placeholder"], x + 42, yy + 13, 15, a, color=T.text_secondary)
            if int(now * 2) % 2 == 0:
                g.rect(x + 43 + tw, yy + 12, 2, 20, T.text, a)
            yy += 54
        # Botones a la derecha; el principal al final.
        bx = x + w - 28
        for k in reversed(range(len(d["buttons"]))):
            label, _fn, style = d["buttons"][k]
            t = g.text(label, 14, T.text, True)
            bw = g.tsize(t)[0] + 36
            bx -= bw
            by = y + h - 28 - 40
            if style == "danger":
                g.round_rect(bx, by, bw, 40, RED + (255,), a)
                g.label_centered(label, bx + bw / 2, by + 11, 14, a, True, color=(255, 255, 255))
            else:
                r = g.button(label, bx, by, h=40, alpha=a, active=style == "primary", size=14)
                bw = r[2]
            self.hits.append(((bx, by, bw, 40), lambda now, k=k: self.dialog_press(k, now)))
            bx -= 10

    def dialog_event(self, e, now):
        d = self.dialog
        if e.type == pygame.TEXTINPUT and d["input"] is not None:
            if len(d["input"]) < 60:
                d["input"] += e.text
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                cancel = next((k for k, b in enumerate(d["buttons"]) if b[2] == "cancel"), None)
                if cancel is not None:
                    self.dialog_press(cancel, now)
                else:
                    self.dialog = None
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.dialog_press(len(d["buttons"]) - 1, now)
            elif e.key == pygame.K_BACKSPACE and d["input"] is not None:
                d["input"] = d["input"][:-1]

    # -- nombres ---------------------------------------------------------------------

    def ask_new_collection(self, now, then=None):
        """Pide un nombre y crea la colección; `then(nombre)` agrega fotos."""
        def create(now, name):
            name = self.lib.create_collection(name)
            if name and then:
                then(name)
            self.lib_refresh(now)
            if name:
                self.say(tr("Colección “{c}” creada", c=name), now)
        self.open_dialog(tr("Nueva colección"), "", [(tr("Cancelar"), None, "cancel"), (tr("Crear"), create, "primary")],
                         now, input_text="", placeholder=tr("Nombre"))

    def ask_rename(self, name, now):
        def rename(now, new):
            if new != name and new in self.user_collections():
                self.say(tr("Ya hay una colección con ese nombre"), now)
                return
            if self.lib.rename_collection(name, new):
                if self.coll_filter == name:
                    self.coll_filter = new
                self.lib_refresh(now)
        self.open_dialog(tr("Renombrar colección"), "", [(tr("Cancelar"), None, "cancel"), (tr("Guardar"), rename, "primary")],
                         now, input_text=name, placeholder=tr("Nombre"))

    def ask_delete_collection(self, name, now):
        def delete(now, _v):
            self.lib.delete_collection(name)
            if self.coll_filter == name:
                self.set_filter(None, now)
            self.lib_refresh(now)
        self.open_dialog(tr("¿Borrar la colección “{c}”?", c=name),
                         tr("Las fotos no se borran: siguen en la biblioteca y en sus otras colecciones."),
                         [(tr("Cancelar"), None, "cancel"), (tr("Borrar colección"), delete, "danger")], now)

    def ask_trash(self, keys, now):
        n = len(keys)
        title = tr("¿Borrar esta foto?") if n == 1 else tr("¿Borrar {n} fotos?", n=n)
        self.open_dialog(title, tr("Puedes recuperarla durante 30 días desde Colecciones → Eliminadas recientemente.")
                         if n == 1 else tr("Puedes recuperarlas durante 30 días desde Colecciones → Eliminadas recientemente."),
                         [(tr("Cancelar"), None, "cancel"),
                          (tr("Borrar"), lambda now, _v: self.finish_trash(keys, now), "danger")], now)

    def finish_trash(self, keys, now):
        self.select = None
        self.trash_keys(keys, now)

    # -- menú de una foto (visor) y de una colección (cuadrícula) -------------------------

    def photo_menu(self, now, anchor):
        it = self.items[self.current_viewer_index()]
        items = [(tr("Agregar a colección…"), lambda now: self.collections_menu([it.key], now, anchor), "")]
        f = self.coll_filter
        if f and f in it.collections:
            items.append((tr("Quitar de “{c}”", c=f), lambda now: self.remove_keys([it.key], f, now), ""))
        items.append((tr("Borrar"), lambda now: self.ask_trash([it.key], now), "danger"))
        self.open_menu(anchor[0] - MENU_W + anchor[2], anchor[1] + anchor[3] + 8, items, now)

    def collections_menu(self, keys, now, anchor):
        """Lista de colecciones con ✓ en las que ya tienen (todas) estas fotos."""
        keys = set(keys)
        chosen = [it for it in self.items if it.key in keys]

        def toggle(name):
            def run(now):
                if chosen and all(name in it.collections for it in chosen):
                    self.remove_keys(keys, name, now)
                else:
                    self.lib.add_to(keys, name)
                    self.lib_refresh(now)
                    self.say(tr("Agregada a “{c}”", c=name) if len(keys) == 1
                             else tr("{n} agregadas a “{c}”", n=len(keys), c=name), now)
            return run
        items = []
        for name in self.user_collections()[:9]:
            on = bool(chosen) and all(name in it.collections for it in chosen)
            items.append((name, toggle(name), "check" if on else "nocheck"))
        items.append((tr("Nueva colección…"), lambda now: self.ask_new_collection(
            now, then=lambda name: self.lib.add_to(keys, name)), ""))
        self.open_menu(anchor[0] - MENU_W + anchor[2], anchor[1] + anchor[3] + 8, items, now,
                       title=tr("Agregar a colección"))

    def remove_keys(self, keys, name, now):
        self.lib.remove_from(set(keys), name)
        self.lib_refresh(now)
        self.say(tr("Se quitó de “{c}”", c=name), now)

    def filter_menu(self, now, anchor):
        """"···" junto al nombre de la colección abierta."""
        f = self.coll_filter
        g = self.groups.group_for(f) if f else None
        if not g:
            return
        if g.kind == "coll":
            items = [(tr("Agregar fotos"), lambda now: self.start_add_photos(f, now), ""),
                     (tr("Renombrar…"), lambda now: self.ask_rename(f, now), ""),
                     (tr("Borrar colección…"), lambda now: self.ask_delete_collection(f, now), "danger")]
        else:
            items = [(tr("Guardar como colección…"), lambda now: self.ask_keep_auto(g, now), ""),
                     (tr("Ocultar"), lambda now: self.hide_auto(g, now), "danger")]
        self.open_menu(anchor[0], anchor[1] + anchor[3] + 8, items, now)

    def ask_keep_auto(self, g, now):
        keys = [self.items[i].key for i in g.members]

        def keep(now, name):
            self.lib.keep_auto(g.key, name, keys)
            self.coll_filter = livelib.safe_name(name) or None
            self.lib_refresh(now)
        self.open_dialog(tr("Guardar como colección"), tr("Se vuelve una colección tuya, con el nombre que quieras."),
                         [(tr("Cancelar"), None, "cancel"), (tr("Guardar"), keep, "primary")],
                         now, input_text=g.title, placeholder=tr("Nombre"))

    def hide_auto(self, g, now):
        self.lib.hide_auto(g.key)
        self.set_filter(None, now)
        self.lib_refresh(now)
        self.say(tr("Colección automática oculta"), now)

    # -- seleccionar ---------------------------------------------------------------------

    def start_select(self, now):
        self.menu = None
        self.select = {"keys": set(), "mode": "pick", "name": None, "orig": set()}

    def start_add_photos(self, name, now):
        """Dentro de una colección: todas las fotos, las suyas encendidas."""
        members = {it.key for it in self.items if name in it.collections}
        self.set_filter(None, now)
        self.select = {"keys": set(members), "mode": "collection", "name": name, "orig": set(members)}

    def select_toggle(self, i):
        k = self.items[i].key
        keys = self.select["keys"]
        if k in keys:
            keys.discard(k)
        else:
            keys.add(k)

    def finish_select(self, now):
        s = self.select
        self.select = None
        if not s or s["mode"] != "collection":
            return
        name = s["name"]
        add, drop = s["keys"] - s["orig"], s["orig"] - s["keys"]
        if add:
            self.lib.add_to(add, name)
        if drop:
            self.lib.remove_from(drop, name)
        self.lib_refresh(now)
        self.set_filter(name, now)

    def tile_alpha(self, i):
        """En el modo Seleccionar, las que no están elegidas se ven apagadas."""
        if not self.select or i >= len(self.items):
            return 1.0
        return 1.0 if self.items[i].key in self.select["keys"] else 0.32

    def draw_tile_check(self, i, x, y, w, alpha):
        if not self.select or self.items[i].key not in self.select["keys"] or w < 26:
            return
        g = self.gfx
        d = max(16, min(26, w * 0.16))
        cx, cy = x + w - d * 0.55 - 6, y + d * 0.55 + 6
        g.circle_at(cx, cy, d / 2 + 2, (255, 255, 255), alpha)
        g.circle_at(cx, cy, d / 2, BLUE, alpha)
        g.draw_icon("check", cx - d * 0.36, cy - d * 0.36, d * 0.72, (255, 255, 255), alpha)

    def draw_select_bar(self, now, a, y):
        """Barra de arriba mientras se selecciona: cuántas y qué hacer."""
        g, s = self.gfx, self.select
        n = len(s["keys"])
        x = self.vw - 24
        if s["mode"] == "collection":
            done = g.button(tr("Listo"), 0, -999, h=44, active=True)
            x -= done[2]
            r = g.button(tr("Listo"), x, y, h=44, alpha=a, active=True)
            self.hit(r, self.finish_select)
            x -= 10
            title = tr("Elige las fotos de “{c}”", c=s["name"])
        else:
            if n:
                t = g.button(tr("Borrar"), 0, -999, h=44)
                x -= t[2]
                r = g.button(tr("Borrar"), x, y, h=44, alpha=a)
                self.hit(r, lambda now: self.ask_trash(set(s["keys"]), now))
                x -= 10
                t = g.button(tr("Agregar a colección…"), 0, -999, h=44)
                x -= t[2]
                r = g.button(tr("Agregar a colección…"), x, y, h=44, alpha=a)
                self.hit(r, lambda now, r=r: self.collections_menu(set(s["keys"]), now, r))
                x -= 10
            title = tr("1 seleccionada") if n == 1 else tr("{n} seleccionadas", n=n)
        t = g.button(tr("Cancelar"), 0, -999, h=44)
        x -= t[2]
        r = g.button(tr("Cancelar"), x, y, h=44, alpha=a)
        self.hit(r, lambda now: setattr(self, "select", None))
        return title

    # -- papelera ----------------------------------------------------------------------

    def open_trash(self, now):
        self.menu = None
        self.trash_ui = {"items": self.lib.trash_items() if self.lib else [], "keys": set(), "scroll": 0.0,
                         "at": now}

    def trash_action(self, what, now):
        t = self.trash_ui
        chosen = [it.path for it, _ in t["items"] if not t["keys"] or it.key in t["keys"]]
        if what == "restore":
            n = self.lib.restore(chosen)
            self.say(tr("Se recuperó 1") if n == 1 else tr("Se recuperaron {n}", n=n), now)
            self.lib_refresh(now, items_changed=True)
            self.open_trash(now)
        elif what == "purge":
            def purge(now, _v):
                self.lib.purge(chosen)
                self.lib_refresh(now)
                self.open_trash(now)
            n = len(chosen)
            self.open_dialog(tr("¿Borrar para siempre?") if n == 1 else tr("¿Borrar {n} para siempre?", n=n),
                             tr("Ya no se podrán recuperar."),
                             [(tr("Cancelar"), None, "cancel"), (tr("Borrar"), purge, "danger")], now)

    def draw_trash(self, now):
        t = self.trash_ui
        if not t:
            return
        g = self.gfx
        a = min(1.0, (now - t["at"]) / 0.15)
        g.rect(0, 0, self.vw, self.vh, (0, 0, 0), 0.5 * a)
        self.hits.append(((0, 0, self.vw, self.vh), lambda now: setattr(self, "trash_ui", None)))
        w, h = min(940, self.vw - 60), self.vh - 60
        x, y = (self.vw - w) / 2, 30
        g.round_rect(x, y, w, h, T.panel, a, 24)
        self.hits.append(((x, y, w, h), lambda now: None))
        g.label(tr("Eliminadas recientemente"), x + 28, y + 26, 20, a, bold=True)
        n = len(t["items"])
        sub = tr("Se borran para siempre 30 días después.") + "  " + (
            tr("Toca para elegir; sin elegir, aplica a todas.") if n else "")
        g.label(sub, x + 28, y + 58, 13, a, color=T.text_secondary)
        # Botones
        bx = x + w - 28
        for label, fn, style in ((tr("Listo"), lambda now: setattr(self, "trash_ui", None), "primary"),
                                 (tr("Borrar"), lambda now: self.trash_action("purge", now), "danger"),
                                 (tr("Recuperar"), lambda now: self.trash_action("restore", now), "")):
            if style != "primary" and not n:
                continue
            tt = g.text(label, 14, T.text, True)
            bw = g.tsize(tt)[0] + 36
            bx -= bw
            if style == "danger":
                g.round_rect(bx, y + 22, bw, 40, RED + (255,), a)
                g.label_centered(label, bx + bw / 2, y + 33, 14, a, True, color=(255, 255, 255))
            else:
                g.button(label, bx, y + 22, h=40, alpha=a, active=style == "primary", size=14)
            self.hits.append(((bx, y + 22, bw, 40), fn))
            bx -= 10
        if not n:
            g.label_centered(tr("No hay fotos eliminadas"), self.vw / 2, y + h / 2 - 10, 16, a,
                             color=T.text_secondary)
            return
        # Cuadrícula
        top, pad, gap = y + 92, 28, 10
        cols = max(3, int((w - 2 * pad + gap) // (130 + gap)))
        size = (w - 2 * pad - (cols - 1) * gap) / cols
        rows = math.ceil(n / cols)
        view_h = y + h - 20 - top
        max_scroll = max(0.0, rows * (size + gap) - gap - view_h)
        t["scroll"] = min(max(0.0, t["scroll"]), max_scroll)
        t["max"] = max_scroll
        for k, (it, rec) in enumerate(t["items"]):
            r, c = divmod(k, cols)
            tx = x + pad + c * (size + gap)
            ty = top + r * (size + gap) - t["scroll"]
            if ty + size < top or ty > top + view_h:
                continue
            on = it.key in t["keys"]
            alpha = a * (1.0 if on or not t["keys"] else 0.4)
            tex = g.thumb(it)
            if tex is not None:
                g.image(tex, tx, ty, size, size, alpha, 10, T.panel)
            else:
                g.round_rect(tx, ty, size, size, T.placeholder, alpha, 10)
            days = self.lib.albums.days_left(rec)
            g.pill(tr("1 día") if days == 1 else tr("{n} días", n=days), tx + 8, ty + size - 30, 11, alpha,
                   anchor="left")
            if on:
                d = 22
                g.circle_at(tx + size - 18, ty + 18, d / 2 + 2, (255, 255, 255), a)
                g.circle_at(tx + size - 18, ty + 18, d / 2, BLUE, a)
                g.draw_icon("check", tx + size - 26, ty + 10, 16, (255, 255, 255), a)
            self.hits.append(((tx, max(ty, top), size, min(size, top + view_h - ty)),
                              lambda now, key=it.key: self.trash_toggle(key)))
        # Las orillas: lo que se sale por arriba o abajo queda tapado por el panel.
        g.rect(x, y + 80, w, max(0, top - (y + 80)), T.panel, a)
        g.rect(x, top + view_h, w, y + h - (top + view_h) - 12, T.panel, a)

    def trash_toggle(self, key):
        keys = self.trash_ui["keys"]
        if key in keys:
            keys.discard(key)
        else:
            keys.add(key)

    def trash_event(self, e, now):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.trash_ui = None
        elif e.type == pygame.MOUSEWHEEL:
            dy = getattr(e, "precise_y", e.y)
            self.trash_ui["scroll"] -= dy * 40

    # -- especiales en Colecciones ----------------------------------------------------

    def draw_special_tile(self, t, alpha, hover, view):
        """"Nueva colección", "Eliminadas recientemente" o una colección vacía."""
        g = self.gfx
        k = 1 + 0.04 * hover
        size = t.size * k
        x, y = t.x - (size - t.size) / 2, t.y - (size - t.size) / 2
        rx, ry, rw, rh = view.rect(x, y, size, size)
        if alpha <= 0.003:
            return None
        g.round_rect(rx, ry, rw, rh, T.empty, alpha, 18 * view.k)
        icon = {"new": "plus", "trash": "trash"}.get(t.group.kind)
        s = min(64, rw * 0.3)
        if icon:
            g.draw_icon(icon, rx + (rw - s) / 2, ry + rh * 0.36 - s / 2, s, T.text_secondary, alpha)
        g.label_centered(t.title, rx + rw / 2, ry + rh * 0.62, 16 if rw > 170 else 13, alpha, True)
        if t.sub:
            g.label_centered(t.sub, rx + rw / 2, ry + rh * 0.62 + 24, 12, alpha, color=T.text_secondary)
        return (rx, ry, rw, rh)


def wrap(g, text, size, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if g.tsize(g.text(test, size, T.text))[0] > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines
