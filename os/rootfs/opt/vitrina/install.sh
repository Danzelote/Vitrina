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
        local mode=todo
        [ -n "$(keep_plan "$NAME")" ] && mode=conservar
        echo "DISK $NAME $SIZE $mode ${MODEL:-Disco}"
    done < <(lsblk -dbnpP -o NAME,TYPE,RM,SIZE,TRAN,MODEL 2>/dev/null)
}

# Tipos de partición (GPT) que importan
GUID_EFI=c12a7328-f81f-11d2-ba4b-00a0c93ec93b
GUID_APPLE_BOOT=426f6f74-0000-11aa-aa11-00306543ecac       # "Recovery HD" de macOS
GUID_HFS=48465300-0000-11aa-aa11-00306543ecac
GUID_CORESTORAGE=53746f72-6167-11aa-aa11-00306543ecac
GUID_APFS=7c3457ef-0000-11aa-aa11-00306543ecac
GUID_LINUX=0fc63daf-8483-4772-8e79-3d69d8477de4             # una Vitrina instalada antes

# Si el disco tiene la recuperación de macOS, se conserva: solo se reemplaza la
# partición de macOS y se usa la partición EFI que ya existe.
#   → "<esp> <partición de macOS>"  (vacío si no aplica)
keep_plan() {
    local disk=$1 esp="" big="" bigsize=0 recovery=0 name type size label
    while read -r name type size label; do
        [ "$name" = "$disk" ] && continue
        case "${type,,}" in
            $GUID_EFI) [ -z "$esp" ] && esp=$name ;;
            $GUID_APPLE_BOOT) recovery=1 ;;
            $GUID_HFS|$GUID_CORESTORAGE|$GUID_APFS|$GUID_LINUX)
                [ "${type,,}" = "$GUID_LINUX" ] && [ "$label" != Vitrina ] && continue
                if [ "${size:-0}" -gt "$bigsize" ]; then big=$name; bigsize=$size; fi ;;
        esac
    done < <(lsblk -lnpbo NAME,PARTTYPE,SIZE,PARTLABEL "$disk" 2>/dev/null)
    if [ $recovery = 1 ] && [ -n "$esp" ] && [ -n "$big" ] && [ "$bigsize" -ge 4000000000 ]; then
        echo "$esp $big"
    fi
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
    local esp root plan
    plan=$(keep_plan "$disk")
    if [ -n "$plan" ]; then
        # Se conserva la recuperación de macOS: solo se reemplaza la partición de macOS.
        read -r esp root <<<"$plan"
        say "MODO conservar"
        local num
        num=$(cat "/sys/class/block/$(basename "$root")/partition")
        run wipefs -a -f "$root" || die "No se pudo borrar macOS"
        run sgdisk -t "$num:8300" -c "$num:Vitrina" "$disk" || die "No se pudo cambiar la partición"
        run partprobe "$disk"
        udevadm settle 2>/dev/null
        sleep 1
        if [ "$(blkid -s TYPE -o value "$esp")" != vfat ]; then
            run mkfs.vfat -F 32 -n EFI "$esp" || die "No se pudo formatear la partición de arranque"
        fi
    else
        run wipefs -a -f "$disk" || die "No se pudo borrar el disco"
        run sgdisk --zap-all "$disk"
        run sgdisk -n1:1M:+300M -t1:EF00 -c1:EFI -n2:0:0 -t2:8300 -c2:Vitrina "$disk" || die "No se pudo particionar"
        run partprobe "$disk"
        udevadm settle 2>/dev/null
        sleep 1
        esp=$(part "$disk" 1)
        root=$(part "$disk" 2)
        run mkfs.vfat -F 32 -n EFI "$esp" || die "No se pudo formatear la partición de arranque"
    fi
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
    rm -f "$TARGET/boot/efi/EFI/vitrina/"*        # una instalación anterior
    local need free
    need=$(( $(stat -c %s "$TARGET/boot/vmlinuz") + $(stat -c %s "$TARGET/boot/initrd.img") + 8000000 ))
    free=$(( $(stat -f -c '%a * %S' "$TARGET/boot/efi") ))
    [ "$free" -ge "$need" ] || die "La partición de arranque no tiene espacio ($((free / 1000000)) MB libres)"
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

# -- Memorias USB con fotos (para importarlas; solo lectura) -------------------------
USBDIR=/run/vitrina-usb

usb_list() {    # "USB <partición> <sistema de archivos> <nombre>" de memorias conectadas
    local skip line NAME TYPE FSTYPE LABEL PKNAME tran
    skip=$(live_disk)
    while IFS= read -r line; do
        NAME="" TYPE="" FSTYPE="" LABEL="" PKNAME=""
        eval "$line"
        case "$TYPE" in part|disk) ;; *) continue ;; esac
        case "$FSTYPE" in vfat|exfat|ntfs|hfsplus|ext4|ext3|ext2) ;; *) continue ;; esac
        echo "$skip" | grep -qx "$NAME" && continue
        [ -n "$PKNAME" ] && echo "$skip" | grep -qx "$PKNAME" && continue
        tran=$(lsblk -dno TRAN "${PKNAME:-$NAME}" 2>/dev/null | tr -d ' ')
        [ "$tran" = usb ] || continue
        echo "USB $NAME $FSTYPE ${LABEL:-USB}"
    done < <(lsblk -npP -o NAME,TYPE,FSTYPE,LABEL,PKNAME 2>/dev/null)
}

usb_mount() {
    local dev=$1 fs dir opts
    usb_list | awk '{print $2}' | grep -qx "$dev" || { echo "ERROR no es una memoria USB"; exit 1; }
    fs=$(blkid -s TYPE -o value "$dev")
    dir=$USBDIR/$(basename "$dev")
    mkdir -p "$dir"
    mountpoint -q "$dir" && { echo "MOUNT $dir"; return; }
    opts=ro,nosuid,nodev,noexec
    case "$fs" in
        vfat) opts=$opts,uid=1000,gid=1000,utf8 ;;
        exfat) opts=$opts,uid=1000,gid=1000 ;;
        ntfs) fs=ntfs3; opts=$opts,uid=1000,gid=1000 ;;
        hfsplus) opts=$opts,uid=1000,gid=1000 ;;
    esac
    if mount -t "$fs" -o "$opts" "$dev" "$dir" 2>/dev/null || mount -o ro "$dev" "$dir" 2>/dev/null; then
        echo "MOUNT $dir"
    else
        rmdir "$dir" 2>/dev/null
        echo "ERROR no se pudo abrir la memoria"
        exit 1
    fi
}

usb_umount() {
    local dir=$USBDIR/$(basename "$1")
    case "$1" in /dev/*) ;; *) exit 1 ;; esac
    umount "$dir" 2>/dev/null || umount -l "$dir" 2>/dev/null
    rmdir "$dir" 2>/dev/null
    echo "OK"
}

# -- Pantalla de arranque negra en vez de gris (Mac) -----------------------------------
# Las Mac leen la variable DefaultBackgroundColor de su memoria NVRAM para el color
# de la pantalla al prender. Se pone en negro (como hace macOS en las Mac nuevas).
# Se deshace con el reinicio de NVRAM (⌘ ⌥ P R al prender). Algunas Mac viejas la ignoran.
boot_black() {
    grep -qi apple /sys/class/dmi/id/sys_vendor 2>/dev/null || { echo "NO_MAC"; return 0; }
    local dir=/sys/firmware/efi/efivars
    [ -d "$dir" ] || { echo "SIN_EFI"; return 0; }
    mountpoint -q "$dir" || mount -t efivarfs efivarfs "$dir" 2>/dev/null
    local var=$dir/DefaultBackgroundColor-4d1ede05-38c7-4a6a-9cc6-4bcca8b38c14
    if [ -f "$var" ] && [ "$(od -An -tx1 -j4 "$var" | tr -d ' \n')" = 000000 ]; then
        echo "YA"; return 0
    fi
    [ -f "$var" ] && chattr -i "$var" 2>/dev/null
    if printf '\x07\x00\x00\x00\x00\x00\x00' >"$var" 2>/dev/null; then echo "OK"; else echo "ERROR"; fi
}

case "${1:-}" in
    detect) detect ;;
    boot-black) boot_black ;;
    usb-list) usb_list ;;
    usb-mount) [ -n "${2:-}" ] && usb_mount "$2" ;;
    usb-umount) [ -n "${2:-}" ] && usb_umount "$2" ;;
    run)
        [ -n "${2:-}" ] || { echo "uso: install.sh run <disco> [extra]"; exit 2; }
        # Que no se duerma ni se apague a medio camino (tapa, tecla de encendido).
        if [ -z "${VITRINA_INHIBIT:-}" ] && command -v systemd-inhibit >/dev/null; then
            VITRINA_INHIBIT=1 exec systemd-inhibit --what=sleep:shutdown:handle-lid-switch:handle-power-key \
                --who=Vitrina --why="Instalando" --mode=block "$0" "$@"
        fi
        install_to "$2" "${3:-}"
        ;;
    *) echo "uso: install.sh detect | run <disco> [extra] | usb-list | usb-mount <dev> | usb-umount <dev>"; exit 2 ;;
esac
