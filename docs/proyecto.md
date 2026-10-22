# Vitrina — documento del proyecto

Este documento reúne lo que se ha decidido sobre Vitrina: cómo se ve y se comporta, en qué hardware corre, cómo está construida y en qué orden se va a hacer. Es la referencia para cualquiera que quiera entender o contribuir al proyecto.

---

## 1. Visión

Una Mac vieja tiene una pantalla buena, batería, teclado, trackpad y bocinas. Vitrina aprovecha todo eso para hacer un portarretratos que:

- Se instala con una USB, sin conocimientos técnicos.
- Arranca directo a las fotos, rápido, sin escritorio.
- Se siente como un producto de Apple: limpio, con bordes redondeados y transiciones cuidadas.
- Funciona sin internet y sin cuentas en la nube.
- Corre en hardware de 2006 a 2015 con requisitos mínimos.

---

## 2. La experiencia

### 2.1 Modo marco (reposo)

- La foto ocupa toda la pantalla. Cada pocos segundos se **funde** con la siguiente (no se desliza por la cuadrícula).
- **Fotos verticales:** van al centro, con la misma foto desenfocada y oscurecida de fondo, estilo Apple TV.
- **Videos:** se reproducen solos y sin sonido. Los verticales también llevan fondo desenfocado (un cuadro fijo del video, no el video en movimiento).
- **Ken Burns:** cada foto se acerca, se aleja o se desplaza muy despacio mientras está en pantalla. Apagado, solo zoom, o zoom y paneo. No se aplica a los videos.
- **Un día como hoy:** una de cada cuatro fotos es de estas fechas (±3 días) de años anteriores, con la etiqueta "Hace N años".
- **Descripción** (lugar y fecha) discreta abajo a la izquierda. Se puede ocultar.
- **Reloj** opcional abajo a la derecha, en 12 o 24 horas.
- La fecha y el reloj se mueven unos pocos píxeles cada 3 minutos, sin que se note, para no marcar las pantallas viejas.
- **Orden:** cronológico o aleatorio (sin repetir hasta que pasen todas).
- Al entrar por primera vez aparece un aviso breve: "Mueve el mouse para explorar".

### 2.2 Cuadrícula de fotos

- **Al mover el mouse**, la foto actual se encoge hasta su lugar en la cuadrícula y aparece el resto alrededor. El modo marco es, en realidad, la cuadrícula vista de muy cerca.
- **Miniaturas cuadradas**, recortadas desde el centro, sin importar si la foto es horizontal o vertical. Al abrir una, se despliega a su proporción real.
- **Recorrido con el mouse:** la posición del mouse en pantalla corresponde a una zona de la cuadrícula. Llevar el mouse a una orilla lleva la cuadrícula a su final en esa dirección. Al entrar, salir de una foto o hacer zoom, el recorrido parte de donde estabas, sin saltos.
- La cuadrícula llega a su límite cuando el mouse está a la mitad de la primera o última fila, para que esa fila se vea completa sin quedar tapada por la barra superior.
- **Zoom** con la rueda o dos dedos, **hacia la foto bajo el cursor**. Los botones − y + hacen zoom al centro. Más inercia con zoom alto, para que no se sienta brusco.
- La foto bajo el cursor se levanta un poco con sombra. (Se probó un efecto "ojo de pez" y se descartó: las fotos se amontonaban.)
- **La forma de la cuadrícula se adapta a la cantidad de fotos**, con proporción parecida a la de la pantalla (126 fotos → 14×9, 500 → 28×18, 1,000 → 40×25).
- Las fotos se ordenan **por fecha**, de la más reciente a la más antigua.

### 2.3 Niveles: fotos, meses y años

Al alejarte más allá del zoom mínimo, las fotos se agrupan (zoom semántico):

| Nivel | Qué se ve |
|---|---|
| **Fotos** | Las fotos individuales |
| **Meses** | Un calendario: cada año es un bloque con sus 12 meses en dos filas. Los meses sin fotos aparecen como cuadros vacíos tenues |
| **Años** | Un cuadro grande por año. Solo aparece si las fotos abarcan dos años o más |

- Cada cuadro de mes, año y colección tiene una **mini presentación**: va fundiendo entre varias de sus fotos, escalonado para que no cambien todos a la vez.
- **Clic o zoom in** sobre un año abre sus meses; sobre un mes, sus fotos.
- **Las animaciones siguen a la cámara:** hacia lo particular se siente que te adentras; hacia lo general, que retrocedes. Salen del punto donde está el cursor.
- Al entrar a un mes, se llega al **zoom más alejado** de las fotos, para explorar con libertad.
- **Protección contra la inercia del trackpad:** cada cambio de nivel requiere un gesto nuevo. Al llegar al zoom mínimo de las fotos, el mismo gesto se detiene ahí.
- Un selector arriba (Años · Meses · Fotos · Colecciones) permite saltar directo a cualquier nivel.

### 2.4 Colecciones

- Se crean desde el celular (por ejemplo "Viaje a Oaxaca", "Perro").
- Se ven como **carpetas**: un cuadro con un par de tarjetas asomándose detrás. Al abrir una, entras a sus fotos ya filtradas.
- También aparecen como sugerencias en la búsqueda.

### 2.5 Barra superior y búsqueda

- Una **franja oscura sólida**, delgada, con: Presentación, el selector de nivel, la búsqueda y el engrane de Ajustes.
- La búsqueda filtra en vivo por nombre, lugar, mes, año o "video", y atenúa lo que no coincide.
- **Al hacer clic en la búsqueda** se despliega un panel con las colecciones como sugerencias, con un pequeño efecto escalonado. La colección elegida queda como etiqueta dentro de la barra ("Viajes ✕").
- Abajo a la izquierda: contador de fotos y nivel actual. Abajo a la derecha: zoom − y +.

### 2.6 Visor

- Al hacer clic en una foto, crece flotando sobre un fondo oscuro, con **Volver** y **Presentación desde aquí**.
- **Pasar de foto:** deslizando con dos dedos (una foto por gesto), con las flechas del teclado o con botones redondos a los lados. Las fotos se desplazan como una tira, igual que en Fotos de Apple. Respeta el filtro de colección.
- **Videos:** al abrirlos se reproducen de inmediato desde el inicio, sin botón de play, con una barra de pausa, progreso y duración.
- **Sonido:** fade-in de ~0.5 s al abrir y fade-out al cerrar, pausar o volver a la presentación. Nunca corta de golpe.
- **Vista previa en la cuadrícula:** si dejas el mouse quieto ~1.5 s sobre un video, se reproduce en miniatura y sin sonido, con barrita de progreso.

### 2.7 Regreso automático

- Tras un tiempo sin mover el mouse (10 s a 1 min, configurable) vuelve al modo marco.
- Con una foto abierta en el visor espera más: 10 minutos.
- No regresa mientras se reproduce un video abierto ni mientras Ajustes está abierto.

### 2.8 Ajustes

Ajustes aparece creciendo un poco sobre el fondo desenfocado y se desvanece al cerrarse. En los selectores la pastilla se desliza de una opción a otra, los interruptores se deslizan y cambian de color suave, y al cambiar de tema claro a oscuro todos los colores pasan gradualmente.

Ajustes tiene dos pestañas: **Presentación** (Ken Burns, Un día como hoy, fecha y lugar, reloj, orden aleatorio, tiempo para volver) y **Pantalla** (apariencia y modo noche).

- **Apariencia:** claro, oscuro o automático (claro de día y oscuro de noche). La presentación siempre es negra; el tema cambia la cuadrícula, los niveles, el visor y los controles. Más adelante el automático podrá usar el sensor de luz.
- Fotos y videos (mostrar el QR para agregar desde el celular).
- Tiempo para volver a la presentación.
- Mostrar fecha y lugar.
- Orden aleatorio.
- **Modo noche:** nunca, por horario (22–7, 23–7 o 0–6) o según la luz del cuarto. Al llegar la noche la pantalla baja poco a poco durante 20 minutos y amanece igual de suave. Puede quedar **apagada** o con un reloj grande sobre negro, inspirado en el modo reposo del iPhone:
  - **Reloj ventana:** números redondos y gruesos; por dentro se ve la presentación desenfocada, tenue y con poco color, como si los números fueran una ventana, para que no distraiga. Entra y sale con un fundido.
  - **Reloj clásico:** números altos y angostos en blanco, azul o rojo (el rojo es el que menos molesta de noche), con el día a un lado.

  Las tipografías son libres (Fredoka y Bebas Neue, licencia OFL) y van incluidas. Mover el mouse la despierta; tras 2 minutos sin uso vuelve a apagarse en 1 minuto. Con la pantalla apagada la app casi no gasta. En la Mac con Vitrina instalado también baja el brillo real de la pantalla. "Según la luz" usa el sensor de luz si la Mac lo tiene (applesmc en las MacBook viejas), o más adelante la cámara si el usuario lo activa (apagado por defecto; se toma una imagen pequeña cada ~30 s, solo se mide el brillo y se descarta; el LED verde de la cámara parpadea en cada medición).
- **Acerca de Vitrina:** versión, enlace al repositorio y a [Ko-fi](https://ko-fi.com/danzelot) para apoyar el proyecto. Discreto, sin interrumpir nunca la presentación.

---

## 3. Las fotos: desde el celular

Las fotos **viven en la propia Mac**. No dependen de Google Drive ni de iCloud.

1. La Mac muestra un **código QR**.
2. Al escanearlo, el celular abre una **app web** servida por la propia Mac en la red local. No se instala nada de la App Store; se puede agregar a la pantalla de inicio.
3. Desde ahí se puede:
   - Subir fotos y videos desde la galería del celular, con barra de progreso.
   - Ver lo que hay en el portarretratos y borrar.
   - Crear colecciones y mover fotos entre ellas.
   - Cambiar los ajustes.
   - Ver el espacio disponible.
4. El QR lleva un **código de emparejamiento**, para que no cualquiera en la red pueda entrar. Varios familiares pueden emparejarse.

**Internet** solo se necesita para actualizaciones opcionales. Basta la red WiFi de la casa, aunque no tenga salida a internet.

### Metadatos

- **La fecha** suele llegar bien al subir directo desde la galería (mucho mejor que por WhatsApp). Si falta, se usa la fecha del archivo.
- **La ubicación** a menudo se pierde: los navegadores de los celulares la quitan por privacidad (por ejemplo [WebKit bug 207088](https://bugs.webkit.org/show_bug.cgi?id=207088)). Por eso las **colecciones hacen de "lugar"**. Subir desde una computadora conserva todos los datos. Una app nativa en el futuro podría pedir permiso para leer la ubicación.

### Videos del iPhone

Vienen en HEVC, a veces 4K. La Mac los convierte a un formato ligero; en un Core 2 Duo un video de un minuto puede tardar varios minutos. El celular muestra "Procesando…" mientras tanto.

### Más adelante

Google Drive, iCloud y otras fuentes, como opcionales.

---

## 4. Hardware soportado

| Nivel | Macs | Comentario |
|---|---|---|
| **Soportadas (v1)** | Intel Core 2 Duo, finales de 2006 a ~2015, 2 GB+ | La gran mayoría de Macs viejas |
| **Mínimo funcional** | Core 2 Duo con 1 GB | Transiciones más simples, video a 480p |
| **Después (v2)** | Core Duo de 2006 (solo 32 bits) | Linux está dejando de soportar 32 bits |
| **Fuera** | PowerPC (antes de 2006) | Otra arquitectura |

La app detecta el hardware al arrancar y elige sola la calidad.

---

## 5. Arquitectura

### Sistema

- **Debian mínimo**, sin escritorio. Arranca directo a la app; si la app falla, se reinicia sola.
- Configurado para **aguantar apagones** sin corromperse.
- **Hora automática** al conectarse a la red (muchas de estas Macs tienen agotada la pila del reloj interno).
- **Actualizaciones** opcionales desde GitHub Releases.

### Componentes

| Componente | Qué hace |
|---|---|
| **app** | La interfaz: modo marco, cuadrícula, niveles, visor. Nativa, dibujada con la gráfica (OpenGL). Nunca un navegador: con 2 GB de RAM no alcanza. Video con **mpv**. |
| **indexer** | Procesa lo que llega: miniaturas cuadradas, versión a tamaño de pantalla, fondo desenfocado de verticales (se genera una sola vez), conversión de video, índice con fecha, colección y lugar. |
| **setup-web** | La app web del celular: emparejamiento, subida, colecciones, ajustes. |
| **os** | Scripts que construyen la imagen de la USB y el instalador. |

### Rendimiento

- La cuadrícula carga **miniaturas pequeñas**; la foto grande se carga al final del zoom.
- Con muchas fotos, solo se dibujan los cuadros visibles, con miniaturas más chicas cuando estás lejos.
- El **vidrio esmerilado** de los botones se reemplaza por gris translúcido sólido en hardware viejo.
- Aceleración de video por hardware solo como bonus; todo debe funcionar bien sin ella.

### Instalación

1. Imagen descargable desde Releases, grabable con balenaEtcher o `dd`.
2. Arranque con ⌥ Option. La imagen incluye arranque EFI de 32 y 64 bits.
3. Opciones **Probar sin instalar** e **Instalar en esta Mac**. La instalación **borra todo el disco**, con advertencia clara y confirmación.
4. Primer arranque: elegir WiFi en la propia Mac, luego el QR para el celular.

### Estructura del repositorio

```
vitrina/
├── app/          ← la interfaz
├── indexer/      ← procesa fotos y videos
├── setup-web/    ← la app web del celular
├── os/           ← construye la imagen de la USB
├── docs/         ← documentación y compatibilidad
└── .github/      ← construye la imagen en cada versión
```

---

## 6. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Nombre | Vitrina |
| Licencia | GPL-3.0 |
| macOS al instalar | Se borra, con advertencia clara |
| Arquitectura v1 | Solo 64 bits |
| Fuente de fotos v1 | Subida desde el celular con QR |
| Almacenamiento | Local en la Mac |
| Agrupación | Por fecha (meses y años) y por colecciones |
| App | Nativa, no navegador |
| Tecnología de la app | Python + SDL2 (pygame-ce) + mpv. Ligera, fácil de leer y de iterar. La lógica va separada del dibujo para poder reescribir en Rust solo una pieza si hiciera falta |

---

## 7. Fases

| Fase | Qué | Estado |
|---|---|---|
| **0** | Probar Linux en vivo en hardware real | ✅ Hecha (ver [compatibilidad](compatibilidad.md)) |
| **1** | La app funcionando con una carpeta local, desarrollada en cualquier computadora | ✅ Casi lista (falta la búsqueda) |
| **2** | El indexer y la app web del celular | |
| **3** | La imagen de la USB y el instalador | |
| **4** | Primer arranque, actualizaciones, documentación y primera versión pública | |
| **5** | 32 bits, otras fuentes de fotos, app nativa del celular | |

---

## 8. Riesgos conocidos

- **WiFi Broadcom:** necesita drivers aparte. Irán preinstalados.
- **Levantar los dedos del trackpad:** SDL no avisa cuándo se levantan los dedos (ni en macOS ni en Linux), solo manda movimientos. En la imagen de Linux se leerá el trackpad directamente (`/dev/input`, que sí reporta cuántos dedos hay) para que el arrastre del visor se suelte justo al levantar los dedos. Mientras tanto se usa una pausa como señal.
- **Pantalla en negro al arrancar en Macs con NVIDIA:** el menú de arranque queda invisible. La imagen debe arrancar sola, sin menú.
- **Memoria:** con 2 GB todo debe ser ligero. Compilar o abrir un navegador basta para agotarla.
- **Teclado:** la distribución no siempre se detecta bien. Mejor que nadie tenga que escribir.
- **Conectar cuentas de nube** en un aparato sin navegador es difícil. Por eso la v1 no depende de ellas.
