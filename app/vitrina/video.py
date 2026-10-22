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
AUDIO_IN = 0.3         # fundido de entrada al empezar (lo hace mpv, justo cuando suena)
AUDIO_RESUME = 0.25    # al reanudar después de una pausa
AUDIO_OUT = 0.6        # fundido de salida al pausar, deslizar o cerrar
AUDIO_LEAD = 0.2       # el fundido empieza este tanto después de lo que ya suena (lo del búfer)
# Los fundidos de salida y de reanudar también los hace mpv, con un filtro de
# volumen que depende del tiempo del propio audio (t). Así no importa cuánto audio
# tenga guardado el sistema por adelantado: el fundido cae justo donde debe, y
# el reproductor solo se cierra cuando lo que ya suena pasó el final del fundido.
_THREADS = []          # hilos de video vivos (para esperarlos al salir)
DEBUG = bool(os.environ.get("VITRINA_DEBUG_AUDIO"))   # imprime los fundidos en la terminal


def wait_all(timeout=2.0):
    """Espera a que los videos terminen de cerrarse (al salir de la app; si no,
    Python puede terminar mientras mpv aún se apaga y cerrarse con error)."""
    end = time.monotonic() + timeout
    for t in list(_THREADS):
        t.join(max(0.0, end - time.monotonic()))


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
        self.volume = 100.0 if audio else 0.0
        self._fade_req = None            # ("out" | "in" | "flat", duración) para el hilo
        self.fade_end = None             # tiempo del audio en que termina el fundido de salida
        self.fade_asked = None           # cuándo se pidió (respaldo por si no hay reloj de audio)
        self.audio_pos = None            # lo que está sonando ahora (audio-pts)
        self._close_now = False
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
        _THREADS[:] = [t for t in _THREADS if t.is_alive()]
        _THREADS.append(self._thread)
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
        # Sin decodificación por hardware: con el dibujo por software de libmpv
        # puede fallar (VideoToolbox en macOS) y las Macs viejas no la tienen.
        opts = dict(vo="libmpv", hwdec="no", keep_open="yes", loglevel="error", audio_buffer=0.1,
                    input_default_bindings=False, input_vo_keyboard=False, osc=False,
                    pause=self.want_pause)
        if not self.audio:
            opts["ao"] = "null"
            opts["mute"] = True
        else:
            opts["volume"] = 100
            opts["af"] = f"lavfi=[afade=t=in:d={AUDIO_IN},volume=volume=1:eval=frame]"
        if self.loop:
            opts["loop_file"] = "inf"
        ctx = None
        try:
            self.mpv = mpv.MPV(**opts)
            ctx = mpv.MpvRenderContext(self.mpv, "sw")
            params = {id(self._front): self._params(self._front), id(self._back): self._params(self._back)}
            self.mpv.play(self.path)
            last_info = 0.0
            applied_pause = self.want_pause
            while not self._stop.is_set():
                if self._fade_req is not None:
                    self._apply_fade(*self._fade_req)
                    self._fade_req = None
                if self.desired_pause != applied_pause:
                    self.mpv.pause = self.desired_pause
                    applied_pause = self.desired_pause
                if self._seek_to is not None:
                    target, self._seek_to = self._seek_to, None
                    try:
                        self.mpv.seek(target, reference="absolute")
                        if self.audio and self.fade_end is None:
                            self._apply_fade("flat", 0)    # al saltar, volumen normal
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

    def _apply_fade(self, kind, duration):
        """(En el hilo del video.) Programa el fundido en el filtro de volumen."""
        try:
            heard = self.mpv.audio_pts
        except Exception:
            heard = None
        base = heard if heard is not None else (self.mpv.time_pos or 0.0)
        if kind == "out":
            st = base + AUDIO_LEAD
            expr = f"min(1,max(0,1-(t-{st:.3f})/{duration:.3f}))"
            self.fade_end = st + duration
        elif kind == "in":
            st = base + 0.1
            expr = f"min(1,max(0,(t-{st:.3f})/{duration:.3f}))"
            self.fade_end = None
        else:
            expr = "1"
            self.fade_end = None
        try:
            self.mpv.command("af-command", "all", "volume", expr)
            if DEBUG:
                print(f"[audio] {kind}: suena {heard}, fundido {expr}", flush=True)
        except Exception as exc:
            if DEBUG:
                print(f"[audio] {kind}: no se pudo ({exc})", flush=True)

    def _fade(self, kind, duration):
        if self.audio:
            self._fade_req = (kind, duration)
            self.fade_asked = time.monotonic()
            if kind != "out":
                self.fade_end = None

    def _read_state(self):
        try:
            if self.audio:
                self.audio_pos = self.mpv.audio_pts
            self.position = self.mpv.time_pos or self.position
            self.duration = self.mpv.duration or self.duration
            if bool(self.mpv.pause) == self.desired_pause:
                self.paused = self.desired_pause
            self.ended = bool(self.mpv.eof_reached)
        except Exception:
            pass

    # -- controles (desde la interfaz) --------------------------------------------

    def play(self):
        """Empieza a reproducir. Si venía de una pausa con fundido, el sonido
        vuelve a entrar suave; al empezar desde cero lo hace el afade inicial."""
        if self.audio and (self.pause_when_silent or self.paused) and self.fade_asked is not None:
            self._fade("in", AUDIO_RESUME)
        self.want_pause = False
        self.pause_when_silent = False
        self.desired_pause = False
        self.paused = False

    def set_paused(self, value):
        if value:
            if self.audio:
                self._fade("out", AUDIO_OUT)      # primero baja el volumen...
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
        if self.paused and not self.pause_when_silent:
            self._close_now = True                # en pausa no suena nada: se cierra ya
            return
        self._fade("out", AUDIO_OUT)

    def frame_alpha(self, now):
        """Opacidad del video sobre su portada: aparece suave con el primer cuadro."""
        if not self.has_frame or self.first_frame_at is None:
            return 0.0
        return min(1.0, (now - self.first_frame_at) / FADE_IN_FRAME)

    # -- por cuadro (desde la interfaz) -------------------------------------------

    def update(self, dt, now=None):
        """Sube el último cuadro a la textura y ajusta el volumen. Devuelve False
        cuando ya se pidió cerrar y terminó el fundido de salida."""
        now = time.monotonic() if now is None else now
        if self.audio:
            # "Ya se escuchó todo el fundido": lo que suena pasó su final. Si no hay
            # reloj de audio (o se atora), un respaldo por tiempo.
            drained = False
            if self.fade_asked is not None and self._fade_req is None:
                if self.fade_end is not None and self.audio_pos is not None:
                    drained = self.audio_pos >= self.fade_end + 0.05
                drained = drained or now - self.fade_asked > AUDIO_LEAD + AUDIO_OUT + 1.2
            if self.pause_when_silent and drained:
                self.desired_pause = True
                self.paused = True
                self.pause_when_silent = False
        else:
            drained = True
        if self.closing and (not self.audio or drained or not self.has_frame or self._close_now):
            if DEBUG and self.audio:
                print(f"[audio] cerrado: sonaba {self.audio_pos}, fin del fundido {self.fade_end}", flush=True)
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
            self.first_frame_at = now
        return True

    def close(self):
        """Cierra en segundo plano (mpv tarda en terminar)."""
        self._stop.set()
        self.texture = None


def fmt_time(sec):
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"
