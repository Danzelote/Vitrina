#!/bin/bash
# Construye la imagen de la USB de Vitrina: Debian 13 (trixie) mínimo que
# arranca directo en la app, con el driver del WiFi Broadcom ya incluido.
#
# Corre como root en un Debian trixie (por ejemplo, el contenedor de GitHub
# Actions; ver .github/workflows/imagen.yml). Necesita internet.
#
#   sudo bash os/build.sh            → out/vitrina-<versión>.iso
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(dirname "$HERE")
OUT=${OUT:-$REPO/out}
WORK=${WORK:-/tmp/vitrina-build}
MIRROR=${MIRROR:-http://deb.debian.org/debian}
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/app/vitrina/__init__.py")
ROOT=$WORK/rootfs
ISO=$WORK/iso

log() { echo; echo "=== $* ==="; }

log "Herramientas para construir"
apt-get update -q
apt-get install -y -q --no-install-recommends \
    mmdebstrap squashfs-tools xorriso grub-common grub-efi-amd64-bin grub-efi-ia32-bin \
    mtools dosfstools isolinux syslinux-common ca-certificates python3

rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

# -----------------------------------------------------------------------------
log "Sistema base (Debian $VERSION)"
PKGS=(
    # Arranque en vivo y sistema
    linux-image-amd64 live-boot systemd-sysv dbus udev sudo ca-certificates tzdata
    systemd-timesyncd procps kmod
    # Red: WiFi y cable
    network-manager wpasupplicant iw rfkill firmware-linux-free polkitd dbus-user-session
    # WiFi Broadcom de las MacBook (driver "wl"): se compila aquí y luego se quitan los compiladores
    broadcom-sta-dkms dkms linux-headers-amd64
    # Pantalla: X mínimo, sin escritorio
    xserver-xorg-core xserver-xorg-legacy xserver-xorg-input-libinput xinit x11-xserver-utils x11-utils
    libgl1 libgl1-mesa-dri libglx-mesa0 libegl1 libx11-6 libxext6 libxcursor1 libxi6 libxrandr2
    libxss1 libxinerama1 libxkbcommon0 libxxf86vm1
    # Logo de arranque y apagado (sin textos de Linux)
    plymouth
    # Sonido
    alsa-utils
    # Cámara iSight (firmware tomado del macOS de la Mac) y lectura del disco de macOS
    isight-firmware-tools util-linux
    # Brillo automático con la cámara (exposición fija) y lectura del código QR del WiFi
    v4l-utils libzbar0t64
    # Instalar en el disco de la Mac
    rsync gdisk dosfstools e2fsprogs efibootmgr parted
    # La app
    python3 python3-venv libmpv2 ffmpeg
)
mmdebstrap --variant=minbase --components="main contrib non-free non-free-firmware" \
    --include="$(IFS=,; echo "${PKGS[*]}")" \
    trixie "$ROOT" "$MIRROR"

KVER=$(ls "$ROOT/lib/modules" | sort -V | tail -1)
echo "Kernel: $KVER"

# -----------------------------------------------------------------------------
log "Driver del WiFi Broadcom (wl)"
WL=$(find "$ROOT/lib/modules/$KVER" -name 'wl.ko*' | head -1)
if [ -z "$WL" ]; then
    echo "No se compiló el driver wl" >&2
    find "$ROOT/var/lib/dkms" -name make.log -exec tail -n 40 {} \; >&2 || true
    exit 1
fi
cp "$WL" "$WORK/"
cp "$ROOT/etc/modprobe.d/broadcom-sta-dkms.conf" "$WORK/wl-blacklist.conf"

mount --bind /dev "$ROOT/dev"
mount -t proc proc "$ROOT/proc"
mount -t sysfs sys "$ROOT/sys"
cleanup() { umount -lf "$ROOT/dev" "$ROOT/proc" "$ROOT/sys" 2>/dev/null || true; }
trap cleanup EXIT
cp /etc/resolv.conf "$ROOT/etc/resolv.conf"
in_root() { chroot "$ROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 "$@"; }

# Se quitan los compiladores (ahorran ~300 MB) y el driver se deja instalado a mano.
in_root apt-get purge -y -q broadcom-sta-dkms dkms 'linux-headers-*' 'linux-kbuild-*'
in_root apt-get autoremove -y -q --purge     # se lleva gcc, make, etc.
mkdir -p "$ROOT/lib/modules/$KVER/updates"
cp "$WORK/$(basename "$WL")" "$ROOT/lib/modules/$KVER/updates/"
cp "$WORK/wl-blacklist.conf" "$ROOT/etc/modprobe.d/broadcom-sta-dkms.conf"
echo wl > "$ROOT/etc/modules-load.d/wl.conf"
in_root depmod -a "$KVER"

# -----------------------------------------------------------------------------
log "Configuración de Vitrina"
cp -a "$HERE/rootfs/." "$ROOT/"
chmod 440 "$ROOT/etc/sudoers.d/vitrina"
chmod 755 "$ROOT/usr/lib/systemd/system-sleep/vitrina-wifi" "$ROOT/opt/vitrina/isight.sh" "$ROOT/opt/vitrina/install.sh" "$ROOT/opt/vitrina/update.sh"
echo vitrina > "$ROOT/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tvitrina\n' > "$ROOT/etc/hosts"
ln -sf /usr/share/zoneinfo/America/Mexico_City "$ROOT/etc/localtime"
echo America/Mexico_City > "$ROOT/etc/timezone"
echo 'LANG=C.UTF-8' > "$ROOT/etc/default/locale"
printf 'allowed_users=anybody\nneeds_root_rights=yes\n' > "$ROOT/etc/X11/Xwrapper.config"

for g in audio video netdev input render plugdev; do
    in_root getent group "$g" >/dev/null || in_root groupadd -r "$g"
done
in_root useradd -m -s /bin/bash -G audio,video,netdev,input,render,plugdev vitrina
in_root passwd -d vitrina
install -o 1000 -g 1000 -m 644 "$HERE/rootfs/opt/vitrina/bash_profile" "$ROOT/home/vitrina/.bash_profile"
mkdir -p "$ROOT/home/vitrina/Fotos"
in_root chown -R vitrina:vitrina /home/vitrina

# Sin tareas de fondo que gasten la Mac vieja.
for unit in apt-daily.timer apt-daily-upgrade.timer man-db.timer e2scrub_all.timer fstrim.timer; do
    in_root systemctl mask "$unit" >/dev/null 2>&1 || true
done
in_root systemctl enable NetworkManager systemd-timesyncd vitrina-isight >/dev/null 2>&1 || true
in_root systemctl enable vitrina.service vitrina-autoinstall.service
in_root systemctl mask getty@tty1.service
# Logo de arranque (queda dentro del initramfs al regenerarlo abajo)
in_root plymouth-set-default-theme vitrina
# Sin textos al entrar: ni el mensaje del día ni "último acceso"
: > "$ROOT/etc/motd"
touch "$ROOT/home/vitrina/.hushlogin"

# -----------------------------------------------------------------------------
log "La app"
mkdir -p "$ROOT/opt/vitrina/app"
cp -a "$REPO/app/main.py" "$REPO/app/vitrina" "$ROOT/opt/vitrina/app/"
cp "$REPO/requirements.txt" "$ROOT/opt/vitrina/"
in_root python3 -m venv /opt/vitrina/venv
in_root /opt/vitrina/venv/bin/pip install -q --no-cache-dir -r /opt/vitrina/requirements.txt
in_root /opt/vitrina/venv/bin/python -c "import pygame, PIL, mpv, segno, pillow_heif; from pyzbar import pyzbar; print('app: dependencias OK')"
find "$ROOT/opt/vitrina" -name __pycache__ -prune -exec rm -rf {} +

# -----------------------------------------------------------------------------
log "Limpieza"
in_root update-initramfs -u -k "$KVER"
in_root apt-get clean
rm -rf "$ROOT"/var/lib/apt/lists/* "$ROOT"/var/cache/* "$ROOT"/tmp/* "$ROOT"/var/log/*.log
rm -rf "$ROOT"/usr/share/doc/* "$ROOT"/usr/share/man/* "$ROOT"/usr/share/info/*
find "$ROOT/usr/share/locale" -mindepth 1 -maxdepth 1 ! -name 'es*' ! -name 'en*' -exec rm -rf {} +
rm -f "$ROOT/etc/resolv.conf"
cleanup
trap - EXIT

# -----------------------------------------------------------------------------
log "Imagen ISO"
mkdir -p "$ISO/live" "$ISO/boot/grub" "$ISO/EFI/BOOT" "$ISO/isolinux"
cp "$ROOT/boot/vmlinuz-$KVER" "$ISO/live/vmlinuz"
cp "$ROOT/boot/initrd.img-$KVER" "$ISO/live/initrd.img"
echo "Vitrina $VERSION" > "$ISO/live/vitrina.id"
mksquashfs "$ROOT" "$ISO/live/filesystem.squashfs" -comp xz -Xbcj x86 -b 1M -noappend -quiet \
    -e boot/vmlinuz-"$KVER" -e boot/initrd.img-"$KVER"

# EFI de 64 y de 32 bits (las MacBook de 2006–2008 tienen EFI de 32 bits).
cp "$HERE/boot/grub.cfg" "$ISO/boot/grub/grub.cfg"
grub-mkstandalone --format=x86_64-efi --output="$ISO/EFI/BOOT/BOOTX64.EFI" \
    --locales="" --fonts="" "boot/grub/grub.cfg=$HERE/boot/grub.cfg"
grub-mkstandalone --format=i386-efi --output="$ISO/EFI/BOOT/BOOTIA32.EFI" \
    --locales="" --fonts="" "boot/grub/grub.cfg=$HERE/boot/grub.cfg"
# Arranque para cuando Vitrina queda instalada en el disco (lo copia install.sh):
# busca el disco instalado y lee su configuración.
mkdir -p "$ISO/instalar"
for fmt in x86_64-efi:BOOTX64 i386-efi:BOOTIA32; do
    grub-mkstandalone --format="${fmt%%:*}" --output="$ISO/instalar/${fmt##*:}.EFI" \
        --locales="" --fonts="" "boot/grub/grub.cfg=$HERE/boot/grub-instalada.cfg"
done
EFIIMG="$ISO/boot/grub/efi.img"
dd if=/dev/zero of="$EFIIMG" bs=1M count=24 status=none
mkfs.vfat -n VITRINA_EFI "$EFIIMG" >/dev/null
mmd -i "$EFIIMG" ::/EFI ::/EFI/BOOT
mcopy -i "$EFIIMG" "$ISO/EFI/BOOT/BOOTX64.EFI" "$ISO/EFI/BOOT/BOOTIA32.EFI" ::/EFI/BOOT/

# Arranque de PC (BIOS), útil para probar en otras computadoras.
cp /usr/lib/ISOLINUX/isolinux.bin "$ISO/isolinux/"
cp /usr/lib/syslinux/modules/bios/ldlinux.c32 "$ISO/isolinux/"
cp "$HERE/boot/isolinux.cfg" "$ISO/isolinux/isolinux.cfg"

NAME="vitrina-$VERSION.iso"
xorriso -as mkisofs -r -V "VITRINA" -o "$OUT/$NAME" -J -joliet-long -cache-inodes \
    -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
    -b isolinux/isolinux.bin -c isolinux/boot.cat -boot-load-size 4 -boot-info-table -no-emul-boot \
    -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot -isohybrid-gpt-basdat -isohybrid-apm-hfsplus \
    "$ISO"
(cd "$OUT" && sha256sum "$NAME" > "$NAME.sha256")
cp "$ISO/live/vmlinuz" "$ISO/live/initrd.img" "$OUT/"   # para la prueba automática
ls -lh "$OUT"
log "Listo: $OUT/$NAME"
