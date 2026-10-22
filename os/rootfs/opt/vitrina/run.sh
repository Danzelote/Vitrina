#!/bin/sh
# Arranca Vitrina en pantalla completa y la vuelve a abrir si se cierra.
export VITRINA_SYSTEM=1
export SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR=0
FOTOS="$HOME/Fotos"
mkdir -p "$FOTOS"
amixer -q sset Master 80% unmute 2>/dev/null
amixer -q sset PCM 100% unmute 2>/dev/null
while true; do
    # Sin teclado de consola (</dev/null): si un programa hijo (ffmpeg) intentara
    # leer de la terminal, el sistema pausaría toda la app (le pasó a la 0.10.0).
    /opt/vitrina/venv/bin/python -u /opt/vitrina/app/main.py --folder "$FOTOS" --fullscreen </dev/null 2>&1 | logger -t vitrina
    sleep 1
done
