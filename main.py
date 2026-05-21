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
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.relativelayout import RelativeLayout
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
            card.add_widget(TitleLabel(text=number, size_hint_x=None, width=dp(64), font_size="20sp"))
            grid.add_widget(card)
        content.add_widget(grid)

        tools = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["white"])
        tools.bind(minimum_height=tools.setter("height"))
        tools.add_widget(BodyLabel(text="Acciones rápidas (placeholder)", size_hint_y=None, height=dp(30)))
        tools.add_widget(SecondaryButton(text="Copiar coordenadas actuales"))
        tools.add_widget(SecondaryButton(text="Enviar ubicación a contacto"))
        content.add_widget(tools)

        back_btn = PrimaryButton(text="Volver al inicio")
        back_btn.bind(on_release=lambda *_: App.get_running_app().go_home())
        content.add_widget(back_btn)


class DownloadMapScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "download_map"

        root = BoxLayout(orientation="vertical")
        root.canvas.before.add(Color(*COLORS["white"]))
        self.add_widget(root)
        root.add_widget(Header("Descargar mapa"))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", spacing=dp(12), padding=[dp(14), dp(20), dp(14), dp(20)], size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        panel = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["soft"])
        panel.bind(minimum_height=panel.setter("height"))
        panel.add_widget(TitleLabel(text="Modo de descarga", size_hint_y=None, height=dp(34), font_size="21sp"))
        panel.add_widget(OriginModeButton(text="Modo mapa", group="map_mode", state="down"))
        panel.add_widget(OriginModeButton(text="Modo satelital", group="map_mode"))
        panel.add_widget(PrimaryButton(text="Descargar zona"))
        panel.add_widget(MutedLabel(text="La descarga real se implementará en una próxima versión.", size_hint_y=None, height=dp(36)))
        content.add_widget(panel)

        info = RoundedPanel(orientation="vertical", size_hint_y=None, bg_color=COLORS["white"])
        info.bind(minimum_height=info.setter("height"))
        info.add_widget(BodyLabel(text="Próximamente", size_hint_y=None, height=dp(30)))
        info.add_widget(MutedLabel(text="• Guardar zonas favoritas para uso offline"))
        info.add_widget(MutedLabel(text="• Administrar descargas por región"))
        info.add_widget(MutedLabel(text="• Ver estado de almacenamiento"))
        content.add_widget(info)

        back_btn = PrimaryButton(text="Volver al inicio")
        back_btn.bind(on_release=lambda *_: App.get_running_app().go_home())
        content.add_widget(back_btn)


class HomeScreen(Screen):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name = "home"
        self.status_label: Optional[Label] = None

        bg_dark = (7/255, 16/255, 24/255, 1)        # #071018
        card_dark = (16/255, 26/255, 36/255, 1)     # #101A24
        brand_blue = (17/255, 72/255, 113/255, 1)   # #114871
        sport_blue = (23/255, 106/255, 154/255, 1)  # #176A9A
        accent = (183/255, 255/255, 74/255, 1)      # #B7FF4A
        white = (1, 1, 1, 1)
        muted = (170/255, 183/255, 194/255, 1)      # #AAB7C2

        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(*bg_dark)
            self._home_bg = RoundedRectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *_: self._sync_home_bg(root), size=lambda *_: self._sync_home_bg(root))
        self.add_widget(root)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3), scroll_type=["bars", "content"])
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(14),
            padding=[dp(16), dp(40), dp(16), dp(36)],
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        def _centered_text_label(text: str, color: tuple[float, float, float, float], font_size: str, height: float, bold: bool = False) -> Label:
            label = Label(
                text=text,
                color=color,
                bold=bold,
                font_size=font_size,
                halign="center",
                valign="middle",
                size_hint_y=None,
                height=height,
            )
            label.bind(size=lambda instance, _: setattr(instance, "text_size", (instance.width, instance.height)))
            Clock.schedule_once(lambda *_: setattr(label, "text_size", (label.width, label.height)), 0)
            return label

        def _build_tappable_card(
            title: str,
            subtitle: str,
            footer: str,
            height: float,
            card_color: tuple[float, float, float, float],
            border_color: tuple[float, float, float, float],
        ) -> RelativeLayout:
            wrap = RelativeLayout(size_hint_y=None, height=height)
            card = RoundedPanel(orientation="vertical", bg_color=card_color, border_color=border_color)
            card.size_hint = (1, 1)
            card.pos_hint = {"x": 0, "y": 0}
            card.padding = [dp(14), dp(12), dp(14), dp(12)]
            card.spacing = dp(4)
            card.add_widget(_centered_text_label(title, white, "20sp", dp(32), bold=True))
            card.add_widget(_centered_text_label(subtitle, muted, "14sp", dp(24)))
            card.add_widget(_centered_text_label(footer, accent, "13sp", dp(24), bold=True))
            wrap.add_widget(card)
            return wrap

        hero = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(168), bg_color=brand_blue, border_color=sport_blue)
        hero.padding = [dp(16), dp(14), dp(16), dp(14)]
        hero.spacing = dp(8)
        hero_logo_wrap = AnchorLayout(anchor_x="center", anchor_y="center", size_hint_y=None, height=dp(46))
        hero_logo_wrap.add_widget(Image(source="assets/logo_cumbrepark.png", fit_mode="contain", size_hint=(None, None), size=(dp(46), dp(46))))
        hero.add_widget(hero_logo_wrap)
        hero.add_widget(_centered_text_label("CumbrePark", white, "32sp", dp(44), bold=True))
        hero.add_widget(_centered_text_label("Explora. Registra. Comparte.", muted, "15sp", dp(24)))
        content.add_widget(hero)

        lead = RoundedPanel(orientation="vertical", size_hint_y=None, height=dp(150), bg_color=card_dark, border_color=sport_blue)
        lead.padding = [dp(16), dp(16), dp(16), dp(16)]
        lead.spacing = dp(8)
        lead.add_widget(_centered_text_label("Tu próxima ruta empieza acá", white, "24sp", dp(40), bold=True))
        lead.add_widget(_centered_text_label("Planifica, registra y comparte tus aventuras outdoor.", muted, "15sp", dp(44)))
        content.add_widget(lead)

        quick_actions = GridLayout(cols=3, spacing=dp(10), size_hint_y=None, height=dp(114))
        for action in ("Mapa + clima", "Emergencia", "Registrar actividad"):
            quick_actions.add_widget(
                _build_tappable_card(
                    title=action,
                    subtitle="Acción rápida",
                    footer="Disponible pronto",
                    height=dp(114),
                    card_color=sport_blue,
                    border_color=sport_blue,
                )
            )
        content.add_widget(quick_actions)

        modules = [
            ("Explorar", "Mapas, clima y lugares cercanos"),
            ("Seguridad", "Emergencia, ubicación y avisos"),
            ("Actividad", "Rutas, distancia, desnivel y tiempo"),
            ("Comunidad", "Ranking, marketplace y grupos"),
            ("Perfil", "Preferencias, nivel y experiencia"),
        ]

        for title, subtitle in modules:
            content.add_widget(
                _build_tappable_card(
                    title=title,
                    subtitle=subtitle,
                    footer="Ver módulo",
                    height=dp(112),
                    card_color=card_dark,
                    border_color=(0.12, 0.20, 0.27, 1),
                )
            )

        self.status_label = Label(
            text="Inicio visual estable V.0.2.1. Las funciones avanzadas están en diseño.",
            color=accent,
            font_size="13sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
            text_size=(0, 0),
        )
        self.status_label.bind(size=lambda instance, _: setattr(instance, "text_size", (instance.width, instance.height)))
        Clock.schedule_once(lambda *_: setattr(self.status_label, "text_size", (self.status_label.width, self.status_label.height)), 0)
        content.add_widget(self.status_label)

    def _sync_home_bg(self, root: BoxLayout) -> None:
        self._home_bg.pos = root.pos
        self._home_bg.size = root.size

    def show_feature_disabled(self, name: str) -> None:
        if self.status_label:
            self.status_label.text = f"{name}: Función en diseño"



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

        self.origin_map = MapView(lat=DEFAULT_LAT, lon=DEFAULT_LON, zoom=12, size_hint_y=None, height=dp(220))
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
        try:
            lat, lon = mapview.get_latlon_at(*touch.pos)
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

    def build(self) -> ScreenManager:
        Window.clearcolor = COLORS["white"]
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.sm.add_widget(HomeScreen())
        self.sm.add_widget(WeatherScreen())
        self.sm.add_widget(NearbyScreen())
        self.sm.add_widget(DownloadMapScreen())
        self.sm.add_widget(EmergencyScreen())
        self.sm.add_widget(PlaceholderScreen(name="offline_maps", title="Mapas sin internet", features=["Guardar mapas para rutas frecuentes", "Navegación básica sin señal", "Sincronización automática al recuperar red"]))
        self.sm.add_widget(PlaceholderScreen(name="live_location", title="Compartir ubicación en vivo", features=["Compartir ubicación por tiempo limitado", "Enlace seguro para contactos", "Estado de batería y señal"]))
        self.sm.add_widget(PlaceholderScreen(name="emergency_contacts", title="Contactos de emergencia", features=["Agregar contactos prioritarios", "Atajos para llamadas rápidas", "Notificación automática con ubicación"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="route_alerts", title="Estado de ruta / avisos", features=["Alertas por clima extremo", "Avisos de cierre temporal", "Historial de incidentes por zona"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="register_activity", title="Registrar actividad", features=["Iniciar y pausar actividad", "Resumen de distancia y tiempo", "Exportar recorrido"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="my_routes", title="Mis rutas", features=["Rutas guardadas", "Notas y fotos por ruta", "Recomendaciones de dificultad"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="sports_history", title="Historial deportivo", features=["Sesiones recientes", "Evolución semanal", "Comparativa mensual"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="monthly_ranking", title="Ranking mensual", features=["Top por distancia", "Top por desnivel", "Retos del mes"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="community", title="Comunidad", features=["Feed de publicaciones", "Clubes y grupos", "Eventos cercanos"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="marketplace", title="Marketplace deportivo", features=["Compra y venta de equipo", "Filtros por deporte", "Valoraciones entre usuarios"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="instagram_share", title="Compartir en Instagram", features=["Plantillas para stories", "Etiquetas automáticas", "Resumen visual de actividad"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="spotify_connect", title="Conectar Spotify", features=["Playlists para entrenamiento", "Control básico desde la app", "Música sugerida por ritmo"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="create_profile", title="Crear perfil", features=["Datos personales outdoor", "Avatar y bio", "Objetivos deportivos"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="sport_preferences", title="Preferencias deportivas", features=["Deportes favoritos", "Nivel actual", "Frecuencia semanal"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="difficulty_level", title="Nivel y dificultad sugerida", features=["Evaluación inicial", "Sugerencias por terreno", "Progresión personalizada"], note="Próximamente"))
        self.sm.add_widget(PlaceholderScreen(name="settings_screen", title="Configuración", features=["Notificaciones", "Unidades de medida", "Privacidad y permisos"], note="Próximamente"))
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
