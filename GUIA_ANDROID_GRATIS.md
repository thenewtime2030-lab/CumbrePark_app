# CumbrePark - Crear APK gratis sin instalar Buildozer en Windows

Este proyecto está preparado para crear un APK Android usando GitHub Actions.

No necesitas instalar Android Studio, WSL ni Buildozer en tu computador para esta primera prueba.

## Qué se necesita

- Una cuenta gratis de GitHub.
- Subir esta carpeta a un repositorio.
- Ejecutar el flujo "Build Android APK".
- Descargar el APK desde "Artifacts".

## Archivos importantes

- `main.py`: código principal de la app.
- `buildozer.spec`: configuración Android de la app.
- `assets/logo_cumbrepark.png`: logo de la app.
- `.github/workflows/build-android.yml`: automatización que crea el APK en GitHub.

## Resultado

Cuando GitHub termine, aparecerá un archivo descargable llamado `CumbrePark-APK`.
Dentro estará el `.apk` para instalar en Android.
