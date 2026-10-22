#!/bin/bash
# Prueba automática de la imagen: la arranca en una máquina virtual y espera a
# que Vitrina abra. Deja el registro (serial.log) y una captura (pantalla.png).
#
#   bash os/smoke.sh out/vitrina-X.iso
set -uo pipefail
ISO=$1
DIR=$(cd "$(dirname "$ISO")" && pwd)
LOG=$DIR/serial.log
MON=/tmp/vitrina-qemu.sock
rm -f "$LOG" "$MON"

ACCEL=""
if [ -e /dev/kvm ]; then
    sudo chmod 666 /dev/kvm 2>/dev/null || true
    [ -w /dev/kvm ] && ACCEL="-enable-kvm -cpu host"
fi
echo "Aceleración: ${ACCEL:-ninguna}"

qemu-system-x86_64 $ACCEL -m 2048 -smp 2 -cdrom "$ISO" \
    -kernel "$DIR/vmlinuz" -initrd "$DIR/initrd.img" \
    -append "boot=live quiet splash plymouth.ignore-serial-consoles console=ttyS0,115200 systemd.journald.forward_to_console=1" \
    -vga std -display none -serial "file:$LOG" -monitor "unix:$MON,server,nowait" \
    -nic user,model=e1000 &
QEMU=$!

ok=1
shot=0
for _ in $(seq 1 120); do
    sleep 5
    shot=$((shot + 1))
    if [ $shot -le 6 ]; then     # el logo de arranque, antes de que abra la app
        echo "screendump $DIR/arranque-$shot.png -f png" | socat - "UNIX-CONNECT:$MON" >/dev/null 2>&1 || true
    fi
    if grep -q "fotos encontradas" "$LOG" 2>/dev/null; then ok=0; break; fi
    kill -0 $QEMU 2>/dev/null || break
done
[ $ok -eq 0 ] && sleep 25      # deja que la app dibuje
echo "screendump $DIR/pantalla.png -f png" | socat - "UNIX-CONNECT:$MON" >/dev/null 2>&1 || true
sleep 2
kill $QEMU 2>/dev/null
wait $QEMU 2>/dev/null

echo "---- Vitrina en la máquina virtual ----"
grep -aE "vitrina|Traceback|Error|error|wl |NetworkManager.*state" "$LOG" | tail -n 60
[ $ok -eq 0 ] && echo "PRUEBA OK: la app abrió" || echo "PRUEBA FALLÓ: la app no abrió"
exit $ok
