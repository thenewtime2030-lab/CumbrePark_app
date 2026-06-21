# -*- coding: utf-8 -*-
"""
PerkVia99 - main.py
Base Android/Kivy offline-first para combustibles, promociones y códigos.

No contiene claves API, no inventa precios reales y no publica descuentos no verificados.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, DictProperty, ListProperty, StringProperty
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

try:
    from kivy_garden.mapview import MapMarker, MapView
except Exception:  # pragma: no cover - fallback for desktop or missing garden package
    MapView = None
    MapMarker = None

try:
    from plyer import gps
except Exception:  # pragma: no cover - fallback for desktop
    gps = None


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"
ICON_PATH = ASSETS_DIR / "icon.png"


DEFAULT_APP_CONFIG: Dict[str, Any] = {
    "app_name": "PerkVia99",
    "version": "0.1.0",
    "country": "CL",
    "currency": "CLP",
    "language": "es-CL",
    "default_map_center": {"latitude": -33.4489, "longitude": -70.6693, "zoom": 12},
    "data_freshness": {"fuel_prices_hours": 24, "promotions_hours": 24, "codes_hours": 12},
    "features": {"fuel_map": True, "promotions": True, "delivery_codes": True, "ride_codes": True},
    "privacy": {"background_location": False, "analytics": False, "personalized_ads_default": False},
}

DEFAULT_THEME: Dict[str, Any] = {
    "colors": {
        "primary": "#6D20D5",
        "primary_dark": "#4E13A8",
        "secondary": "#FF7A14",
        "background": "#F8F6FC",
        "surface": "#FFFFFF",
        "text": "#20242C",
        "text_muted": "#68707D",
        "border": "#E4DDF0",
        "success": "#17B890",
        "warning": "#FF7A14",
        "danger": "#D92D20",
    }
}


@dataclass
class FuelStation:
    id: str
    name: str
    brand: str
    address: str
    latitude: float
    longitude: float
    distance_km: Optional[float] = None
    prices: Dict[str, int] = field(default_factory=dict)
    updated_at: Optional[str] = None
    source_name: str = "Sin proveedor configurado"
    source_url: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> Optional["FuelStation"]:
        try:
            station_id = str(raw.get("id") or "").strip()
            name = str(raw.get("name") or "").strip()
            lat = float(raw.get("latitude"))
            lon = float(raw.get("longitude"))
            if not station_id or not name:
                return None
            prices = raw.get("prices") if isinstance(raw.get("prices"), dict) else {}
            clean_prices: Dict[str, int] = {}
            for key, value in prices.items():
                try:
                    numeric = int(value)
                    if numeric > 0:
                        clean_prices[str(key)] = numeric
                except Exception:
                    continue
            distance = raw.get("distance_km")
            return cls(
                id=station_id,
                name=name,
                brand=str(raw.get("brand") or "").strip(),
                address=str(raw.get("address") or "").strip(),
                latitude=lat,
                longitude=lon,
                distance_km=float(distance) if distance is not None else None,
                prices=clean_prices,
                updated_at=raw.get("updated_at"),
                source_name=str(raw.get("source_name") or "Sin proveedor configurado"),
                source_url=raw.get("source_url"),
            )
        except Exception:
            return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "distance_km": self.distance_km,
            "prices": self.prices,
            "updated_at": self.updated_at,
            "source_name": self.source_name,
            "source_url": self.source_url,
        }


@dataclass
class Promotion:
    id: str
    category: str
    brand: str
    title: str
    description: str
    status: str = "unknown"
    benefit_type: Optional[str] = None
    benefit_value: Optional[float] = None
    code: Optional[str] = None
    expires_at: Optional[str] = None
    verified_at: Optional[str] = None
    source_url: Optional[str] = None
    terms: List[str] = field(default_factory=list)
    verification_score: int = 0
    verification_label: str = "Sin verificar"
    success_reports: int = 0
    failure_reports: int = 0

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> Optional["Promotion"]:
        try:
            promo_id = str(raw.get("id") or "").strip()
            title = str(raw.get("title") or "").strip()
            category = str(raw.get("category") or "").strip()
            if not promo_id or not title or not category:
                return None
            terms = raw.get("terms") if isinstance(raw.get("terms"), list) else []
            return cls(
                id=promo_id,
                category=category,
                brand=str(raw.get("brand") or "").strip(),
                title=title,
                description=str(raw.get("description") or "").strip(),
                status=str(raw.get("status") or "unknown"),
                benefit_type=raw.get("benefit_type"),
                benefit_value=raw.get("benefit_value"),
                code=raw.get("code"),
                expires_at=raw.get("expires_at"),
                verified_at=raw.get("verified_at"),
                source_url=raw.get("source_url"),
                terms=[str(item) for item in terms],
                verification_score=max(0, min(100, int(raw.get("verification_score") or 0))),
                verification_label=str(raw.get("verification_label") or "Sin verificar"),
                success_reports=max(0, int(raw.get("success_reports") or 0)),
                failure_reports=max(0, int(raw.get("failure_reports") or 0)),
            )
        except Exception:
            return None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
    except Exception:
        pass


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def cache_is_fresh(cache_payload: Dict[str, Any], hours: int) -> bool:
    created_at = parse_iso(cache_payload.get("cached_at"))
    if not created_at:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created_at <= timedelta(hours=hours)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def hex_to_rgba(value: str, alpha: float = 1.0) -> Tuple[float, float, float, float]:
    clean = str(value or "#000000").strip().lstrip("#")
    if len(clean) != 6:
        clean = "000000"
    return tuple(int(clean[i : i + 2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


class HomeScreen(Screen):
    pass


class FuelMapScreen(Screen):
    gps_requested = BooleanProperty(False)
    status_text = StringProperty("Esperando ubicación y precios actualizados")

    def on_pre_enter(self, *args: Any) -> None:
        app = App.get_running_app()
        app.ensure_dirs()
        self._build_map_once()
        self._set_status("Solicitando ubicación solo para buscar bencineras cercanas…")
        if not self.gps_requested:
            self.gps_requested = True
            app.request_location_once()
        else:
            app.refresh_fuel_screen()

    def _build_map_once(self) -> None:
        app = App.get_running_app()
        container = self.ids.get("map_container")
        if not container or getattr(self, "_map_ready", False):
            return
        container.clear_widgets()
        center = app.default_center
        if MapView is not None:
            app.map_view = MapView(
                zoom=int(center.get("zoom", 12)),
                lat=float(center.get("latitude", -33.4489)),
                lon=float(center.get("longitude", -70.6693)),
                size_hint_y=0.68,
            )
            container.add_widget(app.map_view)
        else:
            container.add_widget(
                Label(
                    text="Mapa no disponible en este entorno. En Android usa OpenStreetMap vía kivy_garden.mapview.",
                    size_hint_y=0.34,
                    text_size=(None, None),
                    color=(0.41, 0.45, 0.44, 1),
                )
            )
        self.station_list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=dp(12))
        self.station_list.bind(minimum_height=self.station_list.setter("height"))
        scroll = ScrollView(do_scroll_x=False, size_hint_y=0.32)
        scroll.add_widget(self.station_list)
        container.add_widget(scroll)
        self._map_ready = True

    def _set_status(self, text: str) -> None:
        self.status_text = text
        if "fuel_status" in self.ids:
            self.ids.fuel_status.text = text


class OffersScreen(Screen):
    selected_category = StringProperty("delivery")

    def on_pre_enter(self, *args: Any) -> None:
        app = App.get_running_app()
        app.populate_offers_screen(self.selected_category)


class SimulatorScreen(Screen):
    result_text = StringProperty("Completa los datos para estimar tu ahorro.")

    def calculate(self) -> None:
        App.get_running_app().calculate_fuel_saving(self)


class PerkVia99App(App):
    title = "PerkVia99"
    icon = str(ICON_PATH)
    logo_path = StringProperty(str(LOGO_PATH))
    icon_path = StringProperty(str(ICON_PATH))
    config_data = DictProperty({})
    theme_data = DictProperty({})
    fuel_types = ListProperty([])
    service_categories = ListProperty([])
    selected_category = StringProperty("delivery")
    selected_fuel = StringProperty("gasoline_93")

    map_view = None
    current_location: Optional[Tuple[float, float]] = None
    location_source = "fallback"
    gps_timeout_event = None
    cache_dir: Path
    runtime_dir: Path

    def build(self):
        self.ensure_dirs()
        self.load_static_data()
        root = Builder.load_file(str(BASE_DIR / "app.kv"))
        Clock.schedule_once(lambda _dt: self.apply_branding(root), 0)
        return root

    @property
    def default_center(self) -> Dict[str, Any]:
        return self.config_data.get("default_map_center", DEFAULT_APP_CONFIG["default_map_center"])

    def ensure_dirs(self) -> None:
        # En Android, los archivos incluidos en el APK son de solo lectura.
        # Los datos generados deben vivir en el directorio privado de la app.
        writable_data_dir = Path(self.user_data_dir) / "data"
        self.cache_dir = writable_data_dir / "cache"
        self.runtime_dir = writable_data_dir / "runtime"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def load_static_data(self) -> None:
        self.config_data = read_json(CONFIG_DIR / "app.json", DEFAULT_APP_CONFIG)
        if not isinstance(self.config_data, dict):
            self.config_data = dict(DEFAULT_APP_CONFIG)
        self.config_data["app_name"] = "PerkVia99"

        loaded_theme = read_json(CONFIG_DIR / "theme.json", {})
        loaded_colors = loaded_theme.get("colors", {}) if isinstance(loaded_theme, dict) else {}
        # La identidad PerkVia99 prevalece aunque el theme.json antiguo siga en el proyecto.
        self.theme_data = {
            **(loaded_theme if isinstance(loaded_theme, dict) else {}),
            "colors": {**loaded_colors, **DEFAULT_THEME["colors"]},
        }
        self.fuel_types = read_json(DATA_DIR / "fuel_types.json", [])
        self.service_categories = read_json(DATA_DIR / "service_categories.json", [])

    def apply_branding(self, root: Any) -> None:
        """Actualiza identidad y TextInput sin alterar la estructura de app.kv."""
        if root is None:
            return
        for widget in [root, *list(root.walk(restrict=True))]:
            if hasattr(widget, "text") and isinstance(widget.text, str):
                widget.text = widget.text.replace("RutaAhorro", "PerkVia99").replace(
                    "Ruta Ahorro", "PerkVia99"
                )

            if isinstance(widget, Image):
                source_name = Path(widget.source or "").name.lower()
                if "logo" in source_name and LOGO_PATH.exists():
                    widget.source = str(LOGO_PATH)

            if isinstance(widget, TextInput):
                widget.foreground_color = hex_to_rgba("#20242C")
                widget.cursor_color = hex_to_rgba("#6D20D5")
                widget.hint_text_color = hex_to_rgba("#68707D", 0.78)
                widget.background_color = hex_to_rgba("#FFFFFF")
                widget.disabled_foreground_color = hex_to_rgba("#68707D")

    def navigate(self, screen_name: str) -> None:
        if self.root and screen_name in self.root.screen_names:
            current_index = self.root.screen_names.index(self.root.current)
            next_index = self.root.screen_names.index(screen_name)
            self.root.transition.direction = "left" if next_index >= current_index else "right"
            self.root.current = screen_name

    def select_fuel(self, fuel_id: str) -> None:
        valid_ids = {
            item.get("id") for item in self.fuel_types if isinstance(item, dict) and item.get("active", True)
        }
        if fuel_id not in valid_ids:
            return
        self.selected_fuel = fuel_id
        if self.root and self.root.current == "fuel_map":
            self.refresh_fuel_screen()

    def open_category(self, category_id: str) -> None:
        self.selected_category = category_id
        screen = self.root.get_screen("offers") if self.root else None
        if screen:
            screen.selected_category = category_id
        self.navigate("offers")

    def open_simulator(
        self,
        price_per_liter: Optional[int] = None,
        discount_per_liter: Optional[int] = None,
    ) -> None:
        if self.root:
            screen: SimulatorScreen = self.root.get_screen("simulator")
            if price_per_liter is not None:
                screen.ids.price_input.text = str(price_per_liter)
            if discount_per_liter is not None:
                screen.ids.discount_input.text = str(discount_per_liter)
        self.navigate("simulator")

    def calculate_fuel_saving(self, screen: SimulatorScreen) -> None:
        try:
            price = max(0.0, float(screen.ids.price_input.text.replace(",", ".")))
            liters = max(0.0, float(screen.ids.liters_input.text.replace(",", ".")))
            discount_per_liter = max(0.0, float(screen.ids.discount_input.text.replace(",", ".") or 0))
            cap = max(0.0, float(screen.ids.cap_input.text.replace(",", ".") or 0))
        except (TypeError, ValueError):
            screen.result_text = "Revisa los valores ingresados. Usa solo números."
            return
        if price <= 0 or liters <= 0:
            screen.result_text = "Ingresa un precio y una cantidad de litros mayor que cero."
            return
        subtotal = price * liters
        raw_discount = discount_per_liter * liters
        saving = min(raw_discount, cap) if cap > 0 else raw_discount
        saving = min(saving, subtotal)
        final_total = subtotal - saving
        effective_price = final_total / liters
        screen.result_text = (
            f"TOTAL NORMAL  ${subtotal:,.0f}\n"
            f"AHORRO ESTIMADO  −${saving:,.0f}\n"
            f"TOTAL FINAL  ${final_total:,.0f}\n"
            f"PRECIO EFECTIVO  ${effective_price:,.0f}/L"
        ).replace(",", ".")

    def request_location_once(self) -> None:
        self.current_location = None
        self.location_source = "fallback"
        if gps is None:
            self.use_default_location("GPS no disponible en este entorno. Usando Santiago como referencia.")
            return

        # Declarar permisos en buildozer.spec no basta desde Android 6:
        # también hay que solicitarlos cuando el usuario abre el mapa.
        if platform == "android":
            try:
                from android.permissions import Permission, check_permission, request_permissions

                permissions = [Permission.ACCESS_COARSE_LOCATION, Permission.ACCESS_FINE_LOCATION]
                if all(check_permission(permission) for permission in permissions):
                    self._start_gps()
                else:
                    request_permissions(permissions, self._on_location_permissions)
                return
            except Exception:
                self.use_default_location(
                    "No fue posible solicitar el permiso de ubicación. Usando Santiago como referencia."
                )
                return

        self._start_gps()

    def _on_location_permissions(self, _permissions: List[str], grants: List[bool]) -> None:
        granted = bool(grants) and all(grants)
        Clock.schedule_once(lambda _dt: self._finish_location_permission(granted), 0)

    def _finish_location_permission(self, granted: bool) -> None:
        if granted:
            self._start_gps()
        else:
            self.use_default_location("Permiso de ubicación rechazado. Usando Santiago como referencia.")

    def _start_gps(self) -> None:
        try:
            gps.configure(on_location=self.on_location, on_status=self.on_gps_status)
            gps.start(minTime=1000, minDistance=0)
            if self.gps_timeout_event:
                self.gps_timeout_event.cancel()
            self.gps_timeout_event = Clock.schedule_once(
                lambda _dt: self.use_default_location("No se recibió ubicación a tiempo. Usando Santiago como referencia."),
                8,
            )
        except Exception:
            self.use_default_location("Permiso de ubicación rechazado o no disponible. Usando Santiago como referencia.")

    def on_location(self, **kwargs: Any) -> None:
        try:
            lat = float(kwargs.get("lat"))
            lon = float(kwargs.get("lon"))
            # Plyer puede llamar desde otro hilo; la UI se actualiza con Clock.
            Clock.schedule_once(lambda _dt: self._apply_gps_location(lat, lon), 0)
        except Exception:
            Clock.schedule_once(
                lambda _dt: self.use_default_location("Ubicación inválida. Usando Santiago como referencia."), 0
            )

    def _apply_gps_location(self, lat: float, lon: float) -> None:
        self.current_location = (lat, lon)
        self.location_source = "gps"
        if self.gps_timeout_event:
            self.gps_timeout_event.cancel()
            self.gps_timeout_event = None
        try:
            if gps is not None:
                gps.stop()
        except Exception:
            pass
        self.refresh_fuel_screen()

    def on_gps_status(self, status_type: str, status_message: str) -> None:
        write_json(
            self.runtime_dir / "last_gps_status.json",
            {"status_type": status_type, "status_message": status_message, "updated_at": now_iso()},
        )

    def use_default_location(self, message: str) -> None:
        try:
            if gps is not None:
                gps.stop()
        except Exception:
            pass
        center = self.default_center
        self.current_location = (float(center.get("latitude", -33.4489)), float(center.get("longitude", -70.6693)))
        self.location_source = "fallback"
        self.refresh_fuel_screen(message)

    def refresh_fuel_screen(self, prefix_message: Optional[str] = None) -> None:
        if not self.root:
            return
        screen: FuelMapScreen = self.root.get_screen("fuel_map")
        lat, lon = self.current_location or (
            float(self.default_center.get("latitude", -33.4489)),
            float(self.default_center.get("longitude", -70.6693)),
        )
        if self.map_view is not None:
            self.map_view.center_on(lat, lon)
        stations, meta = self.load_fuel_stations(lat, lon)
        self.render_station_results(screen, stations)
        count = len(stations)
        source = meta.get("source", "sin proveedor")
        freshness = meta.get("freshness", "offline")
        if count:
            message = f"{count} estación(es). Fuente: {source}. Estado: {freshness}."
        else:
            message = "Sin precios reales: falta conectar proveedor público o caché local."
        if prefix_message:
            message = f"{prefix_message} {message}"
        screen._set_status(message)

    def load_fuel_stations(self, lat: float, lon: float) -> Tuple[List[FuelStation], Dict[str, Any]]:
        freshness_hours = int(self.config_data.get("data_freshness", {}).get("fuel_prices_hours", 24))
        cache_path = self.cache_dir / "fuel_stations.json"
        cached = read_json(cache_path, {})
        if isinstance(cached, dict):
            stations = self._normalize_stations(cached.get("stations", []), lat, lon)
            if stations and cache_is_fresh(cached, freshness_hours):
                return stations, {"source": cached.get("source", "cache"), "freshness": "cache vigente"}
            if stations:
                # Offline-first: conservar datos vencidos y advertirlo, en vez de borrarlos.
                return stations, {"source": cached.get("source", "cache"), "freshness": "cache antigua"}

        # Stub deliberado: aquí se conectará CNE/u otro proveedor gratuito configurado.
        # No se inventan precios ni estaciones reales.
        if not isinstance(cached, dict) or "stations" not in cached:
            payload = {"cached_at": now_iso(), "source": "stub/offline", "stations": []}
            write_json(cache_path, payload)
        return [], {"source": "stub/offline", "freshness": "sin datos publicados"}

    def _normalize_stations(self, raw_stations: Any, lat: float, lon: float) -> List[FuelStation]:
        stations: List[FuelStation] = []
        if not isinstance(raw_stations, list):
            return stations
        for raw in raw_stations:
            if not isinstance(raw, dict):
                continue
            station = FuelStation.from_dict(raw)
            if not station:
                continue
            station.distance_km = round(haversine_km(lat, lon, station.latitude, station.longitude), 2)
            stations.append(station)
        return sorted(stations, key=lambda item: item.distance_km if item.distance_km is not None else 9999)

    def render_station_results(self, screen: FuelMapScreen, stations: List[FuelStation]) -> None:
        station_list = getattr(screen, "station_list", None)
        if station_list is None:
            return
        station_list.clear_widgets()
        if self.map_view is not None and MapMarker is not None:
            try:
                for child in list(getattr(self.map_view, "children", [])):
                    if isinstance(child, MapMarker):
                        self.map_view.remove_widget(child)
            except Exception:
                pass
        if not stations:
            station_list.add_widget(
                self.info_label(
                    "Todavía no hay estaciones con precios reales en caché. La app está preparada para CNE/proveedor gratuito y modo offline."
                )
            )
            station_list.add_widget(self.info_label("Sugerencia: agregar búsqueda manual por comuna en la siguiente iteración."))
            return
        stations = sorted(
            stations,
            key=lambda station: (
                self.selected_fuel not in station.prices,
                station.prices.get(self.selected_fuel, 10**9),
                station.distance_km if station.distance_km is not None else 10**9,
            ),
        )
        for station in stations:
            if self.map_view is not None and MapMarker is not None:
                try:
                    self.map_view.add_marker(MapMarker(lat=station.latitude, lon=station.longitude))
                except Exception:
                    pass
            station_list.add_widget(self.station_card(station))

    def station_card(self, station: FuelStation) -> BoxLayout:
        box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(14), spacing=dp(6))
        label_by_id = {item.get("id"): item.get("label") for item in self.fuel_types if isinstance(item, dict)}
        fuel_label = label_by_id.get(self.selected_fuel, self.selected_fuel)
        selected_price = station.prices.get(self.selected_fuel)
        price_text = (
            f"[size=25sp][b]${selected_price:,}/L[/b][/size]".replace(",", ".")
            if selected_price
            else "[b]Precio no informado[/b]"
        )
        distance = f" · {station.distance_km:.1f} km" if station.distance_km is not None else ""
        updated = station.updated_at or "sin fecha"
        text = (
            f"[b]{station.name}[/b]{distance}\n"
            f"{station.brand} · {station.address}\n"
            f"{fuel_label}  {price_text}\n"
            f"Fuente: {station.source_name} · Actualizado: {updated}"
        )
        label = Label(markup=True, text=text, color=(0.09, 0.13, 0.12, 1), text_size=(0, None), halign="left")
        label.bind(width=lambda instance, width: setattr(instance, "text_size", (width, None)))
        label.bind(texture_size=lambda instance, size: setattr(box, "height", size[1] + dp(24)))
        box.add_widget(label)
        return box

    def populate_offers_screen(self, category_id: str) -> None:
        if not self.root:
            return
        screen: OffersScreen = self.root.get_screen("offers")
        categories = {item.get("id"): item for item in self.service_categories if isinstance(item, dict)}
        category = categories.get(category_id, {"label": "Promociones", "brands": []})
        title = category.get("label", "Promociones y códigos")
        if "offers_title" in screen.ids:
            screen.ids.offers_title.text = f"{title}: descuentos y códigos"
        offer_list = screen.ids.get("offers_list")
        if not offer_list:
            return
        offer_list.clear_widgets()
        promotions = self.load_promotions(category_id)
        brands = category.get("brands", []) if isinstance(category.get("brands"), list) else []
        if brands:
            offer_list.add_widget(self.info_label("Marcas preparadas: " + ", ".join(brands)))
        if promotions:
            for promo in promotions:
                offer_list.add_widget(self.promotion_card(promo))
        else:
            offer_list.add_widget(
                self.info_label(
                    "No hay códigos verificados para mostrar. La app no inventa promociones: cada código debe tener fuente, fecha y condiciones."
                )
            )
        if "offers_status" in screen.ids:
            screen.ids.offers_status.text = "Modo gratis/offline. Los códigos reales deben verificarse antes de publicarse."

    def load_promotions(self, category_id: str) -> List[Promotion]:
        raw_items = read_json(DATA_DIR / "promotions.sample.json", [])
        promos: List[Promotion] = []
        if not isinstance(raw_items, list):
            return promos
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            promo = Promotion.from_dict(raw)
            if not promo or promo.category != category_id:
                continue
            # Un ejemplo, un aporte aislado o un registro sin respaldo nunca
            # se publica automáticamente como beneficio utilizable.
            if promo.status == "example_not_published":
                continue
            if promo.status not in {"official_verified", "community_verified", "probably_active"}:
                continue
            if promo.verification_score < 55:
                continue
            promos.append(promo)
        return sorted(promos, key=lambda item: item.verification_score, reverse=True)

    def promotion_card(self, promo: Promotion) -> BoxLayout:
        box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(10), spacing=dp(4))
        status = f"{promo.verification_label.upper()} · {promo.verification_score}% CONFIANZA"
        code = f"Código: {promo.code}" if promo.code else "Sin código visible"
        verified = promo.verified_at or "sin fecha de verificación"
        terms = "\n".join(f"• {item}" for item in promo.terms) if promo.terms else "Sin condiciones cargadas"
        text = (
            f"[b]{promo.brand or 'Marca'} · {status}[/b]\n"
            f"{promo.title}\n{promo.description}\n"
            f"{code}\nVigencia: {promo.expires_at or 'no informada'} · Verificado: {verified}\n{terms}"
        )
        label = Label(markup=True, text=text, color=(0.09, 0.13, 0.12, 1), text_size=(0, None), halign="left")
        label.bind(width=lambda instance, width: setattr(instance, "text_size", (width, None)))
        label.bind(texture_size=lambda instance, size: setattr(box, "height", size[1] + dp(24)))
        box.add_widget(label)
        return box

    def info_label(self, text: str) -> Label:
        label = Label(
            text=text,
            size_hint_y=None,
            color=(0.41, 0.45, 0.44, 1),
            text_size=(0, None),
            halign="left",
            valign="top",
            padding=(0, dp(6)),
        )
        label.bind(width=lambda instance, width: setattr(instance, "text_size", (width, None)))
        label.bind(texture_size=lambda instance, size: setattr(instance, "height", size[1] + dp(16)))
        return label


if __name__ == "__main__":
    PerkVia99App().run()
