"""Reproducción de video con mpv, dibujada dentro de la interfaz.

mpv decodifica (y reproduce el audio); cada cuadro se copia a una textura de
SDL, así el video se dibuja, se escala y se desvanece como cualquier foto.

Todo lo lento (crear el reproductor, abrir el archivo, decodificar cada
cuadro y cerrarlo) ocurre en un hilo propio de cada video. La interfaz solo
sube a la gráfica el último cuadro listo, así las animaciones nunca esperan.

Si mpv no está instalado, Vitrina sigue funcionando y muestra la portada de
los videos en lugar de reproducirlos.
"""

import ctypes
import os
import sys
import threading
import time

import pygame
from pygame._sdl2.video import Texture

if sys.platform == "darwin":  # dónde instala Homebrew la biblioteca de mpv
    extra = "/opt/homebrew/lib:/usr/local/lib"
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = extra + ":" + os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")

try:
    import mpv
    AVAILABLE = True
except Exception:  # pragma: no cover
    mpv = None
    AVAILABLE = False

# Parámetros del render por software de libmpv (render.h)
_SW_SIZE, _SW_FORMAT, _SW_STRIDE, _SW_POINTER = 17, 18, 19, 20
FADE_IN_FRAME = 0.25   # segundos en que el primer cuadro aparece sobre la portada


class Player:
    """Un video en reproducción.

    path          archivo a reproducir
    size          tamaño (ancho, alto) en píxeles al que se dibuja cada cuadro
    audio         con sonido (con fundido de entrada); si no, silencio total
    loop          repetir al terminar
    start_paused  prepararlo (primer cuadro listo) sin empezar a reproducir
    """

    def __init__(self, renderer, path, size, audio=False, loop=False, start_paused=False):
        self.renderer = renderer
        self.path = path
        self.w, self.h = max(2, int(size[0]) // 2 * 2), max(2, int(size[1]) // 2 * 2)
        self.audio = audio
        self.loop = loop
        self.volume = 0.0
        self.target_volume = 0.0 if start_paused or not audio else 100.0
        self.fade_speed = 200.0          # unidades de volumen por segundo (0.5 s)
        self.want_pause = start_paused
        self.pause_when_silent = False
        self.closing = False
        self.closed = False
        self.texture = None
        self.has_frame = False
        self.first_frame_at = None
        self.mpv = None
        # Estado que el hilo actualiza y la interfaz lee.
        self._lock = threading.Lock()
        self._front = (ctypes.c_ubyte * (self.w * self.h * 4))()
        self._back = (ctypes.c_ubyte * (self.w * self.h * 4))()
        self._new_frame = False
        self._stop = threading.Event()
        self.position = 0.0
        self.duration = 0.0
        self.paused = start_paused
        self.ended = False
        # Órdenes que la interfaz deja y el hilo del video aplica (nunca bloquean).
        self.desired_pause = start_paused
        self._seek_to = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- hilo del video ---------------------------------------------------------

    def _params(self, buf):
        size = (ctypes.c_int * 2)(self.w, self.h)
        fmt = ctypes.c_char_p(b"rgb0")
        stride = ctypes.c_size_t(self.w * 4)
        arr = (mpv.MpvRenderParam * 5)()
        keep = [size, fmt, stride]
        for k, (tid, ptr) in enumerate([
            (_SW_SIZE, ctypes.cast(size, ctypes.c_void_p)),
            (_SW_FORMAT, ctypes.cast(fmt, ctypes.c_void_p)),
            (_SW_STRIDE, ctypes.cast(ctypes.pointer(stride), ctypes.c_void_p)),
            (_SW_POINTER, ctypes.cast(buf, ctypes.c_void_p)),
            (0, None),
        ]):
            arr[k].type_id = tid
            arr[k].data = ptr
        return arr, keep

    def _run(self):
        opts = dict(vo="libmpv", hwdec="auto-safe", keep_open="yes", loglevel="error",
                    input_default_bindings=False, input_vo_keyboard=False, osc=False,
                    pause=self.want_pause)
        if not self.audio:
            opts["ao"] = "null"
            opts["mute"] = True
        else:
            opts["volume"] = 0
        if self.loop:
            opts["loop_file"] = "inf"
        ctx = None
        try:
            self.mpv = mpv.MPV(**opts)
            ctx = mpv.MpvRenderContext(self.mpv, "sw")
            params = {id(self._front): self._params(self._front), id(self._back): self._params(self._back)}
            self.mpv.play(self.path)
            last_info = 0.0
            applied_volume, applied_pause = -1.0, self.want_pause
            while not self._stop.is_set():
                vol = round(self.volume, 1)
                if self.audio and vol != applied_volume:
                    self.mpv.volume = vol
                    applied_volume = vol
                if self.desired_pause != applied_pause:
                    self.mpv.pause = self.desired_pause
                    applied_pause = self.desired_pause
                if self._seek_to is not None:
                    target, self._seek_to = self._seek_to, None
                    try:
                        self.mpv.seek(target, reference="absolute")
                    except Exception:
                        pass
                if ctx.update():
                    back = self._back
                    mpv._mpv_render_context_render(ctx._handle, params[id(back)][0])
                    with self._lock:
                        self._front, self._back = self._back, self._front
                        self._new_frame = True
                now = time.monotonic()
                if now - last_info > 0.1:
                    last_info = now
                    self._read_state()
                time.sleep(0.004)
        except Exception as exc:
            print("Video:", exc)
        finally:
            try:
                if ctx is not None:
                    ctx.free()
            except Exception:
                pass
            try:
                if self.mpv is not None:
                    self.mpv.terminate()
            except Exception:
                pass
            self.closed = True

    def _read_state(self):
        try:
            self.position = self.mpv.time_pos or self.position
            self.duration = self.mpv.duration or self.duration
            if bool(self.mpv.pause) == self.desired_pause:
                self.paused = self.desired_pause
            self.ended = bool(self.mpv.eof_reached)
        except Exception:
            pass

    # -- controles (desde la interfaz) --------------------------------------------

    def play(self):
        """Empieza a reproducir (con fundido de entrada del sonido)."""
        self.want_pause = False
        self.pause_when_silent = False
        self.desired_pause = False
        self.paused = False
        self.target_volume = 100.0 if self.audio else 0.0

    def set_paused(self, value):
        if value:
            if self.audio:
                self.target_volume = 0.0          # primero baja el volumen...
                self.pause_when_silent = True     # ...y luego pausa
            else:
                self.desired_pause = True
                self.paused = True
        else:
            self.play()

    @property
    def is_playing(self):
        return not self.paused and not self.ended and not self.pause_when_silent

    def seek(self, seconds):
        self._seek_to = max(0.0, seconds)
        self.position = self._seek_to

    def restart(self):
        self.seek(0)
        self.ended = False
        self.play()

    def fade_out_and_close(self):
        """Baja el volumen y luego se cierra (ver update)."""
        self.closing = True
        self.target_volume = 0.0

    def frame_alpha(self, now):
        """Opacidad del video sobre su portada: aparece suave con el primer cuadro."""
        if not self.has_frame or self.first_frame_at is None:
            return 0.0
        return min(1.0, (now - self.first_frame_at) / FADE_IN_FRAME)

    # -- por cuadro (desde la interfaz) -------------------------------------------

    def update(self, dt, now=None):
        """Sube el último cuadro a la textura y ajusta el volumen. Devuelve False
        cuando ya se pidió cerrar y terminó el fundido de salida."""
        if self.audio:
            step = self.fade_speed * dt
            if self.volume < self.target_volume:
                self.volume = min(self.target_volume, self.volume + step)
            elif self.volume > self.target_volume:
                self.volume = max(self.target_volume, self.volume - step)
            if self.volume <= 0.0 and self.pause_when_silent:
                self.desired_pause = True
                self.paused = True
                self.pause_when_silent = False
        if self.closing and (not self.audio or self.volume <= 0.0):
            self.close()
            return False
        with self._lock:
            fresh = self._new_frame
            self._new_frame = False
            if fresh:
                surf = pygame.image.frombuffer(self._front, (self.w, self.h), "RGBX")
                if self.texture is None:
                    self.texture = Texture(self.renderer, (self.w, self.h), streaming=True)
                    self.texture.blend_mode = pygame.BLENDMODE_BLEND
                self.texture.update(surf)
        if fresh and not self.has_frame:
            self.has_frame = True
            self.first_frame_at = now if now is not None else time.monotonic()
        return True

    def close(self):
        """Cierra en segundo plano (mpv tarda en terminar)."""
        self._stop.set()
        self.texture = None


def fmt_time(sec):
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"
