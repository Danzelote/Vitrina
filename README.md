# Vitrina

**Convierte una Mac vieja en un portarretratos digital para fotos y videos.**
*Turn an old Mac into a digital photo and video frame.*

> **Estado:** en desarrollo. Ya hay una primera versión que corre en tu computadora (ver [docs/desarrollo.md](docs/desarrollo.md)); todavía no hay imagen instalable.

---

## Qué es

Vitrina es un sistema que se instala en una Mac Intel vieja (2006–2015) y la convierte en un portarretratos: arranca directo a tus fotos y videos, sin escritorio ni nada más.

- **En reposo**, pasa tus fotos y videos a pantalla completa, con transiciones suaves.
- **Al mover el mouse**, la foto se encoge hasta su lugar en una cuadrícula que puedes explorar, acercar y alejar.
- **Al alejarte**, las fotos se agrupan por meses y por años, cada grupo con su propia mini presentación.
- **Las fotos llegan desde tu celular**: escaneas un código QR en la pantalla y subes fotos por tu red WiFi. Sin cuentas ni nube.
- **Funciona sin internet**: las fotos viven en la propia Mac.

La idea es que se sienta como algo que Apple pudo haber hecho: limpio, simple y con animaciones cuidadas.

## Cómo se instalará

1. Descargas la imagen desde *Releases*.
2. La grabas en una USB.
3. Enciendes la Mac con la tecla ⌥ Option y eliges la USB.
4. Eliges **Probar sin instalar** o **Instalar en esta Mac** (borra el disco).
5. Al terminar, quitas la USB, conectas el WiFi y escaneas el QR con tu celular.

## Macs compatibles

| Nivel | Macs |
|---|---|
| Soportadas | Intel Core 2 Duo (finales de 2006 a ~2015), 2 GB de RAM o más |
| Mínimo funcional | Core 2 Duo con 1 GB (calidad reducida) |
| Más adelante | Core Duo de 2006 (32 bits) |
| No soportadas | PowerPC |

Ver [docs/compatibilidad.md](docs/compatibilidad.md) para los modelos probados.

## Documentación

- [docs/proyecto.md](docs/proyecto.md) — el documento del proyecto: diseño, decisiones, arquitectura y fases.
- [docs/compatibilidad.md](docs/compatibilidad.md) — modelos probados y hallazgos.
- [docs/desarrollo.md](docs/desarrollo.md) — cómo correr la app mientras se desarrolla.

## Apoya el proyecto

Vitrina es gratis y de código abierto. Si te sirvió, o simplemente te gusta la idea de darle una segunda vida a las Macs viejas, puedes apoyar su desarrollo con una donación:

[![Apoyar en Ko-fi](https://img.shields.io/badge/Apoyar_en-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/danzelot)

También ayuda mucho probarlo en tu Mac y contar cómo te fue en [docs/compatibilidad.md](docs/compatibilidad.md).

## Licencia

[GPL-3.0](LICENSE). Puedes usar, modificar y compartir Vitrina; las versiones modificadas que distribuyas deben seguir siendo libres.
