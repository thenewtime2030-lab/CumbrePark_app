# CumbrePark - prototipo Android en Python/Kivy

Este proyecto es una base inicial para una app Android hecha en Python. Incluye:

- Pantalla de inicio fija con logo, título, botones y mapa.
- GPS con permiso de ubicación.
- Pantalla de mapa + clima.
- Consulta de clima mediante Open-Meteo, sin API key.
- Búsqueda de parques, senderos, reservas, miradores y atractivos cercanos mediante OpenStreetMap/Overpass.
- Rango de distancia ajustable con slider, parecido a la lógica de rango de Tinder.
- Botones para abrir coordenadas en Google Maps.

## Archivos importantes

- `main.py`: código principal de la app.
- `assets/logo_cumbrepark.png`: logo usado en inicio, splash e ícono.
- `buildozer.spec`: configuración para compilar Android.
- `requirements.txt`: dependencias para probar en computador.

## Probar en computador

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows PowerShell
pip install -r requirements.txt
python main.py
```

En computador normalmente no habrá GPS real, por eso la app usa una coordenada de prueba. En Android, al aceptar permisos, se actualiza con la ubicación real.

## Compilar para Android

Buildozer funciona mejor en Linux/macOS. En Windows se recomienda WSL2 o una máquina Linux.

```bash
pip install buildozer
buildozer android debug
```

El APK quedará en la carpeta `bin/`.

## Nota sobre Google Maps

El mapa embebido está hecho con OpenStreetMap porque es lo más práctico en Python/Kivy. Para un Google Maps nativo dentro de la app se necesitará una integración Android más avanzada y una API key de Google.
