#!/bin/bash
# Prueba del instalador: arranca la imagen en una máquina virtual con un disco
# vacío, instala sola ("vitrina.autoinstall"), y luego arranca ese disco con
# UEFI (como una Mac) para comprobar que Vitrina abre ya instalada.
#
#   bash os/install-test.sh out/vitrina-X.iso
set -uo pipefail
ISO=$1
DIR=$(cd "$(dirname "$ISO")" && pwd)
DISK=$DIR/disco-prueba.qcow2
LOG1=$DIR/instalar.log
LOG2=$DIR/instalada.log
MON=/tmp/vitrina-qemu-inst.sock
CODE=$(ls /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd 2>/dev/null | head -1)
VARS_SRC=$(ls /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd 2>/dev/null | head -1)
VARS=$DIR/ovmf-vars.fd
rm -f "$DISK" "$LOG1" "$LOG2" "$MON"

ACCEL=""
if [ -e /dev/kvm ]; then
    sudo chmod 666 /dev/kvm 2>/dev/null || true
    [ -w /dev/kvm ] && ACCEL="-enable-kvm -cpu host"
fi
qemu-img create -q -f qcow2 "$DISK" 8G

echo "== 1) Instalar en el disco virtual"
timeout 1800 qemu-system-x86_64 $ACCEL -m 2048 -smp 2 -cdrom "$ISO" \
    -kernel "$DIR/vmlinuz" -initrd "$DIR/initrd.img" \
    -append "boot=live vitrina.autoinstall console=ttyS0,115200 systemd.journald.forward_to_console=1" \
    -drive "file=$DISK,if=virtio,format=qcow2" -vga std -display none -serial "file:$LOG1" -nic none -no-reboot
grep -aE "Instalando en|PASO|AVANCE|LISTO|ERROR|INSTALACION OK" "$LOG1" | awk '!/AVANCE/ || ++n % 10 == 1' | tail -n 40
if ! grep -aq "INSTALACION OK" "$LOG1"; then
    echo "PRUEBA FALLÓ: no se instaló"
    exit 1
fi

echo "== 2) Arrancar el disco instalado con UEFI ($CODE)"
cp "$VARS_SRC" "$VARS"
qemu-system-x86_64 $ACCEL -m 2048 -smp 2 -machine q35 \
    -drive "if=pflash,format=raw,readonly=on,file=$CODE" -drive "if=pflash,format=raw,file=$VARS" \
    -drive "file=$DISK,if=virtio,format=qcow2" -vga std -display none -serial "file:$LOG2" \
    -monitor "unix:$MON,server,nowait" -nic user,model=e1000 &
QEMU=$!
ok=1
for _ in $(seq 1 90); do
    sleep 5
    if grep -aq "fotos encontradas" "$LOG2" 2>/dev/null; then ok=0; break; fi
    kill -0 $QEMU 2>/dev/null || break
done
[ $ok -eq 0 ] && sleep 20
echo "screendump $DIR/instalada.png -f png" | socat - "UNIX-CONNECT:$MON" >/dev/null 2>&1 || true
sleep 2
kill $QEMU 2>/dev/null
wait $QEMU 2>/dev/null
grep -aE "vitrina|Traceback|Error|error" "$LOG2" | tail -n 25
[ $ok -eq 0 ] && echo "PRUEBA OK: Vitrina instalada arrancó sola" || echo "PRUEBA FALLÓ: el disco instalado no arrancó la app"
exit $ok
