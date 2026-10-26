# La USB de Vitrina

La imagen de la USB arranca la Mac directo en Vitrina: sin escritorio, sin menú de arranque y con el WiFi de las MacBook ya incluido. Sirve para **probar sin instalar** (no toca el disco de la Mac, y las fotos que subas se borran al apagar) y, cuando estés listo, para **instalar** Vitrina en la Mac.

## Lo que necesitas

- Una memoria USB de **1 GB o más** (la imagen pesa unos 450 MB). Se borra por completo.
- La imagen `vitrina-….iso`, de la sección [Releases](https://github.com/Danzelote/Vitrina/releases) del proyecto.
- [balenaEtcher](https://etcher.balena.io), para grabarla (Mac, Windows o Linux).

## Grabar la USB

1. Abre balenaEtcher.
2. **Flash from file** → elige `vitrina-….iso`.
3. **Select target** → elige la memoria USB. Revisa que sea la correcta: se borra.
4. **Flash!** Tarda unos minutos.

Si macOS dice al final que "el disco no se puede leer", es normal: elige **Expulsar**.

## Arrancar la Mac desde la USB

1. Con la Mac apagada, conecta la USB.
2. Enciéndela y deja presionada la tecla **⌥ Option** (alt) hasta que aparezcan los discos.
3. Elige el que dice **EFI Boot** (si hay dos, cualquiera).
4. En menos de un minuto aparece Vitrina, en pantalla completa.

No hace falta presionar nada más: la imagen arranca sola, sin el menú invisible que vimos en la prueba con Debian.

## Primeros pasos

1. **WiFi:** en la pantalla de inicio, **Configurar WiFi**. Con cámara, **Escanear código** y muestra el código QR del WiFi desde tu celular (iPhone: app Contraseñas → Wi-Fi → tu red → Mostrar código QR de la red; Android: Ajustes → Wi-Fi → Compartir). Si no, elige tu red y escribe la contraseña con el teclado de la Mac.
2. **Celular:** escanea el código QR que aparece y sube unas fotos.
3. **Apagar:** la tecla de encendido (o Ajustes → General → **Apagar…**) pregunta si quieres **Reposo**, **Apagar** o **Reiniciar**. Dejarla presionada unos segundos apaga de golpe.
4. **Cerrar la tapa** pone la Mac en reposo; al abrirla sigue donde se quedó.

## Instalar en la Mac

Cuando ya probaste que todo funciona desde la USB:

1. **Ajustes → General → Instalar en esta Mac…**
2. Revisa el disco que encontró y lee el aviso: **se borra macOS** con sus programas y archivos. Si quieres conservar algo de esa Mac, sácalo antes. La **recuperación de macOS** (⌘R al prender) se conserva, por si algún día quieres volver a instalarlo; en un disco sin ella se usa el disco completo.
3. **Continuar** → espera la cuenta atrás → **Borrar e instalar**. Tarda unos minutos; no apagues la Mac ni quites la USB.
4. Al terminar: quita la USB y **Reiniciar**. Vitrina arranca sola desde el disco.

Las fotos, el WiFi, los ajustes, los celulares conectados y el firmware de la cámara (que se toma del macOS antes de borrarlo) pasan a la instalación.

Detalles técnicos: el disco queda con una partición de arranque EFI (300 MB) y el sistema en ext4. Las Mac arrancan con `/EFI/BOOT` sin tocar su NVRAM. El instalador es [`os/rootfs/opt/vitrina/install.sh`](../os/rootfs/opt/vitrina/install.sh) y cada imagen se prueba instalándola en un disco virtual y arrancándolo con UEFI ([`os/install-test.sh`](../os/install-test.sh)).

## Actualizar

Ya instalada, Vitrina se actualiza desde internet sin borrar fotos ni ajustes: **Ajustes → General → Actualizaciones** (en la Mac; un punto naranja en el engrane avisa cuando hay una nueva) o **Ajustes → General** (en el celular). Baja de este repositorio el paquete `vitrina-app-<versión>.tar.gz` de la versión más nueva, revisa que llegó completo, cambia la app y se reinicia. Si la versión nueva no arranca, regresa sola a la anterior. Los cambios del sistema base (kernel, controladores) siguen necesitando reinstalar con la USB.

## Qué revisar en la Mac vieja

- [ ] Arranca sola desde la USB, sin pantalla negra.
- [ ] Se ve a la resolución correcta.
- [ ] El trackpad mueve la cuadrícula y el zoom con dos dedos funciona.
- [ ] El WiFi encuentra redes y se conecta.
- [ ] El celular sube fotos.
- [ ] Los videos se ven y se oyen, con fundido de entrada y de salida.
- [ ] Las animaciones se sienten fluidas (presentación, cuadrícula, visor, Ajustes).
- [ ] El brillo automático sube y baja con la luz del cuarto (Ajustes → Pantalla).
- [ ] Calibrar brillo mínimo: la pantalla nunca se va a negro con las teclas de brillo.
- [ ] El modo noche por horario muestra el reloj con el brillo bajo.
- [ ] La tecla de encendido muestra la ventana de apagar.
- [ ] Cerrar la tapa la pone en reposo y al abrirla vuelve (con WiFi).

Anota lo que no funcione y en qué modelo (Acerca de esta Mac); se agrega a [compatibilidad](compatibilidad.md).

## Cómo se construye

La imagen la arma GitHub Actions ([`.github/workflows/imagen.yml`](../.github/workflows/imagen.yml)) con [`os/build.sh`](../os/build.sh) cada vez que se sube algo a la rama `imagen`. Es un Debian 13 mínimo:

- arranque EFI de 64 y 32 bits (las MacBook de 2006–2008 tienen EFI de 32 bits), sin menú;
- el driver `wl` del WiFi Broadcom ya compilado;
- X sin escritorio, con entrada automática del usuario `vitrina` y la app en pantalla completa (si se cierra, se vuelve a abrir);
- NetworkManager para el WiFi y hora automática por internet.

Antes de publicarla, la imagen se arranca en una máquina virtual para comprobar que Vitrina abre; la captura de pantalla y el registro quedan en cada versión de Releases.
