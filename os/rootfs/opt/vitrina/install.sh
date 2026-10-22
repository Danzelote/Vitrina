#!/bin/bash
# Instala Vitrina en el disco interno de la Mac (desde la USB).
#
#   install.sh detect                 → "DISK <dispositivo> <bytes> <modelo>" por cada disco posible
#   install.sh run <disco> [extra]    → BORRA el disco e instala; "extra" se agrega a la línea
#                                       de arranque (la prueba automática pide la consola serial)
#
# Mientras trabaja escribe líneas que la app muestra:
#   PASO <n> <total> <texto>  ·  AVANCE <0-100>  ·  LISTO  ·  ERROR <texto>
#
# Lo que hace: guarda el firmware de la cámara, crea dos particiones (arranque
# EFI y el sistema), copia el sistema de la USB, instala el arranque y pasa las
# fotos, el WiFi y los ajustes de ahora a la instalación.
set -uo pipefail
export LC_ALL=C

MEDIUM=/run/live/medium
LOG=/run/vitrina-install.log
TARGET=/run/vitrina-target
SQ=/run/vitrina-squash
TOTAL=6

say() { echo "$*"; echo "$*" >>"$LOG"; }
die() { say "ERROR $*"; cleanup; exit 1; }
step() { say "PASO $1 $TOTAL $2"; }
run() { echo "+ $*" >>"$LOG"; "$@" >>"$LOG" 2>&1; }

cleanup() {
    sync
    for m in "$TARGET/boot/efi" "$TARGET/dev" "$TARGET/proc" "$TARGET/sys" "$TARGET" "$SQ"; do
        mountpoint -q "$m" 2>/dev/null && umount -lf "$m" 2>/dev/null
    done
    return 0
}

live_disk() {
    local src
    src=$(findmnt -n -o SOURCE "$MEDIUM" 2>/dev/null) || return 0
    lsblk -npo PKNAME "$src" 2>/dev/null | head -1
    echo "$src"
}

detect() {
    local skip line NAME TYPE RM SIZE TRAN MODEL
    skip=$(live_disk)
    while IFS= read -r line; do
        NAME="" TYPE="" RM="" SIZE=0 TRAN="" MODEL=""
        eval "$line"
        [ "$TYPE" = disk ] || continue
        case "$NAME" in /dev/sr*|/dev/loop*|/dev/zram*|/dev/ram*) continue ;; esac
        echo "$skip" | grep -qx "$NAME" && continue
        [ "$TRAN" = usb ] && continue
        [ "${SIZE:-0}" -ge 4000000000 ] || continue
        echo "DISK $NAME $SIZE ${MODEL:-Disco}"
    done < <(lsblk -dbnpP -o NAME,TYPE,RM,SIZE,TRAN,MODEL 2>/dev/null)
}

part() {    # part /dev/sda 1 → /dev/sda1 · part /dev/nvme0n1 1 → /dev/nvme0n1p1
    case "$1" in *[0-9]) echo "${1}p$2" ;; *) echo "$1$2" ;; esac
}

rsync_progress() {    # copia y va diciendo AVANCE (0–100)
    local last=-1 pct
    rsync "$@" --info=progress2 --no-inc-recursive 2>>"$LOG" | tr '\r' '\n' | while IFS= read -r line; do
        pct=$(echo "$line" | grep -o '[0-9]\+%' | head -1 | tr -d '%')
        if [ -n "$pct" ] && [ "$pct" != "$last" ]; then
            say "AVANCE $pct"
            last=$pct
        fi
    done
    return "${PIPESTATUS[0]}"
}

install_to() {
    local disk=$1 extra=${2:-}
    : >"$LOG"
    [ -d "$MEDIUM/live" ] || die "Vitrina no está corriendo desde la USB"
    [ -b "$disk" ] || die "No existe el disco $disk"
    detect | awk '{print $2}' | grep -qx "$disk" || die "Ese disco no se puede usar ($disk)"
    [ -f "$MEDIUM/instalar/BOOTX64.EFI" ] || die "A esta USB le falta el arranque para instalar"

    step 1 "Guardando el firmware de la cámara"
    mkdir -p /run/vitrina-keep
    for f in /lib/firmware/isight.fw /var/lib/vitrina/isight.fw; do
        [ -s "$f" ] && cp -f "$f" /run/vitrina-keep/isight.fw
    done

    step 2 "Preparando el disco"
    for p in $(lsblk -lnpo NAME "$disk" | tail -n +2); do umount -lf "$p" 2>/dev/null; swapoff "$p" 2>/dev/null; done
    run wipefs -a -f "$disk" || die "No se pudo borrar el disco"
    run sgdisk --zap-all "$disk"
    run sgdisk -n1:1M:+300M -t1:EF00 -c1:EFI -n2:0:0 -t2:8300 -c2:Vitrina "$disk" || die "No se pudo particionar"
    run partprobe "$disk"
    udevadm settle 2>/dev/null
    sleep 1
    local esp root
    esp=$(part "$disk" 1)
    root=$(part "$disk" 2)
    run mkfs.vfat -F 32 -n EFI "$esp" || die "No se pudo formatear la partición de arranque"
    # Sin las funciones nuevas de ext4 que el arranque (GRUB) todavía no sabe leer.
    run mkfs.ext4 -F -q -L vitrina -O ^orphan_file,^metadata_csum_seed "$root" || die "No se pudo formatear el disco"
    mkdir -p "$TARGET" "$SQ"
    run mount "$root" "$TARGET" || die "No se pudo abrir el disco nuevo"

    step 3 "Copiando Vitrina"
    run mount -o ro,loop "$MEDIUM/live/filesystem.squashfs" "$SQ" || die "No se pudo leer la USB"
    rsync_progress -aHAX "$SQ/" "$TARGET/" || die "Falló la copia (¿la USB está bien?)"
    umount "$SQ"

    step 4 "Instalando el arranque"
    local kver uuid espuuid
    kver=$(ls "$TARGET/lib/modules" | sort -V | tail -1)
    cp "$MEDIUM/live/vmlinuz" "$TARGET/boot/vmlinuz" || die "Falta el kernel en la USB"
    cp "$MEDIUM/live/initrd.img" "$TARGET/boot/initrd.img" || die "Falta el initrd en la USB"
    uuid=$(blkid -s UUID -o value "$root")
    espuuid=$(blkid -s UUID -o value "$esp")
    mkdir -p "$TARGET/boot/efi" "$TARGET/boot/grub"
    cat >"$TARGET/etc/fstab" <<EOF
# Vitrina instalada
UUID=$uuid  /          ext4  noatime,errors=remount-ro  0 1
UUID=$espuuid  /boot/efi  vfat  umask=0077,noauto,nofail  0 2
EOF
    echo "Vitrina $(cat "$MEDIUM/live/vitrina.id" 2>/dev/null) · $kver · $(date -u +%F)" >"$TARGET/etc/vitrina-instalada"
    run mount "$esp" "$TARGET/boot/efi" || die "No se pudo abrir la partición de arranque"
    # El kernel y la configuración del arranque van en la partición EFI (FAT):
    # así GRUB no necesita leer ext4.
    mkdir -p "$TARGET/boot/efi/EFI/BOOT" "$TARGET/boot/efi/EFI/vitrina"
    cp "$TARGET/boot/vmlinuz" "$TARGET/boot/initrd.img" "$TARGET/boot/efi/EFI/vitrina/" \
        || die "No se pudo copiar el kernel al arranque"
    cat >"$TARGET/boot/efi/EFI/vitrina/grub.cfg" <<EOF
# Sin menú (en algunas Macs con NVIDIA el menú queda invisible).
set timeout=0
set timeout_style=hidden
linux (\$root)/EFI/vitrina/vmlinuz root=UUID=$uuid ro quiet splash loglevel=0 rd.udev.log_level=3 udev.log_level=3 vt.global_cursor_default=0 systemd.show_status=0 rd.systemd.show_status=0 $extra
initrd (\$root)/EFI/vitrina/initrd.img
boot
EOF
    cp "$MEDIUM/instalar/BOOTX64.EFI" "$MEDIUM/instalar/BOOTIA32.EFI" "$TARGET/boot/efi/EFI/BOOT/" \
        || die "No se pudo copiar el arranque"
    # Las Mac arrancan solas con /EFI/BOOT (sin tocar su memoria NVRAM). En otras
    # computadoras se agrega además una entrada de arranque.
    if [ -d /sys/firmware/efi/efivars ] && ! grep -qi apple /sys/class/dmi/id/sys_vendor 2>/dev/null \
            && command -v efibootmgr >/dev/null; then
        local loader='\EFI\BOOT\BOOTX64.EFI'
        [ "$(cat /sys/firmware/efi/fw_platform_size 2>/dev/null)" = 32 ] && loader='\EFI\BOOT\BOOTIA32.EFI'
        run efibootmgr -q -c -d "$disk" -p 1 -L Vitrina -l "$loader"
    fi
    umount "$TARGET/boot/efi"

    step 5 "Pasando tus fotos y ajustes"
    : >"$TARGET/etc/machine-id"
    mkdir -p "$TARGET/var/lib/vitrina" "$TARGET/lib/firmware"
    if [ -s /run/vitrina-keep/isight.fw ]; then
        cp /run/vitrina-keep/isight.fw "$TARGET/var/lib/vitrina/isight.fw"
        cp /run/vitrina-keep/isight.fw "$TARGET/lib/firmware/isight.fw"
    fi
    if [ -d /etc/NetworkManager/system-connections ]; then
        mkdir -p "$TARGET/etc/NetworkManager/system-connections"
        cp -a /etc/NetworkManager/system-connections/. "$TARGET/etc/NetworkManager/system-connections/" 2>/dev/null
    fi
    [ -e /etc/localtime ] && cp -P /etc/localtime "$TARGET/etc/localtime"
    [ -f /etc/timezone ] && cp /etc/timezone "$TARGET/etc/timezone"
    rsync_progress -aHAX /home/vitrina/ "$TARGET/home/vitrina/" || die "Falló la copia de tus fotos"

    step 6 "Terminando"
    sync
    cleanup
    say "LISTO"
}

case "${1:-}" in
    detect) detect ;;
    run)
        [ -n "${2:-}" ] || { echo "uso: install.sh run <disco> [extra]"; exit 2; }
        # Que no se duerma ni se apague a medio camino (tapa, tecla de encendido).
        if [ -z "${VITRINA_INHIBIT:-}" ] && command -v systemd-inhibit >/dev/null; then
            VITRINA_INHIBIT=1 exec systemd-inhibit --what=sleep:shutdown:handle-lid-switch:handle-power-key \
                --who=Vitrina --why="Instalando" --mode=block "$0" "$@"
        fi
        install_to "$2" "${3:-}"
        ;;
    *) echo "uso: install.sh detect | run <disco> [extra]"; exit 2 ;;
esac
