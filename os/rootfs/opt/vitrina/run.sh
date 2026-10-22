#!/bin/sh
# Arranca Vitrina en pantalla completa y la vuelve a abrir si se cierra.
export VITRINA_SYSTEM=1
export SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR=0
FOTOS="$HOME/Fotos"
mkdir -p "$FOTOS"
amixer -q sset Master 80% unmute 2>/dev/null
amixer -q sset PCM 100% unmute 2>/dev/null
fails=0
while true; do
    start=$(date +%s)
    # Sin teclado de consola (</dev/null): si un programa hijo (ffmpeg) intentara
    # leer de la terminal, el sistema pausaría toda la app (le pasó a la 0.10.0).
    /opt/vitrina/venv/bin/python -u /opt/vitrina/app/main.py --folder "$FOTOS" --fullscreen </dev/null 2>&1 | logger -t vitrina
    # Si la app se cierra enseguida varias veces seguidas justo después de una
    # actualización, se regresa a la versión anterior.
    if [ $(( $(date +%s) - start )) -lt 25 ]; then fails=$((fails + 1)); else fails=0; fi
    if [ $fails -ge 3 ] && [ -d /opt/vitrina/app.old ]; then
        sudo -n /opt/vitrina/update.sh rollback 2>&1 | logger -t vitrina
        fails=0
    fi
    sleep 1
done
