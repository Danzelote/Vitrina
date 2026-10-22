#!/bin/bash
# Actualiza la Vitrina instalada con la versión más nueva publicada en GitHub,
# sin tocar las fotos ni los ajustes.
#
#   update.sh check   → "ACTUAL <versión>" y luego "NUEVA <versión>" o "AL_DIA"
#   update.sh apply   → descarga, revisa y cambia la app; escribe
#                       PASO <n> <total> <texto> · LISTO <versión> · ERROR <texto>
#   update.sh rollback → regresa a la versión anterior (lo usa run.sh si la nueva no arranca)
#
# Solo baja del repositorio oficial (no acepta otras direcciones). Si la app
# nueva no arranca, run.sh regresa sola a la anterior (/opt/vitrina/app.old).
set -uo pipefail
export LC_ALL=C

REPO=Danzelote/Vitrina
OPT=/opt/vitrina
WORK=/var/tmp/vitrina-update
LOG=/var/log/vitrina-update.log
TOTAL=5

say() { echo "$*"; echo "$(date '+%F %T') $*" >>"$LOG"; }
die() { say "ERROR $*"; exit 1; }
step() { say "PASO $1 $TOTAL $2"; }
run() { echo "+ $*" >>"$LOG"; "$@" >>"$LOG" 2>&1; }

current() { sed -n 's/^__version__ = "\(.*\)"/\1/p' "$OPT/app/vitrina/__init__.py"; }

# La versión más nueva con paquete de la app: "<versión> <url del .tar.gz> <url del .sha256>"
latest() {
    python3 - "$REPO" <<'PY'
import json, re, sys, urllib.request
repo = sys.argv[1]
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases?per_page=15",
                             headers={"Accept": "application/vnd.github+json", "User-Agent": "Vitrina"})
releases = json.load(urllib.request.urlopen(req, timeout=20))
best = None
for r in releases:
    assets = {a["name"]: a["browser_download_url"] for a in r.get("assets", [])}
    for name, url in assets.items():
        m = re.fullmatch(r"vitrina-app-([0-9.]+)\.tar\.gz", name)
        if m and name + ".sha256" in assets:
            v = tuple(int(x) for x in m.group(1).split("."))
            if best is None or v > best[0]:
                best = (v, m.group(1), url, assets[name + ".sha256"])
if best:
    print(best[1], best[2], best[3])
PY
}

newer() {   # newer A B → éxito si A es más nueva que B
    python3 -c "import sys; a, b = (tuple(int(x) for x in v.split('.')) for v in sys.argv[1:3]); sys.exit(0 if a > b else 1)" "$1" "$2"
}

check() {
    local cur info ver
    cur=$(current)
    echo "ACTUAL $cur"
    info=$(latest 2>>"$LOG") || { echo "ERROR Sin conexión con GitHub"; exit 1; }
    ver=${info%% *}
    if [ -n "$ver" ] && newer "$ver" "$cur"; then echo "NUEVA $ver"; else echo "AL_DIA"; fi
}

copy_os() {     # archivos del sistema que vienen en el paquete (servicios, scripts, logo)
    local src=$1/os/rootfs
    [ -d "$src" ] || return 0
    for f in opt/vitrina/run.sh opt/vitrina/xinitrc opt/vitrina/blank.xbm opt/vitrina/isight.sh \
             opt/vitrina/install.sh opt/vitrina/update.sh; do
        [ -f "$src/$f" ] && install -m 755 "$src/$f" "/$f"
    done
    [ -f "$src/opt/vitrina/blank.xbm" ] && chmod 644 /opt/vitrina/blank.xbm
    for d in etc/systemd/system etc/systemd/logind.conf.d etc/NetworkManager/conf.d etc/polkit-1/rules.d \
             etc/udev/rules.d etc/X11/xorg.conf.d usr/lib/systemd/system-sleep; do
        [ -d "$src/$d" ] || continue
        mkdir -p "/$d"
        cp -r "$src/$d/." "/$d/"
    done
    chmod 755 /usr/lib/systemd/system-sleep/vitrina-wifi 2>/dev/null
    if [ -f "$src/etc/sudoers.d/vitrina" ] && visudo -c -q -f "$src/etc/sudoers.d/vitrina"; then
        install -m 440 "$src/etc/sudoers.d/vitrina" /etc/sudoers.d/vitrina
    fi
    systemctl daemon-reload 2>/dev/null
    # El logo de arranque vive dentro del initrd: solo si cambió se regenera.
    local theme=usr/share/plymouth/themes/vitrina
    if [ -d "$src/$theme" ] && ! diff -rq "$src/$theme" "/$theme" >/dev/null 2>&1; then
        mkdir -p "/$theme"
        cp -r "$src/$theme/." "/$theme/"
        step 4 "Actualizando el logo de arranque"
        local kver
        kver=$(ls /lib/modules | sort -V | tail -1)
        if [ -f "/boot/initrd.img-$kver" ]; then run update-initramfs -u -k "$kver"; else run update-initramfs -c -k "$kver"; fi
        if [ -s "/boot/initrd.img-$kver" ]; then
            mountpoint -q /boot/efi || mount /boot/efi 2>>"$LOG"
            if [ -d /boot/efi/EFI/vitrina ]; then
                cp /boot/efi/EFI/vitrina/initrd.img /boot/efi/EFI/vitrina/initrd.img.anterior 2>/dev/null
                cp "/boot/initrd.img-$kver" /boot/efi/EFI/vitrina/initrd.img
            fi
            umount /boot/efi 2>/dev/null
        fi
    fi
}

apply() {
    [ -f /etc/vitrina-instalada ] || die "Solo se puede actualizar una Vitrina instalada"
    local cur info ver url sumurl
    cur=$(current)
    step 1 "Buscando la versión nueva"
    info=$(latest 2>>"$LOG") || die "Sin conexión con GitHub"
    read -r ver url sumurl <<<"$info"
    [ -n "$ver" ] || die "No hay versiones publicadas"
    newer "$ver" "$cur" || { say "LISTO $cur"; exit 0; }

    step 2 "Descargando la versión $ver"
    rm -rf "$WORK" && mkdir -p "$WORK"
    python3 - "$url" "$WORK/app.tar.gz" "$sumurl" "$WORK/app.tar.gz.sha256" <<'PY' >>"$LOG" 2>&1 || die "No se pudo descargar"
import sys, urllib.request
for url, dest in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    req = urllib.request.Request(url, headers={"User-Agent": "Vitrina"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
PY
    (cd "$WORK" && sha256sum -c --status <(awk '{print $1"  app.tar.gz"}' app.tar.gz.sha256)) \
        || die "La descarga llegó dañada"
    mkdir -p "$WORK/new"
    tar -xzf "$WORK/app.tar.gz" -C "$WORK/new" || die "El paquete está dañado"
    [ -f "$WORK/new/app/main.py" ] && [ -f "$WORK/new/app/vitrina/__init__.py" ] || die "El paquete no tiene la app"

    step 3 "Instalando la versión $ver"
    if [ -f "$WORK/new/requirements.txt" ] && ! cmp -s "$WORK/new/requirements.txt" "$OPT/requirements.txt"; then
        run "$OPT/venv/bin/pip" install -q --no-cache-dir -r "$WORK/new/requirements.txt" \
            || die "No se pudieron instalar las librerías nuevas"
        cp "$WORK/new/requirements.txt" "$OPT/requirements.txt"
    fi
    rm -rf "$OPT/app.new"
    cp -a "$WORK/new/app" "$OPT/app.new"
    find "$OPT/app.new" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
    rm -rf "$OPT/app.old"
    mv "$OPT/app" "$OPT/app.old" && mv "$OPT/app.new" "$OPT/app" || die "No se pudo cambiar la app"
    copy_os "$WORK/new"

    step 5 "Terminando"
    rm -rf "$WORK"
    sync
    say "LISTO $ver"
}

rollback() {    # la app nueva no arranca: regresar a la anterior
    [ -d "$OPT/app.old" ] || { echo "No hay versión anterior"; exit 1; }
    rm -rf "$OPT/app.mala"
    mv "$OPT/app" "$OPT/app.mala" && mv "$OPT/app.old" "$OPT/app"
    say "REGRESO $(current)"
}

case "${1:-}" in
    check) check ;;
    apply) apply ;;
    rollback) rollback ;;
    *) echo "uso: update.sh check | apply"; exit 2 ;;
esac
