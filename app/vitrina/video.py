"""Reproducción de video con mpv, dibujada dentro de la interfaz.

mpv decodifica (y reproduce el audio); cada cuadro se copia a una textura de
SDL, así el video se dibuja, se escala y se desvanece como cualquier foto.
Si mpv no está instalado, Vitrina sigue funcionando y muestra la portada de
los videos en lugar de reproducirlos.
"""

import ctypes
import os
import sys

import pygame
from pygame._sdl2.video import Texture

if sys.platform == "darwin":  # dónde instala Homebrew la biblioteca de mpv
    extra = "/opt/homebrew/lib:/usr/local/lib"
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = extra + ":" + os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")

try:
    import mpv
    AVAILABLE = True
except Exception as exc:  # pragma: no cover
    mpv = None
    AVAILABLE = False
    UNAVAILABLE_REASON = str(exc)

# Parámetros del render por software de libmpv (render.h)
_SW_SIZE, _SW_FORMAT, _SW_STRIDE, _SW_POINTER = 17, 18, 19, 20


class Player:
    """Un video en reproducción.

    path    archivo a reproducir
    size    tamaño (ancho, alto) en píxeles al que se dibuja cada cuadro
    audio   con sonido (con fundido de entrada); si no, silencio total
    loop    repetir al terminar
    """

    def __init__(self, renderer, path, size, audio=False, loop=False):
        self.renderer = renderer
        self.w, self.h = max(2, int(size[0]) // 2 * 2), max(2, int(size[1]) // 2 * 2)
        self.audio = audio
        self.volume = 0.0
        self.target_volume = 100.0 if audio else 0.0
        self.fade_speed = 200.0          # unidades de volumen por segundo (0.5 s)
        self.closing = False
        self.texture = None
        self.has_frame = False
        opts = dict(vo="libmpv", hwdec="auto-safe", keep_open="yes", loglevel="error",
                    input_default_bindings=False, input_vo_keyboard=False, osc=False)
        if not audio:
            opts["ao"] = "null"
            opts["mute"] = True
        else:
            opts["volume"] = 0
        if loop:
            opts["loop_file"] = "inf"
        self.mpv = mpv.MPV(**opts)
        self.ctx = mpv.MpvRenderContext(self.mpv, "sw")
        self.buf = (ctypes.c_ubyte * (self.w * self.h * 4))()
        self._size = (ctypes.c_int * 2)(self.w, self.h)
        self._fmt = ctypes.c_char_p(b"rgb0")
        self._stride = ctypes.c_size_t(self.w * 4)
        self._params = (mpv.MpvRenderParam * 5)()
        for k, (tid, ptr) in enumerate([
            (_SW_SIZE, ctypes.cast(self._size, ctypes.c_void_p)),
            (_SW_FORMAT, ctypes.cast(self._fmt, ctypes.c_void_p)),
            (_SW_STRIDE, ctypes.cast(ctypes.pointer(self._stride), ctypes.c_void_p)),
            (_SW_POINTER, ctypes.cast(self.buf, ctypes.c_void_p)),
            (0, None),
        ]):
            self._params[k].type_id = tid
            self._params[k].data = ptr
        self.mpv.play(path)

    # -- estado ---------------------------------------------------------------

    @property
    def position(self):
        try:
            return self.mpv.time_pos or 0.0
        except Exception:
            return 0.0

    @property
    def duration(self):
        try:
            return self.mpv.duration or 0.0
        except Exception:
            return 0.0

    @property
    def paused(self):
        try:
            return bool(self.mpv.pause)
        except Exception:
            return True

    @property
    def ended(self):
        try:
            return bool(self.mpv.eof_reached)
        except Exception:
            return False

    def set_paused(self, value):
        if self.audio:
            # Pausa con fundido: primero baja el volumen, luego pausa.
            self.target_volume = 0.0 if value else 100.0
            if not value:
                self._set("pause", False)
            self._pause_when_silent = value
        else:
            self._set("pause", value)

    def restart(self):
        try:
            self.mpv.seek(0, reference="absolute")
        except Exception:
            pass
        self.set_paused(False)

    def fade_out_and_close(self):
        """Baja el volumen y luego se cierra (ver update)."""
        self.closing = True
        self.target_volume = 0.0

    def _set(self, name, value):
        try:
            setattr(self.mpv, name, value)
        except Exception:
            pass

    # -- por cuadro ------------------------------------------------------------

    def update(self, dt):
        """Copia el cuadro nuevo a la textura y ajusta el volumen. Devuelve
        False cuando ya terminó de cerrarse."""
        if self.audio:
            step = self.fade_speed * dt
            if self.volume < self.target_volume:
                self.volume = min(self.target_volume, self.volume + step)
            elif self.volume > self.target_volume:
                self.volume = max(self.target_volume, self.volume - step)
            self._set("volume", self.volume)
            if self.volume <= 0.0 and getattr(self, "_pause_when_silent", False):
                self._set("pause", True)
                self._pause_when_silent = False
        if self.closing and (not self.audio or self.volume <= 0.0):
            self.close()
            return False
        try:
            if self.ctx.update():
                mpv._mpv_render_context_render(self.ctx._handle, self._params)
                surf = pygame.image.frombuffer(self.buf, (self.w, self.h), "RGBX")
                if self.texture is None:
                    self.texture = Texture(self.renderer, (self.w, self.h), streaming=True)
                    self.texture.blend_mode = pygame.BLENDMODE_BLEND
                self.texture.update(surf)
                self.has_frame = True
        except Exception:
            pass
        return True

    def close(self):
        try:
            self.ctx.free()
        except Exception:
            pass
        try:
            self.mpv.terminate()
        except Exception:
            pass
        self.texture = None


def fmt_time(sec):
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"
