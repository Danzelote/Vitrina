# Desarrollo

Cómo correr Vitrina en tu computadora mientras se desarrolla. Funciona en macOS y en Linux.

## Preparar (una sola vez)

En macOS, con [Homebrew](https://brew.sh):

```bash
brew install python git
git clone https://github.com/Danzelote/Vitrina.git ~/Vitrina
cd ~/Vitrina
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Correr

Desde la carpeta del proyecto, con el entorno activado (`source .venv/bin/activate`):

```bash
# Con fotos de prueba
python app/main.py --demo

# Con una carpeta tuya (cada subcarpeta es una colección)
python app/main.py --folder ~/Pictures/MiCarpeta

# En pantalla completa
python app/main.py --demo --fullscreen
```

La primera vez con una carpeta nueva, Vitrina prepara las miniaturas en segundo plano; arriba a la derecha se ve el avance. Las siguientes veces abre de inmediato. La caché vive en `~/.cache/vitrina`.

## Controles

| Acción | Qué hace |
|---|---|
| Mover el mouse en la presentación | Pasa a la cuadrícula |
| Mover el mouse en la cuadrícula | Recorre la cuadrícula |
| Rueda o dos dedos | Zoom hacia la foto bajo el cursor |
| `+` / `-` | Zoom hacia el centro |
| Clic en una foto | La abre en el visor |
| Clic en el visor o `Esc` | Regresa a la cuadrícula |
| `Esc` en la cuadrícula | Regresa a la presentación |
| 15 s sin mover el mouse | Regresa a la presentación |
| `i` | Muestra u oculta la fecha y el lugar |
| `f` | Pantalla completa |
| `q` | Salir |

Si el zoom con dos dedos va al revés de lo que esperas, agrega `--invert-zoom`.

## Pruebas

```bash
cd app
python -m pytest tests
```

Las pruebas cubren la lógica de la cámara: que se alcance cada orilla desde cualquier punto y que no haya saltos al entrar, salir o hacer zoom.

## Estructura de la app

| Archivo | Qué contiene |
|---|---|
| `app/main.py` | Arranque y opciones de línea de comandos |
| `app/vitrina/config.py` | Medidas, tiempos y colores del diseño |
| `app/vitrina/camera.py` | Lógica de la cámara, sin dibujo: límites, recorrido con el mouse, zoom |
| `app/vitrina/library.py` | Escaneo de fotos, fechas y caché de miniaturas |
| `app/vitrina/gfx.py` | Ayudantes de dibujo sobre SDL2 |
| `app/vitrina/ui.py` | La interfaz: presentación, cuadrícula y visor |

## Qué falta (siguientes versiones)

- Videos (con mpv)
- Niveles de meses y años, y colecciones como carpetas
- Barra superior con búsqueda y ajustes
- Orden aleatorio y horario nocturno
- La app web del celular
