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
    "Apoya el proyecto en ko-fi.com/danzelot": "Support the project at ko-fi.com/danzelot",
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
