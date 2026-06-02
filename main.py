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
import threading
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import DictProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

try:
    from kivy_garden.mapview import MapMarker, MapView

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


# Paleta tomada del logo: azul profundo, azul petróleo, celeste/mint claro y blanco.
COLORS = {
    "navy": (0.03, 0.20, 0.31, 1),       # #08334F aprox.
    "blue": (0.04, 0.34, 0.48, 1),       # #0A567A aprox.
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


class BodyLabel(Label):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.color = COLORS["text"]
        self.font_size = "14sp"
        self.halign = "left"
        self.valign = "middle"
        self.bind(size=self.setter("text_size"))


class MutedLabel(Label):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.color = COLORS["muted"]
        self.font_size = "13sp"
        self.halign = "left"
        self.valign = "middle"
        self.bind(size=self.setter("text_size"))


class Header(BoxLayout):
    def __init__(self, title: str, back: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(62)
        self.padding = [dp(12), dp(8), dp(12), dp(8)]
        self.spacing = dp(10)
        if back:
            back_btn = SecondaryButton(text="‹ Inicio")
            back_btn.width = dp(96)
            back_btn.size_hint_x = None
            back_btn.bind(on_release=lambda *_: App.get_running_app().go_home())
            self.add_widget(back_btn)
        logo = Image(source="assets/logo_cumbrepark.png", fit_mode="contain", size_hint_x=None, width=dp(52))
        self.add_widget(logo)
        self.add_widget(TitleLabel(text=title))


class LocationMap(BoxLayout):
    """Mapa reutilizable con un marcador principal."""

    marker = ObjectProperty(None, allownone=True)

    def __init__(self, selectable: bool = False, on_select: Optional[Callable[[float, float], None]] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.selectable = selectable
        self.on_select = on_select
        self.map = MapView(zoom=DEFAULT_ZOOM, lat=DEFAULT_LAT, lon=DEFAULT_LON)
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


class HomeScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "home"
        self.has_centered_on_gps = False

        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)

        logo = Image(source="assets/logo_cumbrepark.png", fit_mode="contain", size_hint_y=0.28)
        root.add_widget(logo)

        title = Label(
            text="CumbrePark",
            color=COLORS["navy"],
            font_size="34sp",
            bold=True,
            size_hint_y=None,
            height=dp(42),
        )
        root.add_widget(title)

        subtitle = Label(
            text="Parques, senderos, clima y ubicación para explorar con más seguridad.",
            color=COLORS["muted"],
            font_size="14sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(42),
        )
        subtitle.bind(size=subtitle.setter("text_size"))
        root.add_widget(subtitle)

        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(114))
        btn_map = PrimaryButton(text="Mapa + clima")
        btn_near = PrimaryButton(text="Cercanos")
        btn_route = SecondaryButton(text="Mis rutas\n(próximo)")
        btn_safety = SecondaryButton(text="Seguridad\n(próximo)")
        btn_map.bind(on_release=lambda *_: App.get_running_app().go_to("weather"))
        btn_near.bind(on_release=lambda *_: App.get_running_app().go_to("nearby"))
        grid.add_widget(btn_map)
        grid.add_widget(btn_near)
        grid.add_widget(btn_route)
        grid.add_widget(btn_safety)
        root.add_widget(grid)

        panel = RoundedPanel(orientation="vertical", size_hint_y=0.42, bg_color=COLORS["soft"])
        panel.add_widget(BodyLabel(text="Ubicación en vivo", size_hint_y=None, height=dp(24)))
        self.status_label = MutedLabel(text="Puedes activar GPS para centrar el mapa en tu ubicación.", size_hint_y=None, height=dp(38))
        panel.add_widget(self.status_label)

        self.map_preview = LocationMap(size_hint_y=1)
        panel.add_widget(self.map_preview)

        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(44))
        gps_btn = SmallButton(text="Usar mi ubicación")
        maps_btn = SmallButton(text="Abrir Google Maps")
        gps_btn.bind(on_release=lambda *_: self.request_home_gps())
        maps_btn.bind(on_release=lambda *_: App.get_running_app().open_google_maps())
        actions.add_widget(gps_btn)
        actions.add_widget(maps_btn)
        panel.add_widget(actions)
        root.add_widget(panel)

    def request_home_gps(self) -> None:
        # V.0.1.1:
        # Al pedir ubicación desde el inicio, centramos el mapa una vez.
        # Luego dejamos que la persona pueda mover el mapa sin que vuelva solo.
        self.has_centered_on_gps = False
        App.get_running_app().request_gps()

    def on_location_update(self, lat: float, lon: float) -> None:
        should_center = not self.has_centered_on_gps
        self.map_preview.set_marker(lat, lon, center=should_center)
        self.has_centered_on_gps = True
        self.status_label.text = f"GPS activo: {lat:.5f}, {lon:.5f}"

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

        intro = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(92), bg_color=COLORS["soft"])
        intro.add_widget(BodyLabel(text="Toca un punto del mapa para consultar clima local.", size_hint_y=None, height=dp(26)))
        intro.add_widget(MutedLabel(text="El panel resume temperatura, lluvia y viento. Es una base para evolucionar hacia capas tipo Windy.", size_hint_y=None, height=dp(36)))
        root.add_widget(intro)

        self.map_widget = LocationMap(selectable=True, on_select=self.select_point_from_map, size_hint_y=0.48)
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
        self.weather_content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12), size_hint_y=None)
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

        summary = RoundedPanel(orientation="vertical", bg_color=COLORS["mint"], size_hint_y=None, height=dp(176))
        summary.add_widget(TitleLabel(text="Clima del punto seleccionado", size_hint_y=None, height=dp(34)))
        summary.add_widget(BodyLabel(text=f"Coordenadas: {lat:.5f}, {lon:.5f}", size_hint_y=None, height=dp(24)))
        summary.add_widget(BodyLabel(text=f"Estado: {weather_description(code)}", size_hint_y=None, height=dp(24)))
        summary.add_widget(BodyLabel(text=f"Temperatura: {temp} {units.get('temperature_2m', '°C')}  |  Humedad: {hum}%", size_hint_y=None, height=dp(24)))
        summary.add_widget(BodyLabel(text=f"Lluvia actual: {rain} {units.get('precipitation', 'mm')}  |  Viento: {wind} {units.get('wind_speed_10m', 'km/h')} dir. {wdir}°", size_hint_y=None, height=dp(34)))
        self.weather_content.add_widget(summary)

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])[:8]
        temps = hourly.get("temperature_2m", [])[:8]
        probs = hourly.get("precipitation_probability", [])[:8]
        winds = hourly.get("wind_speed_10m", [])[:8]

        forecast_panel = RoundedPanel(orientation="vertical", bg_color=COLORS["white"], size_hint_y=None)
        forecast_panel.add_widget(TitleLabel(text="Próximas horas", size_hint_y=None, height=dp(34)))
        for idx, hour in enumerate(times):
            line = f"{hour[-5:]}  ·  {temps[idx] if idx < len(temps) else '-'}°C  ·  lluvia {probs[idx] if idx < len(probs) else '-'}%  ·  viento {winds[idx] if idx < len(winds) else '-'} km/h"
            forecast_panel.add_widget(MutedLabel(text=line, size_hint_y=None, height=dp(28)))
        forecast_panel.height = dp(48 + 28 * max(1, len(times)))
        self.weather_content.add_widget(forecast_panel)


class NearbyScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "nearby"
        self.radius_km = 10

        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header("Cercanos"))

        controls = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(170), bg_color=COLORS["soft"])
        controls.add_widget(BodyLabel(text="Busca parques, trekkings, senderos y reservas cercanas a tu GPS.", size_hint_y=None, height=dp(30)))
        self.radius_label = TitleLabel(text=f"Rango: {self.radius_km} km", size_hint_y=None, height=dp(34))
        controls.add_widget(self.radius_label)
        self.slider = Slider(min=1, max=100, value=self.radius_km, step=1, size_hint_y=None, height=dp(44))
        self.slider.bind(value=self.on_radius_change)
        controls.add_widget(self.slider)
        row = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(46))
        gps_btn = SmallButton(text="Actualizar GPS")
        gps_btn.bind(on_release=lambda *_: App.get_running_app().request_gps())
        search_btn = SmallButton(text="Buscar cercanos")
        search_btn.bind(on_release=lambda *_: self.search_nearby())
        row.add_widget(gps_btn)
        row.add_widget(search_btn)
        controls.add_widget(row)
        root.add_widget(controls)

        self.results_scroll = ScrollView()
        self.results_content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12), size_hint_y=None)
        self.results_content.bind(minimum_height=self.results_content.setter("height"))
        self.results_scroll.add_widget(self.results_content)
        root.add_widget(self.results_scroll)

        Clock.schedule_once(lambda *_: self.render_message("Ajusta el rango y presiona “Buscar cercanos”."), 0.2)

    def on_pre_enter(self, *_: Any) -> None:
        app = App.get_running_app()
        if not app.has_requested_gps:
            app.request_gps()

    def on_location_update(self, lat: float, lon: float) -> None:
        # No se busca automáticamente para no gastar datos; se actualiza con el botón.
        pass

    def on_radius_change(self, _: Slider, value: float) -> None:
        self.radius_km = int(value)
        self.radius_label.text = f"Rango: {self.radius_km} km"

    def render_message(self, message: str) -> None:
        self.results_content.clear_widgets()
        panel = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(112), bg_color=COLORS["white"])
        panel.add_widget(BodyLabel(text=message))
        self.results_content.add_widget(panel)

    def search_nearby(self) -> None:
        app = App.get_running_app()
        lat = app.current_lat
        lon = app.current_lon
        radius_m = int(self.radius_km * 1000)
        self.render_message(f"Buscando lugares en un radio de {self.radius_km} km...")

        def worker() -> None:
            try:
                query = f"""
                [out:json][timeout:25];
                (
                  node(around:{radius_m},{lat},{lon})["leisure"~"park|nature_reserve"];
                  way(around:{radius_m},{lat},{lon})["leisure"~"park|nature_reserve"];
                  relation(around:{radius_m},{lat},{lon})["leisure"~"park|nature_reserve"];

                  node(around:{radius_m},{lat},{lon})["boundary"="protected_area"];
                  way(around:{radius_m},{lat},{lon})["boundary"="protected_area"];
                  relation(around:{radius_m},{lat},{lon})["boundary"="protected_area"];

                  node(around:{radius_m},{lat},{lon})["route"="hiking"];
                  way(around:{radius_m},{lat},{lon})["route"="hiking"];
                  relation(around:{radius_m},{lat},{lon})["route"="hiking"];

                  node(around:{radius_m},{lat},{lon})["tourism"~"viewpoint|attraction"];
                  way(around:{radius_m},{lat},{lon})["tourism"~"viewpoint|attraction"];
                  relation(around:{radius_m},{lat},{lon})["tourism"~"viewpoint|attraction"];

                  node(around:{radius_m},{lat},{lon})["natural"~"peak|wood"];
                  way(around:{radius_m},{lat},{lon})["natural"~"peak|wood"];
                  relation(around:{radius_m},{lat},{lon})["natural"~"peak|wood"];
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
                places = self.parse_places(data, lat, lon)
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
        title_panel = RoundedPanel(orientation="vertical", bg_color=COLORS["mint"], size_hint_y=None, height=dp(86))
        title_panel.add_widget(TitleLabel(text=f"{len(places)} lugares encontrados", size_hint_y=None, height=dp(34)))
        title_panel.add_widget(MutedLabel(text="Ordenados desde el más cercano al más lejano según tu GPS.", size_hint_y=None, height=dp(30)))
        self.results_content.add_widget(title_panel)
        for place in places:
            self.results_content.add_widget(PlaceCard(place=place))


class PlaceCard(RoundedPanel):
    def __init__(self, place: Place, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", bg_color=COLORS["white"], size_hint_y=None, height=dp(168), **kwargs)
        self.place = place
        self.add_widget(TitleLabel(text=place.name, size_hint_y=None, height=dp(34)))
        self.add_widget(BodyLabel(text=f"{place.kind}  ·  {place.distance_km:.1f} km", size_hint_y=None, height=dp(28)))
        self.add_widget(MutedLabel(text=f"Coordenadas: {place.lat:.5f}, {place.lon:.5f}  ·  Fuente: {place.source}", size_hint_y=None, height=dp(34)))
        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(42))
        map_btn = SmallButton(text="Ver en mapa")
        google_btn = SmallButton(text="Google Maps")
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

    def build(self) -> ScreenManager:
        Window.clearcolor = COLORS["white"]
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.sm.add_widget(HomeScreen())
        self.sm.add_widget(WeatherScreen())
        self.sm.add_widget(NearbyScreen())
        return self.sm

    def go_to(self, screen_name: str) -> None:
        if self.sm:
            self.sm.current = screen_name

    def go_home(self) -> None:
        self.go_to("home")

    def set_current_location(self, lat: float, lon: float, accuracy: Optional[float] = None) -> None:
        # V.0.1.1:
        # Evita coordenadas inválidas y saltos raros del GPS.
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            self.set_status("GPS entregó una coordenada inválida. Se ignoró.")
            return

        if accuracy is not None and accuracy > 5000:
            self.set_status(f"GPS con poca precisión ({accuracy:.0f} m). Esperando mejor señal...")
            return

        if self.has_real_gps_fix:
            jump_km = haversine_km(self.current_lat, self.current_lon, lat, lon)
            if jump_km > 80 and accuracy is not None and accuracy > 100:
                self.set_status("GPS inestable: se ignoró un salto extraño de ubicación.")
                return

        self.current_lat = lat
        self.current_lon = lon
        self.last_gps_accuracy = accuracy
        self.has_real_gps_fix = True

        for screen in self.sm.screens if self.sm else []:
            callback = getattr(screen, "on_location_update", None)
            if callable(callback):
                callback(lat, lon)

    def set_status(self, message: str) -> None:
        self.status = message
        if self.sm:
            home = self.sm.get_screen("home")
            if hasattr(home, "set_status"):
                home.set_status(message)

    def request_gps(self) -> None:
        self.has_requested_gps = True
        self.set_status("Solicitando permiso de ubicación...")
        try:
            from android.permissions import Permission, request_permissions

            request_permissions([Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION])
        except Exception:
            # En computador no existe el módulo android. Se mantiene la coordenada de prueba.
            pass

        try:
            from plyer import gps

            gps.configure(on_location=self._on_gps_location, on_status=self._on_gps_status)
            gps.start(minTime=5000, minDistance=10)
            self.gps_running = True
            self.set_status("GPS iniciado. Esperando coordenadas reales...")
        except Exception as exc:
            self.set_status(f"GPS no disponible en este entorno. Usando coordenada de prueba. Detalle: {exc}")
            self.set_current_location(DEFAULT_LAT, DEFAULT_LON)

    def _on_gps_location(self, **kwargs: Any) -> None:
        try:
            lat = float(kwargs.get("lat"))
            lon = float(kwargs.get("lon"))
            accuracy_raw = kwargs.get("accuracy")
            accuracy = float(accuracy_raw) if accuracy_raw is not None else None
            Clock.schedule_once(lambda *_: self.set_current_location(lat, lon, accuracy), 0)
        except Exception:
            pass

    def _on_gps_status(self, status_type: str, status_message: str) -> None:
        Clock.schedule_once(lambda *_: self.set_status(f"GPS: {status_type} · {status_message}"), 0)

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
        return True

    def on_stop(self) -> None:
        if self.gps_running:
            try:
                from plyer import gps

                gps.stop()
            except Exception:
                pass


if __name__ == "__main__":
    CumbreParkApp().run()
