"""Un campo de texto de una línea que se comporta como en la Mac.

Lo usan la búsqueda, los nombres de colección y la contraseña del WiFi:
- ⌘A selecciona todo (y lo que se escriba lo reemplaza), ⌘C / ⌘X / ⌘V copian,
  cortan y pegan; con Control también (teclados que no son de Mac).
- ⌥⌫ borra una palabra, ⌘⌫ hasta el inicio, Supr hacia adelante.
- ← → mueven el cursor (⌥ por palabra, ⌘ al inicio o al final).
- Mantener una tecla presionada la repite (solo mientras hay un campo abierto,
  para que no afecte a los atajos de la Vitrina).
"""

import pygame

_clip = [""]               # por si el portapapeles del sistema no está disponible
SELECT = (10, 132, 255)
REPEAT = (450, 38)         # empieza a repetir a los 0.45 s, luego ~26 por segundo


def begin():
    pygame.key.start_text_input()
    pygame.key.set_repeat(*REPEAT)


def end():
    pygame.key.stop_text_input()
    pygame.key.set_repeat()


def clipboard_get():
    try:
        t = pygame.scrap.get_text()
        if t:
            return t
    except Exception:          # noqa: BLE001
        pass
    return _clip[0]


def clipboard_put(text):
    _clip[0] = text
    try:
        pygame.scrap.put_text(text)
    except Exception:          # noqa: BLE001
        pass


def _word_left(s, i):
    while i > 0 and s[i - 1] == " ":
        i -= 1
    while i > 0 and s[i - 1] != " ":
        i -= 1
    return i


def _word_right(s, i):
    n = len(s)
    while i < n and s[i] == " ":
        i += 1
    while i < n and s[i] != " ":
        i += 1
    return i


class TextField:
    def __init__(self, text="", limit=60, secret=False):
        self.text = text
        self.cur = len(text)
        self.all = False        # todo seleccionado (⌘A)
        self.limit = limit
        self.secret = secret    # contraseña: no se copia ni se corta

    def set(self, text):
        self.text, self.cur, self.all = text, len(text), False

    def _replace_all(self, text):
        self.text = text[:self.limit]
        self.cur = len(self.text)
        self.all = False

    def insert(self, s):
        s = s.replace("\n", " ").replace("\r", "").replace("\t", " ")
        if self.all:
            self._replace_all(s)
            return
        room = self.limit - len(self.text)
        s = s[:max(0, room)]
        self.text = self.text[:self.cur] + s + self.text[self.cur:]
        self.cur += len(s)

    def handle(self, e):
        """True si el evento era para el campo (cambió o se movió el cursor)."""
        if e.type == pygame.TEXTINPUT:
            self.insert(e.text)
            return True
        if e.type != pygame.KEYDOWN:
            return False
        cmd = bool(e.mod & (pygame.KMOD_GUI | pygame.KMOD_CTRL))
        alt = bool(e.mod & pygame.KMOD_ALT)
        k = e.key
        s, i = self.text, self.cur
        if cmd and k == pygame.K_a:
            self.all = bool(s)
        elif cmd and k in (pygame.K_c, pygame.K_x):
            if s and not self.secret:
                clipboard_put(s)
                if k == pygame.K_x:
                    self._replace_all("")
        elif cmd and k == pygame.K_v:
            self.insert(clipboard_get())
        elif k == pygame.K_BACKSPACE:
            if self.all:
                self._replace_all("")
            elif cmd:
                self.text, self.cur = s[i:], 0
            elif alt:
                j = _word_left(s, i)
                self.text, self.cur = s[:j] + s[i:], j
            elif i > 0:
                self.text, self.cur = s[:i - 1] + s[i:], i - 1
        elif k == pygame.K_DELETE:
            if self.all:
                self._replace_all("")
            elif i < len(s):
                self.text = s[:i] + s[i + 1:]
        elif k in (pygame.K_LEFT, pygame.K_HOME):
            if self.all:
                self.cur = 0
            elif cmd or k == pygame.K_HOME:
                self.cur = 0
            elif alt:
                self.cur = _word_left(s, i)
            else:
                self.cur = max(0, i - 1)
            self.all = False
        elif k in (pygame.K_RIGHT, pygame.K_END):
            if self.all or cmd or k == pygame.K_END:
                self.cur = len(s)
            elif alt:
                self.cur = _word_right(s, i)
            else:
                self.cur = min(len(s), i + 1)
            self.all = False
        else:
            return False
        if not (cmd and k in (pygame.K_a, pygame.K_c)):
            self.all = False            # cualquier otra cosa quita la selección
        return True

    def draw(self, g, x, y, h, size, color, alpha, now, placeholder="", placeholder_color=None, max_w=None):
        """Texto, selección y cursor. (x, y, h): dónde va la línea. Devuelve el ancho del texto."""
        shown = "•" * len(self.text) if self.secret else self.text
        if not shown:
            if placeholder:
                g.label(placeholder, x, y + (h - size * 1.3) / 2, size, alpha, color=placeholder_color or color)
            if int(now * 2) % 2 == 0:
                g.rect(x + 1, y + h * 0.22, 2, h * 0.56, color, alpha)
            return 0
        t = g.text(shown, size, color)
        tw, th = g.tsize(t)
        if self.all:
            g.round_rect(x - 3, y + (h - th) / 2 - 2, tw + 6, th + 4, SELECT + (90,), alpha, 4)
        t.alpha = int(255 * alpha)
        t.draw(dstrect=(x, y + (h - th) / 2, tw, th))
        if not self.all and int(now * 2) % 2 == 0:
            pre = shown[:self.cur]
            cx = g.tsize(g.text(pre, size, color))[0] if pre else 0
            g.rect(x + cx + 1, y + h * 0.22, 2, h * 0.56, color, alpha)
        return tw
