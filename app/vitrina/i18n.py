"""Idiomas: español (por defecto) e inglés.

Los textos se escriben en español en el código y se traducen con tr():

    tr("Ajustes")                      -> "Settings" en inglés
    tr("{n} fotos", n=3)               -> "3 photos"

La app del celular tiene su propia copia de estas traducciones (web/static/app.js).
"""

_lang = ["es"]

LANGS = [("es", "Español"), ("en", "English")]

MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
ABBR_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
ABBR_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS_ES = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
DAYS_EN = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

EN = {
    # Presentación
    "Fotos": "Photos",
    "Mueve el mouse para explorar": "Move the mouse to explore",
    "Preparando fotos {done} de {total}": "Preparing photos {done} of {total}",
    "Preparando videos {done} de {total}": "Preparing videos {done} of {total}",
    "Un día como hoy  ·  {label}": "On this day  ·  {label}",
    "{n} fotos nuevas": "{n} new photos",
    "1 foto nueva": "1 new photo",
    # Barra y niveles
    "Presentación": "Slideshow",
    "Años": "Years",
    "Meses": "Months",
    "Colecciones": "Collections",
    "Ajustes": "Settings",
    "{n} fotos": "{n} photos",
    "{n} fotos en {c}": "{n} photos in {c}",
    "· {c} columnas": "· {c} columns",
    "· {n} con fotos": "· {n} with photos",
    # Visor
    "‹  Volver": "‹  Back",
    "Presentación desde aquí": "Slideshow from here",
    "Preparando video…": "Preparing video…",
    # Ajustes
    "Listo": "Done",
    "Pantalla": "Display",
    "Celular": "Phone",
    "Ken Burns": "Ken Burns",
    "Movimiento lento de las fotos": "Slow motion on photos",
    "Apagado": "Off",
    "Solo zoom": "Zoom only",
    "Zoom y paneo": "Zoom and pan",
    "Un día como hoy": "On this day",
    "Fotos de estas fechas de otros años": "Photos from this date in past years",
    "Fecha y lugar": "Date and place",
    "Abajo a la izquierda": "Bottom left",
    "Reloj": "Clock",
    "Abajo a la derecha": "Bottom right",
    "Oculto": "Hidden",
    "Orden aleatorio": "Shuffle",
    "Mezcla las fotos": "Mixes the photos",
    "Volver a la presentación": "Back to slideshow",
    "Sin mover el mouse": "Without moving the mouse",
    "Idioma": "Language",
    "Español o inglés": "Spanish or English",
    "Apariencia": "Appearance",
    "Automático: claro de día": "Automatic: light by day",
    "Claro": "Light",
    "Oscuro": "Dark",
    "Automático": "Automatic",
    "Modo noche": "Night mode",
    "La pantalla siempre encendida": "Screen always on",
    "Se apaga poco a poco": "Dims slowly",
    "Con el sensor de luz de la Mac": "Uses the Mac's light sensor",
    "Con la cámara: el foquito verde parpadea": "Uses the camera: its green light blinks",
    "Cámara: luz {n} de 255": "Camera: light {n} of 255",
    "Esta computadora no tiene sensor ni cámara": "This computer has no light sensor or camera",
    "Brillo automático": "Auto-brightness",
    "Brillo mínimo": "Minimum brightness",
    "Calibrado": "Calibrated",
    "Para que nunca se vaya a negro": "So the screen never goes black",
    "Calibrar": "Calibrate",
    "Calibrar brillo mínimo": "Calibrate minimum brightness",
    "La pantalla se irá oscureciendo poco a poco.": "The screen will slowly get darker.",
    "Haz clic o presiona una tecla en cuanto deje de verse.": "Click or press a key as soon as you can no longer see it.",
    "Esc para cancelar": "Esc to cancel",
    "Brillo mínimo calibrado": "Minimum brightness calibrated",
    "Noche": "Night",
    "Reloj o pantalla apagada a cierta hora": "Clock or screen off at set hours",
    "Nunca": "Never",
    "Por horario": "Schedule",
    "Por la luz": "Room light",
    "Horario": "Schedule",
    "De noche a mañana": "From night to morning",
    "De noche": "At night",
    "Qué se ve en la pantalla": "What the screen shows",
    "Apagada": "Off",
    "Reloj ventana": "Window clock",
    "Reloj clásico": "Classic clock",
    "Color del reloj clásico": "Classic clock color",
    "Rojo: el que menos molesta": "Red is easiest on the eyes",
    "Blanco": "White",
    "Azul": "Blue",
    "Rojo": "Red",
    "Tecla N: simula la noche para probarlo": "N key: simulate night to try it",
    "Tecla N: vista previa de la noche · H: todos los atajos": "N key: night preview · H: all shortcuts",
    "Vista previa del modo noche": "Night mode preview",
    "Vista previa del modo noche · toca cualquier tecla para salir": "Night mode preview · press any key to exit",
    "Apoya el proyecto en ko-fi.com/danzelot": "Support the project at ko-fi.com/danzelot",
    # Atajos de teclado
    "Sí": "On",
    "No": "Off",
    "Atajos de teclado": "Keyboard shortcuts",
    "Empezar o salir de la presentación": "Start or leave the slideshow",
    "Foto anterior o siguiente": "Previous or next photo",
    "Pausar o seguir el video": "Pause or resume the video",
    "Volver": "Back",
    "Años, Meses, Fotos, Colecciones": "Years, Months, Photos, Collections",
    "Acercar o alejar": "Zoom in or out",
    "Ajustes rápidos": "Quick settings",
    "Apariencia: oscuro, claro o automático": "Appearance: dark, light or automatic",
    "Modo noche ahora": "Night mode now",
    "Esta lista": "This list",
    "Español o inglés": "Spanish or English",
    "La cámara no manda imagen": "The camera isn't sending a picture",
    # Celular
    "Agregar fotos desde el celular": "Add photos from your phone",
    "Escanea el código con la cámara del celular": "Scan the code with your phone's camera",
    "El celular y la Mac deben estar en el mismo WiFi.": "The phone and the Mac must be on the same Wi-Fi.",
    "Celulares conectados": "Connected phones",
    "Ninguno todavía": "None yet",
    "Quitar": "Remove",
    "Sin conexión a la red": "Not connected to a network",
    "Conecta la Mac al WiFi para usar el celular.": "Connect the Mac to Wi-Fi to use your phone.",
    "Falta instalar segno (pip install -r requirements.txt)": "segno is missing (pip install -r requirements.txt)",
    # WiFi y sistema
    "Conectada por cable": "Connected by cable",
    "Conectada a {ssid}": "Connected to {ssid}",
    "Sin conexión": "Not connected",
    "Buscar redes": "Find networks",
    "Buscando…": "Searching…",
    "No se encontraron redes": "No networks found",
    "Con contraseña": "Password protected",
    "Abierta": "Open",
    "Conectada": "Connected",
    "Contraseña de {ssid}": "Password for {ssid}",
    "Escribe con el teclado de la Mac": "Type with the Mac's keyboard",
    "Conectar": "Connect",
    "Cancelar": "Cancel",
    "Mostrar": "Show",
    "Ocultar": "Hide",
    "Conectando…": "Connecting…",
    "Contraseña incorrecta": "Wrong password",
    "No se pudo conectar": "Couldn't connect",
    "Configurar WiFi": "Set up Wi-Fi",
    "Escanear código": "Scan code",
    "Muestra el código QR de tu WiFi": "Show your Wi-Fi QR code",
    "Acerca el celular a la cámara (unos 20–30 cm).": "Hold your phone close to the camera (about 20–30 cm).",
    "No se pudo abrir la cámara": "Couldn't open the camera",
    "Abriendo la cámara…": "Opening the camera…",
    "Ese código no es de una red WiFi": "That code isn't a Wi-Fi network",
    "iPhone: app Contraseñas → Wi-Fi → tu red → Mostrar código QR de la red": "iPhone: Passwords app → Wi-Fi → your network → Show Network QR Code",
    "Android: Ajustes → Wi-Fi → tu red → Compartir": "Android: Settings → Wi-Fi → your network → Share",
    "Conectando a {ssid}…": "Connecting to {ssid}…",
    "Apagar": "Shut down",
    "Reiniciar": "Restart",
    "Apagar…": "Shut down…",
    "Reposo": "Sleep",
    "¿Apagar la Vitrina?": "Shut down Vitrina?",
    "En reposo, la pantalla se apaga y gasta casi nada. Despierta al abrir la tapa o con cualquier tecla.":
        "Sleep turns the screen off and uses almost no power. Open the lid or press any key to wake it.",
    # Instalar
    "Instalar en esta Mac…": "Install on this Mac…",
    "Instalar Vitrina en esta Mac": "Install Vitrina on this Mac",
    "Vitrina quedará en el disco de la Mac y arrancará sola, sin la USB. Las fotos, el WiFi y los ajustes de ahora se pasan a la instalación.":
        "Vitrina will live on the Mac's disk and start by itself, without the USB. Your current photos, Wi-Fi and settings move over.",
    "Buscando el disco…": "Looking for the disk…",
    "No se encontró un disco interno donde instalar.": "No internal disk was found to install on.",
    "Disco: {m} · {s}": "Disk: {m} · {s}",
    "Se borrará TODO lo que tiene este disco: macOS, programas, documentos y fotos. No se puede deshacer.":
        "EVERYTHING on this disk will be erased: macOS, apps, documents and photos. This can't be undone.",
    "Continuar": "Continue",
    "Se borrará macOS con todos sus programas, documentos y fotos. No se puede deshacer.":
        "macOS will be erased with all its apps, documents and photos. This can't be undone.",
    "Se conserva la recuperación de macOS (⌘R al prender) por si algún día quieres volver a instalarlo.":
        "The macOS recovery partition (⌘R at startup) is kept, in case you ever want to reinstall it.",
    "¿Borrar el disco e instalar?": "Erase the disk and install?",
    "Último aviso: se borrará {m} ({s}) y no habrá forma de recuperar lo que tiene.":
        "Last warning: {m} ({s}) will be erased and its contents can't be recovered.",
    "Deja la Mac conectada a la corriente. Tarda unos minutos.": "Keep the Mac plugged in. It takes a few minutes.",
    "Borrar e instalar ({n})": "Erase and install ({n})",
    "Borrar e instalar": "Erase and install",
    "Instalando Vitrina…": "Installing Vitrina…",
    "Paso {n} de {t} · {s}": "Step {n} of {t} · {s}",
    "Empezando": "Starting",
    "Guardando el firmware de la cámara": "Saving the camera firmware",
    "Preparando el disco": "Preparing the disk",
    "Copiando Vitrina": "Copying Vitrina",
    "Instalando el arranque": "Installing the boot loader",
    "Pasando tus fotos y ajustes": "Moving your photos and settings",
    "Terminando": "Finishing",
    "No apagues la Mac ni quites la USB.": "Don't turn off the Mac or remove the USB.",
    "Vitrina quedó instalada. Quita la USB y reinicia: arrancará sola desde el disco.":
        "Vitrina is installed. Remove the USB and restart: it will start from the disk by itself.",
    "No se pudo instalar": "Couldn't install",
    "Puedes intentarlo otra vez. Los detalles están en el Diagnóstico del celular.":
        "You can try again. Details are in Diagnostics on your phone.",
    "Cerrar": "Close",
    # Actualizar
    "Actualizaciones": "Updates",
    "Versión {v}": "Version {v}",
    "Versión {v} · al día": "Version {v} · up to date",
    "Hay una versión nueva: {v}": "A new version is available: {v}",
    "Listo: versión {v}. Reiniciando…": "Done: version {v}. Restarting…",
    "Actualizar": "Update",
    "Buscar": "Check",
    "Buscando la versión nueva": "Looking for the new version",
    "Descargando la versión {v}": "Downloading version {v}",
    "Actualizando el logo de arranque": "Updating the boot logo",
    # 0.11
    "Conexión": "Connection",
    "General": "General",
    "Qué pasa sola en la presentación": "What plays in the slideshow",
    "Fotos y videos": "Photos and videos",
    "Solo fotos": "Photos only",
    "Solo videos": "Videos only",
    "Fotos, videos o ambos": "Photos, videos or both",
    "Tecla H en cualquier momento": "Press H anytime",
    "Ver": "Show",
    "Bloquear teclado": "Lock keyboard",
    "Para que nadie (ni el gato) cambie nada: mantén Control + L 3 s": "So nobody (not even the cat) changes anything: hold Control + L for 3 s",
    "Bloquear": "Lock",
    "Mantén… {n}": "Hold… {n}",
    "Teclado bloqueado": "Keyboard locked",
    "Teclado desbloqueado": "Keyboard unlocked",
    "Teclado bloqueado · Mantén Control + L 3 s para desbloquear": "Keyboard locked · Hold Control + L for 3 s to unlock",
    "Bloquear el teclado (mantener 3 s)": "Lock the keyboard (hold 3 s)",
    "{n} en {c}": "{n} in {c}",
    "Fotos en la memoria USB": "Photos on the USB drive",
    "Se encontraron {n} en “{l}”.": "Found {n} on “{l}”.",
    "Ahora no": "Not now",
    "Importar": "Import",
    "Importando…": "Importing…",
    "{a} de {b}": "{a} of {b}",
    "No quites la memoria.": "Don't remove the drive.",
    "No se terminó de importar": "The import didn't finish",
    "{a} nuevas · {d} ya estaban": "{a} new · {d} already here",
    "Ya puedes quitar la memoria.": "You can remove the drive now.",
    "Colección «{l}»": "Collection “{l}”",
    "Sin colección": "No collection",
    "La memoria se quitó antes de terminar": "The drive was removed before finishing",
    "videos, 2019, diciembre, Cancún…": "videos, 2019, december, Paris…",
    "Nada coincide con “{q}”": "Nothing matches “{q}”",
    "Buscar (videos, 2019, diciembre, un lugar…)": "Search (videos, 2019, december, a place…)",
    # Biblioteca vacía
    "No hay fotos todavía": "No photos yet",
    "Escanea el código con el celular para agregar fotos": "Scan the code with your phone to add photos",
}


def set_lang(lang):
    _lang[0] = lang if lang in ("es", "en") else "es"


def lang():
    return _lang[0]


def tr(_text, **kw):
    t = EN.get(_text, _text) if _lang[0] == "en" else _text
    if not kw:
        return t
    try:
        return t.format(**kw)
    except (KeyError, IndexError, ValueError):     # un texto mal formado nunca debe cerrar la app
        return t


def photos(n):
    if _lang[0] == "en":
        return f"{n:,} photo" if n == 1 else f"{n:,} photos"
    return f"{n:,} foto" if n == 1 else f"{n:,} fotos"


def month_abbr(m):
    """m de 0 a 11."""
    return (ABBR_EN if _lang[0] == "en" else ABBR_ES)[m]


def weekday_abbr(wd):
    return (DAYS_EN if _lang[0] == "en" else DAYS_ES)[wd]


def long_date(d):
    if _lang[0] == "en":
        return f"{MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    return f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}"


def years_ago(n):
    if _lang[0] == "en":
        return "1 year ago" if n == 1 else f"{n} years ago"
    return "Hace 1 año" if n == 1 else f"Hace {n} años"


def ampm(hour):
    if _lang[0] == "en":
        return "AM" if hour < 12 else "PM"
    return "a. m." if hour < 12 else "p. m."


def media_count(photos, videos):
    """'5 fotos · 5 videos', '48 fotos', '1 video'."""
    en = _lang[0] == "en"
    parts = []
    if photos or not videos:
        parts.append(f"{photos:,} " + (("photo" if photos == 1 else "photos") if en else ("foto" if photos == 1 else "fotos")))
    if videos:
        parts.append(f"{videos:,} video" + ("" if videos == 1 else "s"))
    return " · ".join(parts)


def new_media(photos, videos):
    """Aviso de lo recién subido: '3 fotos y 1 video nuevos'."""
    en = _lang[0] == "en"
    if en:
        bits = []
        if photos:
            bits.append(f"{photos} new photo" + ("" if photos == 1 else "s"))
        if videos:
            bits.append(f"{videos} new video" + ("" if videos == 1 else "s"))
        return " and ".join(bits)
    if photos and videos:
        return (f"{photos} foto" if photos == 1 else f"{photos} fotos") + " y " + \
            (f"{videos} video nuevos" if videos == 1 else f"{videos} videos nuevos")
    if videos:
        return "1 video nuevo" if videos == 1 else f"{videos} videos nuevos"
    return "1 foto nueva" if photos == 1 else f"{photos} fotos nuevas"
