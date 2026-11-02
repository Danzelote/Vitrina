# Datos de lugares

- **cities.tsv.gz**: ciudades y pueblos de más de 1000 habitantes (latitud, longitud, nombre,
  región, país), de [GeoNames](https://www.geonames.org) con licencia
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), tomados del paquete
  [reverse_geocoder](https://github.com/thampiman/reverse-geocoder). Sirve para mostrar el lugar
  de una foto sin internet.
- **countries.json**: nombres de los países en español e inglés, de
  [pycountry](https://github.com/pycountry/pycountry) (ISO 3166).

- `face_detection_yunet_2023mar.onnx`: detector de caras YuNet, de
  [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
  (licencia MIT). Solo encuentra dónde hay caras (para que el Ken Burns no las corte);
  no reconoce quién es.
