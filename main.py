# CumbrePark - prototipo inicial en Python/Kivy para Android
# -------------------------------------------------------------
# Objetivo de esta versión:
# - Pantalla de inicio fija con logo, título, botones y recuadro de mapa.
# - Uso de ubicación GPS si la persona acepta compartirla.
# - Pantalla de mapa + clima para tocar un punto del mapa y ver pronóstico.
# - Pantalla de parques/senderos/reservas cercanas ordenadas por distancia.
#
# IMPORTANTE:
# - El mapa embebido usa OpenStreetMap mediante kivy_garden.mapview, porque es
#   lo más directo para una app Android hecha en Python/Kivy.
# - Se incluye botón para abrir la misma coordenada en Google Maps.
# - Para integrar Google Maps nativo dentro de la app más adelante, lo ideal es
#   agregar Google Maps SDK con una parte nativa Android/Kotlin o una integración
#   específica con API key.

from __future__ import annotations

import math
import json
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import DictProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.utils import platform
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

try:
    from kivy_garden.mapview import MapMarker, MapSource, MapView

    MAPVIEW_AVAILABLE = True
except Exception:  # pragma: no cover - solo se usa si falta la dependencia
    MAPVIEW_AVAILABLE = False

    class MapView(BoxLayout):  # type: ignore
        lat = NumericProperty(0)
        lon = NumericProperty(0)
        zoom = NumericProperty(1)

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.orientation = "vertical"
            self.add_widget(
                Label(
                    text="Instala kivy_garden.mapview para ver el mapa.",
                    color=(0.05, 0.18, 0.28, 1),
                    halign="center",
                )
            )

        def add_marker(self, marker: Any) -> None:
            return None

        def remove_marker(self, marker: Any) -> None:
            return None

        def center_on(self, lat: float, lon: float) -> None:
            self.lat = lat
            self.lon = lon

    class MapMarker(Widget):  # type: ignore
        def __init__(self, lat: float = 0, lon: float = 0, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.lat = lat
            self.lon = lon

    MapSource = None  # type: ignore


# Paleta tomada del logo: azul profundo, azul petróleo, celeste/mint claro y blanco.
COLORS = {
    "navy": (0.03, 0.20, 0.31, 1),       # #08334F aprox.
    "blue": (17/255, 72/255, 113/255, 1),  # #114871 exacto
    "teal": (0.12, 0.47, 0.58, 1),       # #1F7894 aprox.
    "mint": (0.84, 0.97, 0.94, 1),       # #D6F7F0 aprox.
    "soft": (0.94, 0.98, 0.98, 1),       # fondo suave
    "white": (1, 1, 1, 1),
    "text": (0.04, 0.14, 0.20, 1),
    "muted": (0.28, 0.40, 0.46, 1),
    "danger": (0.70, 0.18, 0.12, 1),
}

# Coordenada inicial solo para probar en computador cuando no hay GPS.
# En Android, al aceptar permisos, se reemplaza por la ubicación real.
DEFAULT_LAT = -33.4489
DEFAULT_LON = -70.6693
DEFAULT_ZOOM = 11
OFFLINE_MIN_ZOOM = 10
OFFLINE_MAX_ZOOM = 14
OFFLINE_TILE_LIMIT = 650
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
HTTP_HEADERS = {"User-Agent": "CumbrePark/0.3 (Android outdoor app; contact: local prototype)"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return fallback


def web_tile_xy(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Return the standard Slippy Map tile containing a coordinate."""
    lat = clamp(float(lat), -85.05112878, 85.05112878)
    lon = clamp(float(lon), -180.0, 180.0)
    size = 1 << int(zoom)
    x = int((lon + 180.0) / 360.0 * size)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * size)
    return min(size - 1, max(0, x)), min(size - 1, max(0, y))


def offline_tiles(lat: float, lon: float, radius_km: float, min_zoom: int, max_zoom: int) -> list[tuple[int, int, int]]:
    """Calculate a bounded tile set for a circular area's enclosing box."""
    radius_km = clamp(float(radius_km), 1.0, 20.0)
    lat_delta = radius_km / 111.32
    lon_scale = max(0.15, math.cos(math.radians(float(lat))))
    lon_delta = radius_km / (111.32 * lon_scale)
    north = clamp(lat + lat_delta, -85.05112878, 85.05112878)
    south = clamp(lat - lat_delta, -85.05112878, 85.05112878)
    west = clamp(lon - lon_delta, -180.0, 180.0)
    east = clamp(lon + lon_delta, -180.0, 180.0)
    tiles: list[tuple[int, int, int]] = []
    for zoom in range(int(min_zoom), int(max_zoom) + 1):
        x_min, y_min = web_tile_xy(north, west, zoom)
        x_max, y_max = web_tile_xy(south, east, zoom)
        for x in range(min(x_min, x_max), max(x_min, x_max) + 1):
            for y in range(min(y_min, y_max), max(y_min, y_max) + 1):
                tiles.append((zoom, x, y))
    return tiles


def mapview_cache_name(zoom: int, x: int, web_y: int) -> str:
    """Translate standard web Y into garden.mapview's inverted cache Y."""
    internal_y = (1 << int(zoom)) - int(web_y) - 1
    return f"osm_{int(zoom)}_{int(x)}_{internal_y}.png"


def create_map_view(**kwargs: Any) -> MapView:
    """Create every map with the same persistent cache used by offline downloads."""
    app = App.get_running_app()
    cache_dir = str(getattr(app, "offline_cache_dir", Path("map_cache")))
    if MAPVIEW_AVAILABLE and MapSource is not None:
        source = MapSource(
            url=OSM_TILE_URL,
            cache_key="osm",
            min_zoom=0,
            max_zoom=19,
            attribution="© OpenStreetMap contributors",
            cache_dir=cache_dir,
        )
        kwargs.setdefault("map_source", source)
        kwargs.setdefault("cache_dir", cache_dir)
    return MapView(**kwargs)


@dataclass
class TrackPoint:
    lat: float
    lon: float
    altitude: Optional[float]
    accuracy: Optional[float]
    recorded_at: str


@dataclass
class ActivityRecord:
    started_at: str
    sport: str = "Trekking"
    ended_at: Optional[str] = None
    elapsed_seconds: float = 0.0
    distance_km: float = 0.0
    ascent_m: float = 0.0
    descent_m: float = 0.0
    points: list[TrackPoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "points": [asdict(point) for point in self.points],
        }


def _bind_label_auto_height(label: Label, min_height: float = 0.0) -> None:
    def _update_height(*_: Any) -> None:
        if not label.text_size:
            return
        texture_h = label.texture_size[1] if label.texture_size else 0
        label.height = max(min_height, texture_h + dp(6))

    label.bind(texture_size=_update_height, width=lambda *_: _update_height())
    Clock.schedule_once(lambda *_: _update_height(), 0)


@dataclass
class Place:
    name: str
    kind: str
    lat: float
    lon: float
    distance_km: float
    source: str = "OpenStreetMap"


def rgba_to_hex(color: tuple[float, float, float, float]) -> str:
    r, g, b, _ = color
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def weather_description(code: int) -> str:
    # Códigos WMO usados por Open-Meteo.
    descriptions = {
        0: "Cielo despejado",
        1: "Mayormente despejado",
        2: "Parcialmente nublado",
        3: "Nublado",
        45: "Niebla",
        48: "Niebla con escarcha",
        51: "Llovizna débil",
        53: "Llovizna moderada",
        55: "Llovizna intensa",
        61: "Lluvia débil",
        63: "Lluvia moderada",
        65: "Lluvia intensa",
        71: "Nieve débil",
        73: "Nieve moderada",
        75: "Nieve intensa",
        80: "Chubascos débiles",
        81: "Chubascos moderados",
        82: "Chubascos intensos",
        95: "Tormenta",
        96: "Tormenta con granizo débil",
        99: "Tormenta con granizo intenso",
    }
    return descriptions.get(code, "Condición no clasificada")


def detect_place_kind(tags: dict[str, Any]) -> str:
    if tags.get("route") == "hiking":
        return "Sendero / ruta de trekking"
    if tags.get("boundary") == "protected_area":
        return "Área protegida"
    if tags.get("leisure") == "nature_reserve":
        return "Reserva natural"
    if tags.get("leisure") == "park":
        return "Parque"
    if tags.get("tourism") == "viewpoint":
        return "Mirador"
    if tags.get("tourism") == "attraction":
        return "Atractivo natural/turístico"
    if tags.get("natural") == "peak":
        return "Cumbre / cerro"
    if tags.get("natural") == "wood":
        return "Bosque"
    return "Lugar outdoor"


class RoundedPanel(BoxLayout):
    bg_color = ListProperty(COLORS["white"])
    border_color = ListProperty((0.85, 0.92, 0.94, 1))
    radius = NumericProperty(dp(18))
    border_width = NumericProperty(dp(1))

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.padding = dp(14)
        self.spacing = dp(8)
        with self.canvas.before:
            self._bg_color_instruction = Color(*self.bg_color)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self._border_color_instruction = Color(*self.border_color)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self.radius), width=self.border_width)
        self.bind(pos=self._update_canvas, size=self._update_canvas, bg_color=self._update_canvas, border_color=self._update_canvas)

    def _update_canvas(self, *_: Any) -> None:
        self._bg_color_instruction.rgba = self.bg_color
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._bg.radius = [self.radius]
        self._border_color_instruction.rgba = self.border_color
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self.radius)
        self._border.width = self.border_width


class PrimaryButton(Button):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = COLORS["blue"]
        self.color = COLORS["white"]
        self.font_size = "16sp"
        self.bold = True
        self.size_hint_y = None
        self.height = dp(52)


class SecondaryButton(Button):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = COLORS["mint"]
        self.color = COLORS["navy"]
        self.font_size = "14sp"
        self.bold = True
        self.size_hint_y = None
        self.height = dp(44)


class SmallButton(Button):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = COLORS["teal"]
        self.color = COLORS["white"]
        self.font_size = "13sp"
        self.bold = True
        self.size_hint_y = None
        self.height = dp(38)


class TitleLabel(Label):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.color = COLORS["navy"]
        self.bold = True
        self.font_size = "24sp"
        self.halign = "left"
        self.valign = "middle"
        self.bind(size=self.setter("text_size"))
        self.text_size = (self.width, None)


class BodyLabel(Label):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.color = COLORS["text"]
        self.font_size = "14sp"
        self.halign = "left"
        self.valign = "middle"
        self.bind(size=self.setter("text_size"))
        self.text_size = (self.width, None)


class MutedLabel(Label):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.color = COLORS["muted"]
        self.font_size = "13sp"
        self.halign = "left"
        self.valign = "middle"
        self.bind(size=self.setter("text_size"))
        self.text_size = (self.width, None)


class Header(BoxLayout):
    def __init__(self, title: str, back: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.height = dp(96)
        self.padding = [dp(12), dp(8), dp(12), dp(10)]
        self.spacing = dp(4)

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        if back:
            back_btn = SecondaryButton(text="‹ Inicio")
            back_btn.width = dp(112)
            back_btn.size_hint_x = None
            back_btn.bind(on_release=lambda *_: App.get_running_app().go_home())
            top_row.add_widget(back_btn)
        logo = Image(
            source="assets/logo_cumbrepark.png",
            fit_mode="contain",
            size_hint=(None, None),
            width=dp(28),
            height=dp(28),
        )
        logo_wrap = AnchorLayout(anchor_x="left", anchor_y="center", size_hint_x=None, width=dp(36))
        logo_wrap.add_widget(logo)
        top_row.add_widget(logo_wrap)
        top_row.add_widget(Widget())
        self.add_widget(top_row)

        title_label = TitleLabel(text=title, font_size="22sp", size_hint_y=None, height=dp(34))
        title_label.halign = "center"
        title_label.valign = "middle"
        self.add_widget(title_label)


class LocationMap(BoxLayout):
    """Mapa reutilizable con un marcador principal."""

    marker = ObjectProperty(None, allownone=True)

    def __init__(self, selectable: bool = False, on_select: Optional[Callable[[float, float], None]] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.selectable = selectable
        self.on_select = on_select
        self.map = create_map_view(zoom=DEFAULT_ZOOM, lat=DEFAULT_LAT, lon=DEFAULT_LON)
        self.add_widget(self.map)
        if selectable and MAPVIEW_AVAILABLE:
            self.map.bind(on_touch_up=self._handle_map_touch)
        self.set_marker(DEFAULT_LAT, DEFAULT_LON, center=True)

    def set_marker(self, lat: float, lon: float, center: bool = True) -> None:
        try:
            if self.marker:
                self.map.remove_marker(self.marker)
        except Exception:
            pass
        self.marker = MapMarker(lat=lat, lon=lon)
        try:
            self.map.add_marker(self.marker)
        except Exception:
            pass
        if center:
            try:
                self.map.center_on(lat, lon)
            except Exception:
                self.map.lat = lat
                self.map.lon = lon

    def add_extra_marker(self, lat: float, lon: float) -> None:
        try:
            self.map.add_marker(MapMarker(lat=lat, lon=lon))
        except Exception:
            pass

    def _handle_map_touch(self, map_widget: Widget, touch: Any) -> bool:
        if not self.selectable or not self.collide_point(*touch.pos):
            return False
        if getattr(touch, "is_mouse_scrolling", False):
            return False
        if getattr(touch, "grab_current", None):
            return False

        # V.0.1.1:
        # Si la persona arrastra el mapa, no seleccionamos clima.
        # Solo seleccionamos clima cuando fue un toque corto.
        try:
            opos = getattr(touch, "opos", touch.pos)
            dx = float(touch.x - opos[0])
            dy = float(touch.y - opos[1])
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > dp(12):
                return False
        except Exception:
            pass

        try:
            try:
                lat, lon = map_widget.get_latlon_at(touch.x, touch.y, map_widget.zoom)
            except TypeError:
                lat, lon = map_widget.get_latlon_at(touch.x, touch.y)
            self.set_marker(lat, lon, center=False)
            if self.on_select:
                self.on_select(lat, lon)
        except Exception:
            return False
        return False


class CollapsibleCategory(RoundedPanel):
    def __init__(self, title: str, options: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(orientation="vertical", size_hint_y=None, bg_color=COLORS["soft"], **kwargs)
        self.options = options
        self.is_open = False
        self._base_height = dp(52) + self.padding[1] + self.padding[3]
        self._option_height = dp(48)
        self._option_spacing = dp(8)
        self.height = self._base_height

        self.toggle_btn = PrimaryButton(text=f"{title}  ▾", size_hint_y=None, height=dp(52))
        self.toggle_btn.bind(on_release=self.toggle)
        self.add_widget(self.toggle_btn)

        self.options_box = BoxLayout(orientation="vertical", spacing=self._option_spacing, size_hint_y=None, height=0, opacity=0)

        for text_btn, screen in self.options:
            btn = SecondaryButton(text=text_btn, height=dp(48))
            btn.bind(on_release=lambda *_ , s=screen: App.get_running_app().go_to(s))
            self.options_box.add_widget(btn)

        self.add_widget(self.options_box)

    def toggle(self, *_: Any) -> None:
        self.is_open = not self.is_open
        self.toggle_btn.text = self.toggle_btn.text[:-1] + ("▴" if self.is_open else "▾")
        if self.is_open:
            options_count = len(self.options)
            self.options_box.height = (options_count * self._option_height) + (max(0, options_count - 1) * self._option_spacing)
            self.options_box.opacity = 1
            self.height = self._base_height + self.options_box.height + self.spacing
        else:
            self.options_box.height = 0
            self.options_box.opacity = 0
            self.height = self._base_height


class PlaceholderScreen(Screen):
    def __init__(self, name: str, title: str, features: list[str], note: str = "Función en desarrollo", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = name

        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header(title))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(14), dp(20), dp(14), dp(20)],
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        hero = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["soft"])
        hero.padding = [dp(16), dp(16), dp(16), dp(16)]
        hero.spacing = dp(8)
        hero.bind(minimum_height=hero.setter("height"))
        hero.add_widget(TitleLabel(text=title, size_hint_y=None, height=dp(36), font_size="22sp"))
        hero.add_widget(BodyLabel(text=note, size_hint_y=None, height=dp(28)))
        hero.add_widget(MutedLabel(text="Próximamente tendrás esta función lista para uso real.", size_hint_y=None, height=dp(26)))
        content.add_widget(hero)

        future = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["white"])
        future.padding = [dp(16), dp(16), dp(16), dp(16)]
        future.spacing = dp(8)
        future.bind(minimum_height=future.setter("height"))
        future.add_widget(BodyLabel(text="Funciones futuras", size_hint_y=None, height=dp(30)))
        for item in features:
            feature_line = MutedLabel(text=f"• {item}", size_hint_y=None, height=dp(24))
            _bind_label_auto_height(feature_line, dp(24))
            future.add_widget(feature_line)
        content.add_widget(future)

        back_btn = PrimaryButton(text="Volver al inicio", size_hint_y=None, height=dp(52))
        back_btn.bind(on_release=lambda *_: App.get_running_app().go_home())
        content.add_widget(back_btn)


class EmergencyScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "emergency"

        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header("Emergencia"))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(14), dp(20), dp(14), dp(20)],
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        warning = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["soft"])
        warning.padding = [dp(16), dp(16), dp(16), dp(16)]
        warning.bind(minimum_height=warning.setter("height"))
        warning.add_widget(TitleLabel(text="Números de emergencia", size_hint_y=None, height=dp(34), font_size="21sp"))
        warning.add_widget(MutedLabel(text="En una emergencia real, llama directamente al número correspondiente.", size_hint_y=None, height=dp(46)))
        content.add_widget(warning)

        contacts = [
            ("CONAF / incendios forestales", "130"),
            ("SAMU / Ambulancia", "131"),
            ("Bomberos", "132"),
            ("Carabineros", "133"),
            ("PDI", "134"),
            ("Socorro Andino / rescate montaña", "136"),
            ("Emergencia marítima", "137"),
            ("Rescate aéreo", "138"),
        ]
        grid = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        for label, number in contacts:
            card = RoundedPanel(orientation="horizontal", size_hint_y=None, height=dp(58), bg_color=COLORS["white"])
            card.padding = [dp(14), dp(12), dp(14), dp(12)]
            card.add_widget(BodyLabel(text=label))
            call_button = SmallButton(text=number, size_hint_x=None, width=dp(84), height=dp(38))
            call_button.bind(on_release=lambda _button, phone=number: self.call_number(phone))
            card.add_widget(call_button)
            grid.add_widget(card)
        content.add_widget(grid)

        tools = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["white"])
        tools.bind(minimum_height=tools.setter("height"))
        tools.add_widget(BodyLabel(text="Tu ubicación de emergencia", size_hint_y=None, height=dp(30)))
        self.location_label = MutedLabel(text="Obteniendo coordenadas...", size_hint_y=None, height=dp(44))
        tools.add_widget(self.location_label)
        copy_button = SecondaryButton(text="Copiar coordenadas actuales")
        copy_button.bind(on_release=lambda *_: self.copy_coordinates())
        maps_button = SecondaryButton(text="Abrir ubicación en Google Maps")
        maps_button.bind(on_release=lambda *_: App.get_running_app().open_google_maps())
        tools.add_widget(copy_button)
        tools.add_widget(maps_button)
        content.add_widget(tools)

        back_btn = PrimaryButton(text="Volver al inicio")
        back_btn.bind(on_release=lambda *_: App.get_running_app().go_home())
        content.add_widget(back_btn)

    def on_pre_enter(self, *_: Any) -> None:
        app = App.get_running_app()
        self.on_location_update(app.current_lat, app.current_lon)
        app.request_gps()

    def on_location_update(self, lat: float, lon: float) -> None:
        app = App.get_running_app()
        precision = f" · precisión {app.last_gps_accuracy:.0f} m" if app.last_gps_accuracy is not None else ""
        self.location_label.text = f"{lat:.6f}, {lon:.6f}{precision}"

    def copy_coordinates(self) -> None:
        app = App.get_running_app()
        Clipboard.copy(f"{app.current_lat:.6f}, {app.current_lon:.6f}")
        self.location_label.text = "Coordenadas copiadas. Compártelas con tu contacto de emergencia."

    def call_number(self, number: str) -> None:
        webbrowser.open(f"tel:{number}")


class DownloadMapScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "download_map"
        self.download_cancelled = False
        self.selected_lat = DEFAULT_LAT
        self.selected_lon = DEFAULT_LON

        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header("Mapa sin internet"))

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(14), dp(14), dp(14), dp(24)],
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        panel = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(650), bg_color=COLORS["soft"])
        panel.add_widget(TitleLabel(text="Descargar zona", size_hint_y=None, height=dp(36), font_size="21sp"))
        panel.add_widget(MutedLabel(
            text="Elige el centro en el mapa, usa tu GPS o escribe coordenadas. La zona quedará disponible en este dispositivo.",
            size_hint_y=None,
            height=dp(54),
        ))

        self.preview_map = LocationMap(
            selectable=True,
            on_select=self.select_center,
            size_hint_y=None,
            height=dp(230),
        )
        panel.add_widget(self.preview_map)

        location_actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(44))
        gps_button = SecondaryButton(text="Usar mi GPS")
        gps_button.bind(on_release=lambda *_: self.use_gps())
        center_button = SecondaryButton(text="Usar centro del mapa")
        center_button.bind(on_release=lambda *_: self.use_map_center())
        location_actions.add_widget(gps_button)
        location_actions.add_widget(center_button)
        panel.add_widget(location_actions)

        coordinates = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(46))
        self.lat_input = TextInput(
            text=f"{DEFAULT_LAT:.6f}", multiline=False, input_filter="float",
            background_normal="", background_active="", background_color=COLORS["white"],
            foreground_color=COLORS["text"], padding=[dp(8), dp(12), dp(8), 0],
        )
        self.lon_input = TextInput(
            text=f"{DEFAULT_LON:.6f}", multiline=False, input_filter="float",
            background_normal="", background_active="", background_color=COLORS["white"],
            foreground_color=COLORS["text"], padding=[dp(8), dp(12), dp(8), 0],
        )
        apply_button = SmallButton(text="Aplicar")
        apply_button.bind(on_release=lambda *_: self.apply_coordinates())
        coordinates.add_widget(self.lat_input)
        coordinates.add_widget(self.lon_input)
        coordinates.add_widget(apply_button)
        panel.add_widget(coordinates)

        self.radius_label = BodyLabel(text="Radio: 5 km", size_hint_y=None, height=dp(28))
        panel.add_widget(self.radius_label)
        self.radius_slider = Slider(min=1, max=10, value=5, step=1, size_hint_y=None, height=dp(38))
        self.radius_slider.bind(value=lambda _slider, value: self.update_estimate(radius=value))
        panel.add_widget(self.radius_slider)

        self.zoom_label = BodyLabel(text="Detalle máximo: nivel 14", size_hint_y=None, height=dp(28))
        panel.add_widget(self.zoom_label)
        self.zoom_slider = Slider(min=12, max=14, value=14, step=1, size_hint_y=None, height=dp(38))
        self.zoom_slider.bind(value=lambda _slider, value: self.update_estimate(max_zoom=value))
        panel.add_widget(self.zoom_slider)

        self.estimate_label = MutedLabel(text="", size_hint_y=None, height=dp(32))
        panel.add_widget(self.estimate_label)

        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(52))
        download_button = PrimaryButton(text="Descargar mapa")
        download_button.bind(on_release=lambda *_: self.start_download())
        cancel_button = SecondaryButton(text="Cancelar")
        cancel_button.bind(on_release=lambda *_: self.cancel_download())
        actions.add_widget(download_button)
        actions.add_widget(cancel_button)
        panel.add_widget(actions)
        content.add_widget(panel)

        info = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(142), bg_color=COLORS["white"])
        info.add_widget(BodyLabel(text="Estado", size_hint_y=None, height=dp(28)))
        self.status_label = MutedLabel(
            text="Aún no hay una descarga en curso.",
            size_hint_y=None,
            height=dp(76),
        )
        info.add_widget(self.status_label)
        content.add_widget(info)

        back_btn = PrimaryButton(text="Volver al inicio")
        back_btn.bind(on_release=lambda *_: App.get_running_app().go_home())
        content.add_widget(back_btn)

        Clock.schedule_once(lambda *_: self.update_estimate(), 0)

    def on_pre_enter(self, *_: Any) -> None:
        app = App.get_running_app()
        if app.has_real_gps_fix:
            self.select_center(app.current_lat, app.current_lon)
        self.update_storage_status()

    def select_center(self, lat: float, lon: float) -> None:
        if not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
            self.set_status("Las coordenadas ingresadas no son válidas.")
            return
        self.selected_lat, self.selected_lon = float(lat), float(lon)
        self.lat_input.text = f"{self.selected_lat:.6f}"
        self.lon_input.text = f"{self.selected_lon:.6f}"
        self.preview_map.set_marker(self.selected_lat, self.selected_lon, center=True)
        self.update_estimate()

    def use_gps(self) -> None:
        app = App.get_running_app()
        app.request_gps()
        self.select_center(app.current_lat, app.current_lon)
        self.set_status("Usando la última ubicación válida. El centro se actualizará al recibir un GPS más preciso.")

    def on_location_update(self, lat: float, lon: float) -> None:
        self.select_center(lat, lon)
        self.set_status("Ubicación GPS actualizada. Ya puedes descargar la zona.")

    def use_map_center(self) -> None:
        coordinate = self.preview_map.map.get_latlon_at(*self.preview_map.map.center)
        lat = coordinate.lat if hasattr(coordinate, "lat") else coordinate[0]
        lon = coordinate.lon if hasattr(coordinate, "lon") else coordinate[1]
        self.select_center(float(lat), float(lon))

    def apply_coordinates(self) -> None:
        try:
            self.select_center(float(self.lat_input.text), float(self.lon_input.text))
        except ValueError:
            self.set_status("Escribe latitud y longitud usando números válidos.")

    def selected_tiles(self) -> list[tuple[int, int, int]]:
        return offline_tiles(
            self.selected_lat,
            self.selected_lon,
            float(self.radius_slider.value),
            OFFLINE_MIN_ZOOM,
            int(self.zoom_slider.value),
        )

    def update_estimate(self, radius: Optional[float] = None, max_zoom: Optional[float] = None) -> None:
        if radius is not None:
            self.radius_label.text = f"Radio: {int(radius)} km"
        if max_zoom is not None:
            self.zoom_label.text = f"Detalle máximo: nivel {int(max_zoom)}"
        total = len(self.selected_tiles())
        estimated_mb = total * 0.035
        self.estimate_label.text = f"Descarga estimada: {total} archivos, aproximadamente {estimated_mb:.1f} MB"

    def set_status(self, message: str) -> None:
        self.status_label.text = message

    def start_download(self) -> None:
        tiles = self.selected_tiles()
        if len(tiles) > OFFLINE_TILE_LIMIT:
            self.set_status(
                f"La zona requiere {len(tiles)} archivos. Reduce radio o detalle; el máximo seguro es {OFFLINE_TILE_LIMIT}."
            )
            return
        self.download_cancelled = False
        self.set_status(f"Preparando {len(tiles)} archivos de mapa...")
        threading.Thread(target=self._download_worker, args=(tiles,), daemon=True).start()

    def cancel_download(self) -> None:
        self.download_cancelled = True
        self.set_status("Cancelando descarga...")

    def _download_worker(self, tiles: list[tuple[int, int, int]]) -> None:
        app = App.get_running_app()
        cache_dir = app.offline_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        session = requests.Session()
        downloaded = 0
        reused = 0
        failed = 0
        total = len(tiles)
        for index, (zoom, x, web_y) in enumerate(tiles, start=1):
            if self.download_cancelled:
                break
            destination = cache_dir / mapview_cache_name(zoom, x, web_y)
            if destination.exists() and destination.stat().st_size > 100:
                reused += 1
            else:
                temporary = destination.with_suffix(".part")
                try:
                    response = session.get(
                        OSM_TILE_URL.format(z=zoom, x=x, y=web_y),
                        headers=HTTP_HEADERS,
                        timeout=15,
                    )
                    response.raise_for_status()
                    data = response.content
                    if not data.startswith(b"\x89PNG"):
                        raise ValueError("respuesta de mapa inválida")
                    temporary.write_bytes(data)
                    temporary.replace(destination)
                    downloaded += 1
                except (OSError, requests.RequestException, ValueError):
                    failed += 1
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
            if index == total or index % 5 == 0:
                Clock.schedule_once(
                    lambda _dt, done=index, count=total: self.set_status(
                        f"Descargando mapa: {done}/{count} archivos procesados."
                    ),
                    0,
                )
            time.sleep(0.04)

        result = {
            "center": [self.selected_lat, self.selected_lon],
            "radius_km": int(self.radius_slider.value),
            "min_zoom": OFFLINE_MIN_ZOOM,
            "max_zoom": int(self.zoom_slider.value),
            "tiles": total,
            "downloaded": downloaded,
            "reused": reused,
            "failed": failed,
            "completed_at": utc_now_iso(),
        }
        atomic_write_json(app.data_dir / "offline_map.json", result)
        if self.download_cancelled:
            message = f"Descarga cancelada. Se conservaron {downloaded + reused} archivos útiles."
        elif failed:
            message = f"Mapa guardado parcialmente: {downloaded} nuevos, {reused} existentes y {failed} fallidos."
        else:
            message = f"Mapa listo para uso sin internet: {downloaded} nuevos y {reused} ya guardados."
        Clock.schedule_once(lambda _dt: self.set_status(message), 0)

    def update_storage_status(self) -> None:
        app = App.get_running_app()
        files = list(app.offline_cache_dir.glob("osm_*.png"))
        size_mb = sum(path.stat().st_size for path in files if path.is_file()) / (1024 * 1024)
        if files:
            self.set_status(f"Mapa offline disponible: {len(files)} archivos, {size_mb:.1f} MB en este dispositivo.")


class HomeActionButton(Button):
    def __init__(self, accent: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (23/255, 106/255, 154/255, 1) if accent else (16/255, 26/255, 36/255, 1)
        self.color = COLORS["white"]
        self.bold = True
        self.font_size = "16sp"
        self.halign = "center"
        self.valign = "middle"
        self.text_size = (0, 0)
        self.bind(size=lambda instance, _size: setattr(instance, "text_size", (instance.width - dp(12), instance.height - dp(8))))


class HomeScreen(Screen):
    """Functional, fixed Home without a ScrollView or self-sizing cards."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "home"
        dark = (7/255, 16/255, 24/255, 1)
        accent = (183/255, 255/255, 74/255, 1)
        muted = (170/255, 183/255, 194/255, 1)

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(14), dp(14), dp(16)],
            spacing=dp(10),
        )
        with root.canvas.before:
            Color(*dark)
            background = RoundedRectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *_: setattr(background, "pos", root.pos))
        root.bind(size=lambda *_: setattr(background, "size", root.size))
        self.add_widget(root)

        hero = RoundedPanel(
            orientation="horizontal",
            size_hint_y=0.22,
            bg_color=COLORS["blue"],
            border_color=COLORS["teal"],
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(12),
        )
        logo = Image(
            source="assets/logo_cumbrepark.png",
            fit_mode="contain",
            size_hint_x=0.28,
        )
        hero.add_widget(logo)
        hero_text = BoxLayout(orientation="vertical", spacing=0)
        title = Label(text="CumbrePark", color=COLORS["white"], bold=True, font_size="27sp", halign="left", valign="middle")
        subtitle = Label(text="Explora. Registra. Vuelve seguro.", color=muted, font_size="13sp", halign="left", valign="middle")
        for label in (title, subtitle):
            label.bind(size=lambda instance, _size: setattr(instance, "text_size", instance.size))
            hero_text.add_widget(label)
        hero.add_widget(hero_text)
        root.add_widget(hero)

        self.status_label = Label(
            text="Preparando ubicación...",
            color=accent,
            font_size="12sp",
            halign="center",
            valign="middle",
            size_hint_y=0.08,
        )
        self.status_label.bind(size=lambda instance, _size: setattr(instance, "text_size", instance.size))
        root.add_widget(self.status_label)

        action_grid = GridLayout(cols=2, rows=3, spacing=dp(10), size_hint_y=0.70)
        actions = [
            ("Mapa + clima\nPronóstico del punto", "weather", True),
            ("Lugares cercanos\nSenderos y parques", "nearby", True),
            ("Registrar actividad\nGPS, tiempo y distancia", "register_activity", False),
            ("Mapa sin internet\nDescargar una zona", "download_map", False),
            ("Emergencia\nCoordenadas y ayuda", "emergency", False),
            ("Mis actividades\nHistorial local", "sports_history", False),
        ]
        for text, screen_name, highlighted in actions:
            button = HomeActionButton(text=text, accent=highlighted)
            button.bind(on_release=lambda _button, target=screen_name: App.get_running_app().go_to(target))
            action_grid.add_widget(button)
        root.add_widget(action_grid)

    def set_status(self, message: str) -> None:
        self.status_label.text = message



class WeatherScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "weather"
        self.selected_lat = DEFAULT_LAT
        self.selected_lon = DEFAULT_LON

        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)

        root.add_widget(Header("Mapa + clima"))

        intro = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(120), bg_color=COLORS["soft"])
        intro.add_widget(BodyLabel(text="Toca un punto del mapa para consultar clima local.", size_hint_y=None, height=dp(30)))
        intro.add_widget(MutedLabel(text="El panel resume temperatura, lluvia y viento. Es una base para evolucionar hacia capas tipo Windy.", size_hint_y=None, height=dp(52)))
        root.add_widget(intro)

        self.map_widget = LocationMap(selectable=True, on_select=self.select_point_from_map, size_hint_y=0.44)
        root.add_widget(self.map_widget)

        action_row = GridLayout(cols=3, spacing=dp(8), padding=[dp(12), dp(6), dp(12), dp(6)], size_hint_y=None, height=dp(56))
        current_btn = SmallButton(text="Mi ubicación")
        current_btn.bind(on_release=lambda *_: self.use_current_location())
        weather_btn = SmallButton(text="Actualizar clima")
        weather_btn.bind(on_release=lambda *_: self.fetch_weather(self.selected_lat, self.selected_lon))
        google_btn = SmallButton(text="Google Maps")
        google_btn.bind(on_release=lambda *_: App.get_running_app().open_google_maps(self.selected_lat, self.selected_lon))
        action_row.add_widget(current_btn)
        action_row.add_widget(weather_btn)
        action_row.add_widget(google_btn)
        root.add_widget(action_row)

        self.weather_scroll = ScrollView(size_hint_y=0.42)
        self.weather_content = BoxLayout(orientation="vertical", spacing=dp(14), padding=dp(12), size_hint_y=None)
        self.weather_content.bind(minimum_height=self.weather_content.setter("height"))
        self.weather_scroll.add_widget(self.weather_content)
        root.add_widget(self.weather_scroll)

        Clock.schedule_once(lambda *_: self.fetch_weather(self.selected_lat, self.selected_lon), 0.4)

    def on_location_update(self, lat: float, lon: float) -> None:
        # No cambia el punto elegido si la persona ya tocó otro punto, pero sí deja disponible "Mi ubicación".
        pass

    def use_current_location(self) -> None:
        app = App.get_running_app()
        self.select_point(app.current_lat, app.current_lon, center=True)
        app.request_gps()

    def select_point_from_map(self, lat: float, lon: float) -> None:
        # V.0.1.1:
        # Cuando se toca el mapa para consultar clima, no lo recentramos.
        # Así la persona puede explorar sin que el mapa salte.
        self.select_point(lat, lon, center=False)

    def select_point(self, lat: float, lon: float, center: bool = True) -> None:
        self.selected_lat = float(lat)
        self.selected_lon = float(lon)
        self.map_widget.set_marker(self.selected_lat, self.selected_lon, center=center)
        self.fetch_weather(self.selected_lat, self.selected_lon)

    def fetch_weather(self, lat: float, lon: float) -> None:
        self.set_weather_message("Cargando clima...")

        def worker() -> None:
            try:
                url = "https://api.open-meteo.com/v1/forecast"
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code",
                    "hourly": "temperature_2m,precipitation_probability,wind_speed_10m",
                    "forecast_days": 1,
                    "timezone": "auto",
                }
                response = requests.get(url, params=params, timeout=12)
                response.raise_for_status()
                data = response.json()
                Clock.schedule_once(lambda *_: self.render_weather(data, lat, lon), 0)
            except Exception as exc:
                Clock.schedule_once(lambda *_: self.set_weather_message(f"No se pudo obtener el clima: {exc}"), 0)

        threading.Thread(target=worker, daemon=True).start()

    def set_weather_message(self, message: str) -> None:
        self.weather_content.clear_widgets()
        panel = RoundedPanel(orientation="vertical", bg_color=COLORS["white"], size_hint_y=None, height=dp(100))
        panel.add_widget(BodyLabel(text=message))
        self.weather_content.add_widget(panel)

    def render_weather(self, data: dict[str, Any], lat: float, lon: float) -> None:
        self.weather_content.clear_widgets()
        current = data.get("current", {})
        units = data.get("current_units", {})
        temp = current.get("temperature_2m", "-")
        hum = current.get("relative_humidity_2m", "-")
        rain = current.get("precipitation", "-")
        wind = current.get("wind_speed_10m", "-")
        wdir = current.get("wind_direction_10m", "-")
        code = int(current.get("weather_code", -1)) if str(current.get("weather_code", "")).lstrip("-").isdigit() else -1

        summary = RoundedPanel(orientation="vertical", bg_color=COLORS["mint"], size_hint_y=None)
        summary.spacing = dp(6)
        summary.bind(minimum_height=summary.setter("height"))
        summary.add_widget(TitleLabel(text="Clima del punto seleccionado", size_hint_y=None, height=dp(34)))
        summary.add_widget(BodyLabel(text=f"Coordenadas: {lat:.5f}, {lon:.5f}", size_hint_y=None, height=dp(26)))
        summary.add_widget(BodyLabel(text=f"Estado: {weather_description(code)}", size_hint_y=None, height=dp(26)))
        summary.add_widget(BodyLabel(text=f"Temperatura: {temp} {units.get('temperature_2m', '°C')}", size_hint_y=None, height=dp(26)))
        summary.add_widget(BodyLabel(text=f"Humedad: {hum}%", size_hint_y=None, height=dp(26)))
        summary.add_widget(BodyLabel(text=f"Lluvia actual: {rain} {units.get('precipitation', 'mm')}", size_hint_y=None, height=dp(26)))
        summary.add_widget(BodyLabel(text=f"Viento: {wind} {units.get('wind_speed_10m', 'km/h')}  ·  Dirección: {wdir}°", size_hint_y=None, height=dp(30)))
        self.weather_content.add_widget(summary)

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])[:8]
        temps = hourly.get("temperature_2m", [])[:8]
        probs = hourly.get("precipitation_probability", [])[:8]
        winds = hourly.get("wind_speed_10m", [])[:8]

        forecast_panel = RoundedPanel(orientation="vertical", bg_color=COLORS["white"], size_hint_y=None)
        forecast_panel.padding = [dp(14), dp(16), dp(14), dp(14)]
        forecast_panel.spacing = dp(10)
        forecast_panel.bind(minimum_height=forecast_panel.setter("height"))

        forecast_panel.add_widget(TitleLabel(text="Ver más información", size_hint_y=None, height=dp(34)))
        forecast_panel.add_widget(BodyLabel(text="Próximas horas", size_hint_y=None, height=dp(28)))

        for idx, hour in enumerate(times):
            line = (
                f"{hour[-5:]}  ·  {temps[idx] if idx < len(temps) else '-'}°C\n"
                f"Lluvia: {probs[idx] if idx < len(probs) else '-'}%  ·  Viento: {winds[idx] if idx < len(winds) else '-'} km/h"
            )
            hour_label = MutedLabel(text=line, size_hint_y=None, height=dp(44))
            hour_label.line_height = 1.15
            forecast_panel.add_widget(hour_label)

        if not times:
            forecast_panel.add_widget(MutedLabel(text="Sin horas disponibles en este momento.", size_hint_y=None, height=dp(28)))

        self.weather_content.add_widget(forecast_panel)


class OriginModeButton(ToggleButton):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.size_hint_y = None
        self.height = dp(42)
        self.font_size = "13sp"
        self.bold = True
        self.update_style()
        self.bind(state=lambda *_: self.update_style())

    def update_style(self, *_: Any) -> None:
        if self.state == "down":
            self.background_color = COLORS["blue"]
            self.color = COLORS["white"]
        else:
            self.background_color = COLORS["mint"]
            self.color = COLORS["navy"]


class NearbyScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "nearby"
        self.radius_km = 10
        self.selected_origin_lat: Optional[float] = None
        self.selected_origin_lon: Optional[float] = None
        self.selected_origin_source = "gps"

        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header("Lugares cercanos"))

        body_scroll = ScrollView()
        body = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        body_scroll.add_widget(body)
        root.add_widget(body_scroll)

        controls = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["soft"])
        controls.bind(minimum_height=controls.setter("height"))
        controls.add_widget(BodyLabel(text="Selecciona un origen para buscar parques, senderos y reservas cercanas.", size_hint_y=None, height=dp(34)))

        self.origin_status = MutedLabel(text="Origen actual: GPS", size_hint_y=None, height=dp(28))
        controls.add_widget(self.origin_status)

        mode_row = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(44))
        self.mode_gps = OriginModeButton(text="Usar mi GPS", group="origin_mode", state="down")
        self.mode_manual = OriginModeButton(text="Elegir punto manualmente", group="origin_mode")
        self.mode_address = OriginModeButton(text="Buscar dirección", group="origin_mode")
        self.mode_gps.bind(on_release=lambda *_: self.set_origin_mode("gps"))
        self.mode_manual.bind(on_release=lambda *_: self.set_origin_mode("manual"))
        self.mode_address.bind(on_release=lambda *_: self.set_origin_mode("address"))
        mode_row.add_widget(self.mode_gps)
        mode_row.add_widget(self.mode_manual)
        mode_row.add_widget(self.mode_address)
        controls.add_widget(mode_row)

        self.origin_map = create_map_view(lat=DEFAULT_LAT, lon=DEFAULT_LON, zoom=12, size_hint_y=None, height=dp(220))
        controls.add_widget(self.origin_map)
        self.origin_marker = MapMarker(lat=DEFAULT_LAT, lon=DEFAULT_LON)
        self.origin_map.add_marker(self.origin_marker)
        self.origin_map.bind(on_touch_up=self.on_origin_map_touch)

        address_row = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(46))
        self.address_input = TextInput(hint_text="Escribe una dirección", multiline=False, size_hint_y=None, height=dp(46), background_normal="", background_active="", background_color=COLORS["white"], foreground_color=COLORS["text"], padding=[dp(10), dp(12), dp(10), 0])
        address_btn = SmallButton(text="Usar dirección")
        address_btn.bind(on_release=lambda *_: self.use_address())
        address_row.add_widget(self.address_input)
        address_row.add_widget(address_btn)
        controls.add_widget(address_row)

        self.radius_label = TitleLabel(text=f"Rango: {self.radius_km} km", size_hint_y=None, height=dp(32), font_size="20sp")
        controls.add_widget(self.radius_label)
        self.slider = Slider(min=1, max=100, value=self.radius_km, step=1, size_hint_y=None, height=dp(44))
        self.slider.bind(value=self.on_radius_change)
        controls.add_widget(self.slider)

        action_row = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(46))
        gps_btn = SecondaryButton(text="Actualizar GPS")
        gps_btn.bind(on_release=lambda *_: App.get_running_app().request_gps())
        search_btn = SmallButton(text="Buscar cercanos")
        search_btn.bind(on_release=lambda *_: self.search_nearby())
        action_row.add_widget(gps_btn)
        action_row.add_widget(search_btn)
        controls.add_widget(action_row)
        body.add_widget(controls)

        self.results_content = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.results_content.bind(minimum_height=self.results_content.setter("height"))
        body.add_widget(self.results_content)

        Clock.schedule_once(lambda *_: self.render_message("Ajusta origen y rango, luego presiona “Buscar cercanos”."), 0.2)

    def on_pre_enter(self, *_: Any) -> None:
        app = App.get_running_app()
        if not app.has_requested_gps:
            app.request_gps()
        self.ensure_origin_fallback()

    def on_location_update(self, lat: float, lon: float) -> None:
        if self.selected_origin_source == "gps":
            self.set_selected_origin(lat, lon, "gps")

    def set_origin_mode(self, mode: str) -> None:
        self.selected_origin_source = mode
        if mode == "gps":
            app = App.get_running_app()
            self.set_selected_origin(app.current_lat, app.current_lon, "gps")
            self.render_message("Se usará tu GPS actual como origen de búsqueda.")
        elif mode == "manual":
            self.render_message("Toca el mapa para elegir el punto manual de búsqueda.")
        else:
            self.render_message("Escribe una dirección y pulsa “Usar dirección”.")
        self.update_origin_status()

    def on_origin_map_touch(self, mapview: MapView, touch: Any) -> bool:
        if not self.mode_manual.state == "down":
            return False
        if not mapview.collide_point(*touch.pos):
            return False
        if getattr(touch, "is_mouse_scrolling", False) or getattr(touch, "grab_current", None):
            return False
        try:
            origin = getattr(touch, "opos", touch.pos)
            if math.hypot(touch.x - origin[0], touch.y - origin[1]) > dp(12):
                return False
        except Exception:
            return False
        try:
            coordinate = mapview.get_latlon_at(*touch.pos)
            lat = coordinate.lat if hasattr(coordinate, "lat") else coordinate[0]
            lon = coordinate.lon if hasattr(coordinate, "lon") else coordinate[1]
            self.set_selected_origin(lat, lon, "manual")
            self.render_message("Punto manual actualizado. Ya puedes buscar por rango.")
            return False
        except Exception:
            return False

    def set_selected_origin(self, lat: float, lon: float, source: str) -> None:
        self.selected_origin_lat = float(lat)
        self.selected_origin_lon = float(lon)
        self.selected_origin_source = source
        self.origin_marker.lat = float(lat)
        self.origin_marker.lon = float(lon)
        self.origin_map.center_on(float(lat), float(lon))
        self.update_origin_status()

    def update_origin_status(self) -> None:
        lat = self.selected_origin_lat
        lon = self.selected_origin_lon
        source_labels = {"gps": "GPS", "manual": "Punto manual", "address": "Dirección"}
        source_text = source_labels.get(self.selected_origin_source, "GPS")
        if lat is None or lon is None:
            self.origin_status.text = f"Origen actual: {source_text}"
        else:
            self.origin_status.text = f"Origen actual: {source_text} ({lat:.5f}, {lon:.5f})"

    def ensure_origin_fallback(self) -> tuple[float, float, str]:
        app = App.get_running_app()
        if self.selected_origin_lat is None or self.selected_origin_lon is None:
            self.set_selected_origin(app.current_lat, app.current_lon, "gps")
        return self.selected_origin_lat, self.selected_origin_lon, self.selected_origin_source

    def use_address(self) -> None:
        address = self.address_input.text.strip()
        if not address:
            self.render_message("Debes escribir una dirección antes de usarla.")
            return
        self.render_message("Buscando dirección...")

        def worker() -> None:
            try:
                response = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": address, "format": "json", "limit": 1},
                    timeout=20,
                    headers={"User-Agent": "CumbrePark prototype / Python Kivy"},
                )
                response.raise_for_status()
                data = response.json()
                if not data:
                    raise ValueError("No se encontró la dirección ingresada.")
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                Clock.schedule_once(lambda *_: self.after_address_resolved(lat, lon), 0)
            except Exception as exc:
                Clock.schedule_once(lambda *_: self.render_message(f"No se pudo resolver la dirección: {exc}"), 0)

        threading.Thread(target=worker, daemon=True).start()

    def after_address_resolved(self, lat: float, lon: float) -> None:
        self.mode_address.state = "down"
        self.mode_gps.state = "normal"
        self.mode_manual.state = "normal"
        self.set_selected_origin(lat, lon, "address")
        self.render_message("Dirección encontrada y marcada como origen.")

    def on_radius_change(self, _: Slider, value: float) -> None:
        self.radius_km = int(value)
        self.radius_label.text = f"Rango: {self.radius_km} km"

    def render_message(self, message: str) -> None:
        self.results_content.clear_widgets()
        panel = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(88), bg_color=COLORS["white"])
        panel.add_widget(BodyLabel(text=message))
        self.results_content.add_widget(panel)

    def search_nearby(self) -> None:
        origin_lat, origin_lon, origin_source = self.ensure_origin_fallback()
        radius_m = int(self.radius_km * 1000)
        self.render_message(f"Buscando lugares en {self.radius_km} km desde {origin_source}...")

        def worker() -> None:
            try:
                query = f"""
                [out:json][timeout:25];
                (
                  node(around:{radius_m},{origin_lat},{origin_lon})["leisure"~"park|nature_reserve"];
                  way(around:{radius_m},{origin_lat},{origin_lon})["leisure"~"park|nature_reserve"];
                  relation(around:{radius_m},{origin_lat},{origin_lon})["leisure"~"park|nature_reserve"];

                  node(around:{radius_m},{origin_lat},{origin_lon})["boundary"="protected_area"];
                  way(around:{radius_m},{origin_lat},{origin_lon})["boundary"="protected_area"];
                  relation(around:{radius_m},{origin_lat},{origin_lon})["boundary"="protected_area"];

                  node(around:{radius_m},{origin_lat},{origin_lon})["route"="hiking"];
                  way(around:{radius_m},{origin_lat},{origin_lon})["route"="hiking"];
                  relation(around:{radius_m},{origin_lat},{origin_lon})["route"="hiking"];

                  node(around:{radius_m},{origin_lat},{origin_lon})["tourism"~"viewpoint|attraction"];
                  way(around:{radius_m},{origin_lat},{origin_lon})["tourism"~"viewpoint|attraction"];
                  relation(around:{radius_m},{origin_lat},{origin_lon})["tourism"~"viewpoint|attraction"];

                  node(around:{radius_m},{origin_lat},{origin_lon})["natural"~"peak|wood"];
                  way(around:{radius_m},{origin_lat},{origin_lon})["natural"~"peak|wood"];
                  relation(around:{radius_m},{origin_lat},{origin_lon})["natural"~"peak|wood"];
                );
                out center tags 80;
                """
                response = requests.post(
                    "https://overpass-api.de/api/interpreter",
                    data={"data": query},
                    timeout=30,
                    headers={"User-Agent": "CumbrePark prototype / Python Kivy"},
                )
                response.raise_for_status()
                data = response.json()
                places = self.parse_places(data, origin_lat, origin_lon)
                Clock.schedule_once(lambda *_: self.render_places(places), 0)
            except Exception as exc:
                Clock.schedule_once(lambda *_: self.render_message(f"No se pudo buscar: {exc}"), 0)

        threading.Thread(target=worker, daemon=True).start()

    def parse_places(self, data: dict[str, Any], origin_lat: float, origin_lon: float) -> list[Place]:
        places: list[Place] = []
        seen: set[tuple[str, int]] = set()
        for element in data.get("elements", []):
            tags = element.get("tags", {}) or {}
            name = tags.get("name") or tags.get("name:es") or "Lugar sin nombre registrado"
            lat = element.get("lat") or element.get("center", {}).get("lat")
            lon = element.get("lon") or element.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue
            key = (str(name).lower(), int(float(lat) * 1000))
            if key in seen:
                continue
            seen.add(key)
            distance = haversine_km(origin_lat, origin_lon, float(lat), float(lon))
            places.append(Place(name=str(name), kind=detect_place_kind(tags), lat=float(lat), lon=float(lon), distance_km=distance))
        places.sort(key=lambda item: item.distance_km)
        return places[:40]

    def render_places(self, places: list[Place]) -> None:
        self.results_content.clear_widgets()
        if not places:
            self.render_message("No encontré resultados en ese rango. Prueba aumentando la distancia.")
            return
        title_panel = RoundedPanel(orientation="vertical", bg_color=COLORS["mint"], size_hint_y=None, height=dp(78))
        title_panel.add_widget(TitleLabel(text=f"{len(places)} lugares encontrados", size_hint_y=None, height=dp(30), font_size="19sp"))
        title_panel.add_widget(MutedLabel(text="Ordenados por distancia desde el origen seleccionado.", size_hint_y=None, height=dp(24)))
        self.results_content.add_widget(title_panel)
        for place in places:
            self.results_content.add_widget(PlaceCard(place=place))


class ActivityScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "register_activity"
        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header("Registrar actividad"))

        self.map_widget = LocationMap(selectable=False, size_hint_y=0.48)
        root.add_widget(self.map_widget)

        panel = RoundedPanel(
            orientation="vertical",
            size_hint_y=0.52,
            bg_color=COLORS["soft"],
            padding=[dp(14), dp(10), dp(14), dp(12)],
            spacing=dp(6),
        )
        self.state_label = BodyLabel(text="Actividad lista", size_hint_y=0.16, halign="center")
        self.metrics_label = TitleLabel(
            text="00:00:00\n0.00 km",
            size_hint_y=0.38,
            font_size="25sp",
            halign="center",
            valign="middle",
        )
        self.detail_label = MutedLabel(
            text="Velocidad media: 0.0 km/h · Desnivel: +0 m / -0 m",
            size_hint_y=0.16,
            halign="center",
        )
        for label in (self.state_label, self.metrics_label, self.detail_label):
            label.bind(size=lambda instance, _size: setattr(instance, "text_size", instance.size))
            panel.add_widget(label)

        actions = GridLayout(cols=3, spacing=dp(8), size_hint_y=0.30)
        self.start_button = PrimaryButton(text="Iniciar")
        self.pause_button = SecondaryButton(text="Pausar")
        self.finish_button = SecondaryButton(text="Finalizar")
        self.start_button.bind(on_release=lambda *_: self.start_or_resume())
        self.pause_button.bind(on_release=lambda *_: App.get_running_app().pause_activity())
        self.finish_button.bind(on_release=lambda *_: App.get_running_app().finish_activity())
        actions.add_widget(self.start_button)
        actions.add_widget(self.pause_button)
        actions.add_widget(self.finish_button)
        panel.add_widget(actions)
        root.add_widget(panel)

        Clock.schedule_interval(lambda _dt: self.refresh(), 1)

    def on_pre_enter(self, *_: Any) -> None:
        self.refresh()

    def on_location_update(self, lat: float, lon: float) -> None:
        self.map_widget.set_marker(lat, lon, center=True)

    def start_or_resume(self) -> None:
        app = App.get_running_app()
        if app.active_activity and app.activity_paused:
            app.resume_activity()
        elif not app.active_activity:
            app.start_activity("Trekking")
        self.refresh()

    def refresh(self) -> None:
        app = App.get_running_app()
        record = app.active_activity
        if not record:
            self.state_label.text = "Actividad lista · Trekking"
            self.metrics_label.text = "00:00:00\n0.00 km"
            self.detail_label.text = "Velocidad media: 0.0 km/h · Desnivel: +0 m / -0 m"
            self.start_button.text = "Iniciar"
            return
        seconds = app.activity_elapsed_seconds()
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        speed = record.distance_km / (seconds / 3600) if seconds > 0 else 0.0
        self.state_label.text = "Actividad pausada" if app.activity_paused else "Grabando recorrido con GPS"
        self.metrics_label.text = f"{hours:02d}:{minutes:02d}:{secs:02d}\n{record.distance_km:.2f} km"
        self.detail_label.text = (
            f"Velocidad media: {speed:.1f} km/h · Desnivel: +{record.ascent_m:.0f} m / -{record.descent_m:.0f} m"
        )
        self.start_button.text = "Reanudar" if app.activity_paused else "Grabando"


class ActivityHistoryScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "sports_history"
        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header("Mis actividades"))
        scroll = ScrollView(do_scroll_x=False)
        self.content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(14), dp(12), dp(14), dp(24)],
            size_hint_y=None,
        )
        self.content.bind(minimum_height=self.content.setter("height"))
        scroll.add_widget(self.content)
        root.add_widget(scroll)

    def on_pre_enter(self, *_: Any) -> None:
        self.render()

    def render(self) -> None:
        self.content.clear_widgets()
        records = App.get_running_app().load_activity_history()
        if not records:
            panel = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(100), bg_color=COLORS["soft"])
            panel.add_widget(BodyLabel(text="Aún no hay actividades guardadas. Inicia una desde el comienzo."))
            self.content.add_widget(panel)
            return
        for record in reversed(records[-30:]):
            seconds = int(record.get("elapsed_seconds", 0))
            hours, remainder = divmod(seconds, 3600)
            minutes, _seconds = divmod(remainder, 60)
            date = str(record.get("started_at", ""))[:16].replace("T", " ")
            panel = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(118), bg_color=COLORS["white"])
            panel.add_widget(TitleLabel(text=f"{record.get('sport', 'Actividad')} · {date}", size_hint_y=None, height=dp(34), font_size="18sp"))
            panel.add_widget(BodyLabel(
                text=f"{float(record.get('distance_km', 0)):.2f} km · {hours:02d}:{minutes:02d} h · +{float(record.get('ascent_m', 0)):.0f} m",
                size_hint_y=None,
                height=dp(30),
            ))
            panel.add_widget(MutedLabel(text=f"{len(record.get('points', []))} puntos GPS guardados en el dispositivo", size_hint_y=None, height=dp(26)))
            self.content.add_widget(panel)


class PlaceCard(RoundedPanel):
    def __init__(self, place: Place, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", bg_color=COLORS["white"], size_hint_y=None, height=dp(176), **kwargs)
        self.place = place
        self.spacing = dp(4)
        self.padding = [dp(12), dp(10), dp(12), dp(10)]
        self.border_color = (0.78, 0.89, 0.93, 1)
        title = TitleLabel(text=place.name, size_hint_y=None, height=dp(44), font_size="18sp")
        title.max_lines = 2
        title.text_size = (Window.width - dp(72), dp(44))
        subtitle = BodyLabel(text=f"{place.kind} · {place.distance_km:.1f} km", size_hint_y=None, height=dp(26), font_size="14sp")
        coords = MutedLabel(text=f"{place.lat:.5f}, {place.lon:.5f}", size_hint_y=None, height=dp(22), font_size="12sp")
        source = MutedLabel(text=f"Fuente: {place.source}", size_hint_y=None, height=dp(20), font_size="12sp")
        self.add_widget(title)
        self.add_widget(subtitle)
        self.add_widget(coords)
        self.add_widget(source)
        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(38))
        map_btn = SmallButton(text="Ver en mapa", height=dp(38))
        google_btn = SmallButton(text="Google Maps", height=dp(38))
        map_btn.bind(on_release=lambda *_: App.get_running_app().open_place_in_weather(place))
        google_btn.bind(on_release=lambda *_: App.get_running_app().open_google_maps(place.lat, place.lon))
        actions.add_widget(map_btn)
        actions.add_widget(google_btn)
        self.add_widget(actions)


class CumbreParkApp(App):
    current_lat = NumericProperty(DEFAULT_LAT)
    current_lon = NumericProperty(DEFAULT_LON)
    status = StringProperty("Listo")
    settings = DictProperty({})

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.title = "CumbrePark"
        self.has_requested_gps = False
        self.gps_running = False
        self.has_real_gps_fix = False
        self.last_gps_accuracy: Optional[float] = None
        self.sm: Optional[ScreenManager] = None
        self.data_dir = Path(".")
        self.offline_cache_dir = Path("map_cache")
        self.gps_timeout_event = None
        self.last_fix_monotonic: Optional[float] = None
        self.active_activity: Optional[ActivityRecord] = None
        self.activity_paused = False
        self.activity_segment_started: Optional[float] = None
        self.activity_accumulated_seconds = 0.0
        self.last_track_monotonic: Optional[float] = None
        self.last_activity_checkpoint = 0.0

    def build(self) -> ScreenManager:
        Window.clearcolor = COLORS["white"]
        self.data_dir = Path(self.user_data_dir)
        self.offline_cache_dir = self.data_dir / "map_cache"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.offline_cache_dir.mkdir(parents=True, exist_ok=True)
        self.restore_last_location()
        self.restore_active_activity()
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.sm.add_widget(HomeScreen())
        self.sm.add_widget(WeatherScreen())
        self.sm.add_widget(NearbyScreen())
        self.sm.add_widget(DownloadMapScreen())
        self.sm.add_widget(EmergencyScreen())
        self.sm.add_widget(ActivityScreen())
        self.sm.add_widget(ActivityHistoryScreen())
        Clock.schedule_once(lambda *_: self.request_gps(), 0.8)
        return self.sm

    def go_to(self, screen_name: str) -> None:
        if self.sm:
            self.sm.current = screen_name

    def go_home(self) -> None:
        self.go_to("home")

    def restore_last_location(self) -> None:
        saved = read_json(self.data_dir / "last_location.json", {})
        try:
            lat = float(saved["lat"])
            lon = float(saved["lon"])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                self.current_lat, self.current_lon = lat, lon
                self.last_gps_accuracy = float(saved["accuracy"]) if saved.get("accuracy") is not None else None
        except (KeyError, TypeError, ValueError):
            pass

    def set_current_location(
        self,
        lat: float,
        lon: float,
        accuracy: Optional[float] = None,
        altitude: Optional[float] = None,
    ) -> None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            self.set_status("GPS entregó una coordenada inválida. Se ignoró.")
            return

        if accuracy is not None and accuracy > 2000:
            self.set_status(f"GPS con poca precisión ({accuracy:.0f} m). Esperando mejor señal...")
            return

        now = time.monotonic()
        if self.has_real_gps_fix:
            jump_km = haversine_km(self.current_lat, self.current_lon, lat, lon)
            elapsed = max(1.0, now - (self.last_fix_monotonic or now))
            implied_speed_kmh = jump_km / (elapsed / 3600.0)
            if jump_km > 2 and implied_speed_kmh > 220:
                self.set_status("GPS inestable: se ignoró un salto extraño de ubicación.")
                return

        self.current_lat = lat
        self.current_lon = lon
        self.last_gps_accuracy = accuracy
        self.has_real_gps_fix = True
        self.last_fix_monotonic = now
        atomic_write_json(
            self.data_dir / "last_location.json",
            {"lat": lat, "lon": lon, "accuracy": accuracy, "altitude": altitude, "updated_at": utc_now_iso()},
        )

        if self.gps_timeout_event:
            self.gps_timeout_event.cancel()
            self.gps_timeout_event = None

        if self.active_activity and not self.activity_paused and (accuracy is None or accuracy <= 120):
            self.record_track_point(lat, lon, altitude, accuracy)

        for screen in self.sm.screens if self.sm else []:
            callback = getattr(screen, "on_location_update", None)
            if callable(callback):
                callback(lat, lon)
        accuracy_text = f" · precisión {accuracy:.0f} m" if accuracy is not None else ""
        self.set_status(f"Ubicación GPS lista{accuracy_text}")

    def set_status(self, message: str) -> None:
        self.status = message
        if self.sm:
            home = self.sm.get_screen("home")
            if hasattr(home, "set_status"):
                home.set_status(message)

    def request_gps(self) -> None:
        self.has_requested_gps = True
        if self.gps_running:
            self.set_status("GPS activo. Esperando una ubicación más precisa...")
            return
        self.set_status("Solicitando permiso de ubicación...")
        if platform == "android":
            try:
                from android.permissions import Permission, check_permission, request_permissions

                permissions = [Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION]
                if all(check_permission(permission) for permission in permissions):
                    self._start_gps()
                else:
                    request_permissions(permissions, self._on_location_permissions)
                return
            except Exception as exc:
                self.set_status(f"No se pudo solicitar ubicación: {exc}")
                return
        self._start_gps()

    def _on_location_permissions(self, _permissions: list[str], grants: list[bool]) -> None:
        granted = bool(grants) and any(grants)
        Clock.schedule_once(lambda _dt: self._finish_location_permission(granted), 0)

    def _finish_location_permission(self, granted: bool) -> None:
        if granted:
            self._start_gps()
        else:
            self.set_status("Permiso GPS rechazado. Puedes elegir una ubicación manual en el mapa.")

    def _start_gps(self) -> None:
        try:
            from plyer import gps

            gps.configure(on_location=self._on_gps_location, on_status=self._on_gps_status)
            gps.start(minTime=3000, minDistance=5)
            self.gps_running = True
            self.set_status("GPS iniciado. Esperando coordenadas reales...")
            self.gps_timeout_event = Clock.schedule_once(
                lambda _dt: self.set_status("Sin señal GPS nueva. Se mantiene la última ubicación válida o el punto manual."),
                20,
            )
        except Exception as exc:
            self.set_status(f"GPS no disponible. Puedes usar una ubicación manual. Detalle: {exc}")

    def _on_gps_location(self, **kwargs: Any) -> None:
        try:
            lat = float(kwargs.get("lat"))
            lon = float(kwargs.get("lon"))
            accuracy_raw = kwargs.get("accuracy")
            accuracy = float(accuracy_raw) if accuracy_raw is not None else None
            altitude_raw = kwargs.get("altitude")
            altitude = float(altitude_raw) if altitude_raw is not None else None
            Clock.schedule_once(lambda *_: self.set_current_location(lat, lon, accuracy, altitude), 0)
        except Exception:
            pass

    def _on_gps_status(self, status_type: str, status_message: str) -> None:
        Clock.schedule_once(lambda *_: self.set_status(f"GPS: {status_type} · {status_message}"), 0)

    @property
    def activity_history_path(self) -> Path:
        return self.data_dir / "activities.json"

    @property
    def active_activity_path(self) -> Path:
        return self.data_dir / "active_activity.json"

    def restore_active_activity(self) -> None:
        payload = read_json(self.active_activity_path, {})
        if not isinstance(payload, dict) or not payload.get("started_at"):
            return
        try:
            points = [
                TrackPoint(
                    lat=float(item["lat"]),
                    lon=float(item["lon"]),
                    altitude=float(item["altitude"]) if item.get("altitude") is not None else None,
                    accuracy=float(item["accuracy"]) if item.get("accuracy") is not None else None,
                    recorded_at=str(item["recorded_at"]),
                )
                for item in payload.get("points", [])
                if isinstance(item, dict)
            ]
            self.active_activity = ActivityRecord(
                started_at=str(payload["started_at"]),
                sport=str(payload.get("sport", "Trekking")),
                elapsed_seconds=float(payload.get("elapsed_seconds", 0)),
                distance_km=float(payload.get("distance_km", 0)),
                ascent_m=float(payload.get("ascent_m", 0)),
                descent_m=float(payload.get("descent_m", 0)),
                points=points,
            )
            self.activity_accumulated_seconds = self.active_activity.elapsed_seconds
            self.activity_paused = True
        except (KeyError, TypeError, ValueError):
            self.active_activity = None

    def save_active_activity(self, force: bool = False) -> None:
        if not self.active_activity:
            return
        now = time.monotonic()
        if not force and now - self.last_activity_checkpoint < 10:
            return
        self.active_activity.elapsed_seconds = self.activity_elapsed_seconds()
        atomic_write_json(self.active_activity_path, self.active_activity.to_dict())
        self.last_activity_checkpoint = now

    def start_activity(self, sport: str) -> None:
        if self.active_activity:
            return
        self.active_activity = ActivityRecord(started_at=utc_now_iso(), sport=sport)
        self.activity_paused = False
        self.activity_accumulated_seconds = 0.0
        self.activity_segment_started = time.monotonic()
        self.last_track_monotonic = None
        self.request_gps()
        self.save_active_activity(force=True)
        self.set_status("Actividad iniciada. Mantén la ubicación activada durante el recorrido.")

    def pause_activity(self) -> None:
        if not self.active_activity or self.activity_paused:
            return
        if self.activity_segment_started is not None:
            self.activity_accumulated_seconds += time.monotonic() - self.activity_segment_started
        self.activity_segment_started = None
        self.activity_paused = True
        self.save_active_activity(force=True)
        self.set_status("Actividad pausada.")

    def resume_activity(self) -> None:
        if not self.active_activity or not self.activity_paused:
            return
        self.activity_segment_started = time.monotonic()
        self.last_track_monotonic = None
        self.activity_paused = False
        self.save_active_activity(force=True)
        self.set_status("Actividad reanudada.")

    def activity_elapsed_seconds(self) -> float:
        elapsed = self.activity_accumulated_seconds
        if self.active_activity and not self.activity_paused and self.activity_segment_started is not None:
            elapsed += time.monotonic() - self.activity_segment_started
        return max(0.0, elapsed)

    def record_track_point(
        self,
        lat: float,
        lon: float,
        altitude: Optional[float],
        accuracy: Optional[float],
    ) -> None:
        record = self.active_activity
        if not record:
            return
        now = time.monotonic()
        point = TrackPoint(lat=lat, lon=lon, altitude=altitude, accuracy=accuracy, recorded_at=utc_now_iso())
        if record.points:
            previous = record.points[-1]
            segment_km = haversine_km(previous.lat, previous.lon, lat, lon)
            seconds = max(1.0, now - (self.last_track_monotonic or now))
            speed_kmh = segment_km / (seconds / 3600.0)
            noise_floor_km = max(0.004, ((accuracy or 0.0) + (previous.accuracy or 0.0)) / 2500.0)
            if segment_km < noise_floor_km:
                return
            if speed_kmh > 160:
                return
            record.distance_km += segment_km
            if altitude is not None and previous.altitude is not None:
                elevation_delta = altitude - previous.altitude
                if elevation_delta >= 3:
                    record.ascent_m += elevation_delta
                elif elevation_delta <= -3:
                    record.descent_m += abs(elevation_delta)
        record.points.append(point)
        self.last_track_monotonic = now
        self.save_active_activity()

    def finish_activity(self) -> None:
        record = self.active_activity
        if not record:
            self.set_status("No hay una actividad activa para finalizar.")
            return
        record.elapsed_seconds = self.activity_elapsed_seconds()
        record.ended_at = utc_now_iso()
        history = self.load_activity_history()
        history.append(record.to_dict())
        atomic_write_json(self.activity_history_path, history[-200:])
        self.active_activity = None
        self.activity_paused = False
        self.activity_segment_started = None
        self.activity_accumulated_seconds = 0.0
        self.last_track_monotonic = None
        try:
            self.active_activity_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.set_status("Actividad guardada en Mis actividades.")
        if self.sm:
            self.sm.get_screen("register_activity").refresh()

    def load_activity_history(self) -> list[dict[str, Any]]:
        payload = read_json(self.activity_history_path, [])
        return payload if isinstance(payload, list) else []

    def open_google_maps(self, lat: Optional[float] = None, lon: Optional[float] = None) -> None:
        final_lat = self.current_lat if lat is None else lat
        final_lon = self.current_lon if lon is None else lon
        webbrowser.open(f"https://www.google.com/maps/search/?api=1&query={final_lat},{final_lon}")

    def open_place_in_weather(self, place: Place) -> None:
        if not self.sm:
            return
        weather_screen = self.sm.get_screen("weather")
        self.sm.current = "weather"
        Clock.schedule_once(lambda *_: weather_screen.select_point(place.lat, place.lon), 0.2)

    def on_pause(self) -> bool:
        self.save_active_activity(force=True)
        return True

    def on_stop(self) -> None:
        self.save_active_activity(force=True)
        if self.gps_running:
            try:
                from plyer import gps

                gps.stop()
            except Exception:
                pass


if __name__ == "__main__":
    CumbreParkApp().run()
