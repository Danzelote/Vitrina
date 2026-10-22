# Desarrollo

Cómo correr Vitrina en tu computadora mientras se desarrolla. Funciona en macOS y en Linux.

## Preparar (una sola vez)

En macOS, con [Homebrew](https://brew.sh):

```bash
brew install python git mpv ffmpeg
git clone https://github.com/Danzelote/Vitrina.git ~/Vitrina
cd ~/Vitrina
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Correr

Desde la carpeta del proyecto, con el entorno activado (`source .venv/bin/activate`):

```bash
# Con fotos de prueba (140)
python app/main.py --demo

# Con más fotos de prueba, para sentir los niveles de meses y años
python app/main.py --demo 500

# Con una carpeta tuya (cada subcarpeta es una colección)
python app/main.py --folder ~/Pictures/MiCarpeta

# En pantalla completa
python app/main.py --demo --fullscreen
```

La primera vez con una carpeta nueva, Vitrina prepara las miniaturas en segundo plano; abajo a la derecha se ve el avance. Los videos se procesan después de las fotos (una versión ligera para reproducir y un clip corto de vista previa); mientras tanto se reproduce el original. Sin `mpv` instalado, los videos se muestran con su portada. Las siguientes veces abre de inmediato. La caché vive en `~/.cache/vitrina`.

## Controles

| Acción | Qué hace |
|---|---|
| Mover el mouse en la presentación | Pasa a la cuadrícula |
| Mover el mouse en la cuadrícula | Recorre la cuadrícula |
| Rueda o dos dedos | Zoom hacia la foto bajo el cursor. Más allá del zoom mínimo, con un gesto nuevo, pasa a meses y luego a años |
| Clic en un año o un mes | Entra a él |
| Selector de arriba (Años · Meses · Fotos · Colecciones) | Salta directo a ese nivel |
| Clic en una colección | Muestra solo sus fotos (la etiqueta de arriba la quita) |
| Ajustes · Presentación | Ken Burns, Un día como hoy, fecha y lugar, reloj, orden aleatorio, tiempo para volver |
| Ajustes · Pantalla | Apariencia (claro, oscuro, automático) y modo noche |
| `+` / `-` | Zoom hacia el centro |
| Clic en una foto | La abre en el visor |
| Mouse quieto 1.5 s sobre un video | Vista previa en miniatura, sin sonido |
| Abrir un video | Se reproduce desde el inicio, con el sonido entrando suave |
| `Espacio` o el botón de la barra | Pausa / reproduce el video (con fundido de sonido) |
| Clic en la barra de progreso | Salta a ese punto del video |
| En el visor: deslizar con dos dedos | Un gesto = una foto (anterior o siguiente); el video de destino se prepara durante la animación |
| En el visor: flechas ← → o los botones laterales | Foto anterior o siguiente (respeta el filtro de colección) |
| Clic en el visor o `Esc` | Regresa a la cuadrícula |
| `Esc` en meses, años o colecciones | Entra un nivel |
| `Esc` en la cuadrícula | Regresa a la presentación |
| Sin mover el mouse (15 s, configurable) | Regresa a la presentación |
| `i` | Muestra u oculta la fecha y el lugar |
| `n` | Simula la noche (se apaga en segundos) para probar el modo noche; otra vez la regresa |
| `f` | Pantalla completa |
| `q` | Salir |

Si el zoom con dos dedos va al revés de lo que esperas, agrega `--invert-zoom`.

## Pruebas

```bash
cd app
python -m pytest tests
```

Las pruebas cubren la lógica de la cámara (que se alcance cada orilla desde cualquier punto y que no haya saltos al entrar, salir o hacer zoom), que el Ken Burns nunca deje ver las orillas de la foto, las fechas de "Un día como hoy" y el horario nocturno.

## Estructura de la app

| Archivo | Qué contiene |
|---|---|
| `app/main.py` | Arranque y opciones de línea de comandos |
| `app/vitrina/config.py` | Medidas, tiempos y colores del diseño |
| `app/vitrina/camera.py` | Lógica de la cámara, sin dibujo: límites, recorrido con el mouse, zoom |
| `app/vitrina/library.py` | Escaneo de fotos, fechas y caché de miniaturas |
| `app/vitrina/gfx.py` | Ayudantes de dibujo sobre SDL2 |
| `app/vitrina/levels.py` | Grupos por mes, año y colección; su acomodo y sus mini presentaciones |
| `app/vitrina/settings.py` | Ajustes guardados en `~/.config/vitrina/settings.json` |
| `app/vitrina/video.py` | Reproducción de video con mpv, dibujada dentro de la interfaz |
| `app/vitrina/theme.py` | Temas claro, oscuro y automático |
| `app/vitrina/kenburns.py` | Movimiento lento de las fotos en la presentación |
| `app/vitrina/memories.py` | "Un día como hoy" |
| `app/vitrina/night.py` | Modo noche: horario, sensor de luz y brillo de la pantalla |
| `app/vitrina/nightclock.py` | Relojes grandes de la noche (ventana y clásico) |
| `app/vitrina/fonts/` | Tipografías libres de los relojes, con sus licencias |
| `app/vitrina/ui.py` | La interfaz: presentación, cuadrícula, niveles, visor y controles |

## Qué falta (siguientes versiones)

- Búsqueda
- La app web del celular
- La imagen de la USB y el instalador
