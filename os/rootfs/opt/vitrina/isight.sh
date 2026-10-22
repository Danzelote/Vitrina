#!/bin/sh
# Cámara iSight de las MacBook 2006–2009 (05ac:8300): arranca sin firmware y
# macOS se lo carga al prender. El firmware es de Apple (no se puede incluir en
# la USB), así que se toma del macOS de la propia Mac, solo leyendo su disco.
# Se guarda en /var/lib/vitrina para que siga ahí después de instalar.
LOG=/run/vitrina-isight.log
exec >"$LOG" 2>&1
FW=/lib/firmware/isight.fw
SAVED=/var/lib/vitrina/isight.fw
KEXT=System/Library/Extensions/IOUSBFamily.kext/Contents/PlugIns/AppleUSBVideoSupport.kext/Contents/MacOS/AppleUSBVideoSupport

has_isight() { grep -qx 8300 /sys/bus/usb/devices/*/idProduct 2>/dev/null; }
if ! has_isight; then echo "sin iSight que necesite firmware"; exit 0; fi

mkdir -p /var/lib/vitrina /lib/firmware
if [ ! -s "$FW" ] && [ -s "$SAVED" ]; then
    cp "$SAVED" "$FW" && echo "firmware guardado"
fi
if [ ! -s "$FW" ]; then
    MNT=/run/vitrina-mac
    mkdir -p "$MNT"
    for dev in $(blkid -t TYPE=hfsplus -o device 2>/dev/null); do
        echo "revisando $dev"
        mount -t hfsplus -o ro "$dev" "$MNT" 2>&1 || continue
        if [ -f "$MNT/$KEXT" ]; then
            echo "encontrado en $dev"
            ift-extract --apple-driver "$MNT/$KEXT" --output-directory /lib/firmware 2>&1
        fi
        umount "$MNT"
        [ -s "$FW" ] && break
    done
fi
if [ ! -s "$FW" ]; then echo "no se encontró el firmware"; exit 0; fi
cp -f "$FW" "$SAVED"

# Cargarlo: el módulo del kernel lo pide al conectar la cámara; también ift-load.
modprobe -r isight_firmware 2>/dev/null
modprobe isight_firmware 2>&1
sleep 2
if has_isight; then
    for d in /sys/bus/usb/devices/*; do
        [ "$(cat "$d/idVendor" 2>/dev/null)" = 05ac ] && [ "$(cat "$d/idProduct" 2>/dev/null)" = 8300 ] || continue
        bus=$(cat "$d/busnum"); num=$(cat "$d/devnum")
        echo "ift-load en $bus/$num"
        for L in /lib/udev/ift-load /usr/lib/udev/ift-load "$(command -v ift-load)"; do
            [ -x "$L" ] && { BUSNUM=$bus DEVNUM=$num DEVICE=/dev/bus/usb/$(printf %03d "$bus")/$(printf %03d "$num") \
                "$L" --firmware "$FW" 2>&1; break; }
        done
    done
    sleep 3
fi
if has_isight; then echo "la cámara sigue sin firmware (apaga la Mac por completo y vuelve a prender)"; else echo "cámara lista"; fi
ls /dev/video* 2>/dev/null
