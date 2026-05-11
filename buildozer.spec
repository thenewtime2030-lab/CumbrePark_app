[app]
title = CumbrePark
package.name = cumbrepark
package.domain = org.cumbrepark

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = tests, bin, venv, .venv, __pycache__

version = 0.1.2.0

requirements = python3,kivy,requests,plyer,kivy_garden.mapview,certifi,charset-normalizer,idna,urllib3

presplash.filename = %(source.dir)s/assets/logo_cumbrepark.png
icon.filename = %(source.dir)s/assets/logo_cumbrepark.png

orientation = portrait
fullscreen = 0

# Permisos necesarios para mapa, APIs externas y GPS en Android.
android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION

android.accept_sdk_license = True

android.api = 35
android.minapi = 24
android.archs = arm64-v8a

# Color aproximado del logo.
android.presplash_color = #08334F

[buildozer]
log_level = 2
warn_on_root = 1
