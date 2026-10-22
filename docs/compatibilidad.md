# Compatibilidad

Modelos probados y lo que se encontró en cada uno. Si pruebas Vitrina (o Linux en vivo) en tu Mac, agrega tu modelo con un *pull request* o abre un *issue*.

## Modelos probados

| Modelo | Procesador | RAM | Gráfica | WiFi | Arranque | Pantalla | Trackpad | Sonido | Video | Notas |
|---|---|---|---|---|---|---|---|---|---|---|
| MacBook 13" mediados de 2009 (A1181, blanca) | Core 2 Duo 2.13 GHz | 2 GB DDR2 | NVIDIA GeForce 9400M | Broadcom BCM4322 `[14e4:432b]` | ⚠️ EFI con menú invisible | ✅ | ✅ | ✅ | ✅ | Ver abajo |

## Hallazgos

### MacBook 13" mediados de 2009 (A1181)

Probado con Debian 13.7 *live* (Xfce, amd64) desde USB.

- **Arranque:** el Mac muestra dos entradas "EFI Boot"; ambas llevan al mismo sistema. Tras elegir una, la pantalla queda negra con un guion blanco fijo: el menú de arranque está ahí pero invisible. Presionar Enter arranca el sistema normalmente. **La imagen de Vitrina debe arrancar sola, sin esperar al menú.**
- **Arranque desde USB en modo compatible (BIOS):** no disponible. Estas Macs solo lo ofrecen desde CD/DVD.
- **WiFi:** la tarjeta se detecta, pero Debian no trae el driver. Necesita `broadcom-sta-dkms` (driver `wl`). Compilarlo en la sesión en vivo agotó la memoria, así que no se pudo confirmar la conexión. **Debe ir preinstalado en la imagen.**
- **Pantalla, trackpad (scroll con dos dedos), sonido y video en YouTube:** funcionan.
- **Memoria:** con 2 GB, Firefox más la instalación del driver congelaron el sistema. Confirma que la app debe ser nativa y ligera.
- **Reloj:** la fecha del sistema estaba meses atrás, lo que rompe las páginas seguras y las descargas de paquetes. **Vitrina debe poner la hora sola al conectarse.**
- **Teclado:** un teclado en español se detectó como inglés (EN). **Nadie debería tener que escribir comandos.**
