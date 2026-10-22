# La USB de Vitrina

La imagen de la USB arranca la Mac directo en Vitrina: sin escritorio, sin menú de arranque y con el WiFi de las MacBook ya incluido. Por ahora es para **probar sin instalar**: no toca el disco de la Mac, y las fotos que subas se borran al apagar.

## Lo que necesitas

- Una memoria USB de **4 GB o más**. Se borra por completo.
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

1. **WiFi:** en la pantalla de inicio, **Configurar WiFi**. Elige tu red y escribe la contraseña con el teclado de la Mac. Si la Mac está conectada por cable, no hace falta.
2. **Celular:** escanea el código QR que aparece y sube unas fotos.
3. **Apagar:** Ajustes → Pantalla → **Apagar**.

## Qué revisar en la Mac vieja

- [ ] Arranca sola desde la USB, sin pantalla negra.
- [ ] Se ve a la resolución correcta.
- [ ] El trackpad mueve la cuadrícula y el zoom con dos dedos funciona.
- [ ] El WiFi encuentra redes y se conecta.
- [ ] El celular sube fotos.
- [ ] Los videos se ven y se oyen, con fundido de entrada y de salida.
- [ ] Las animaciones se sienten fluidas (presentación, cuadrícula, visor, Ajustes).
- [ ] El modo noche baja el brillo de verdad.
- [ ] Apagar desde Ajustes funciona.

Anota lo que no funcione y en qué modelo (Acerca de esta Mac); se agrega a [compatibilidad](compatibilidad.md).

## Cómo se construye

La imagen la arma GitHub Actions ([`.github/workflows/imagen.yml`](../.github/workflows/imagen.yml)) con [`os/build.sh`](../os/build.sh) cada vez que se sube algo a la rama `imagen`. Es un Debian 13 mínimo:

- arranque EFI de 64 y 32 bits (las MacBook de 2006–2008 tienen EFI de 32 bits), sin menú;
- el driver `wl` del WiFi Broadcom ya compilado;
- X sin escritorio, con entrada automática del usuario `vitrina` y la app en pantalla completa (si se cierra, se vuelve a abrir);
- NetworkManager para el WiFi y hora automática por internet.

Antes de publicarla, la imagen se arranca en una máquina virtual para comprobar que Vitrina abre; la captura de pantalla y el registro quedan en cada versión de Releases.
