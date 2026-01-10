import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import random

from .config import AutoModeConfig
from .alert_monitor import AlertMonitor
from .telegram_monitor import TelegramMonitor
from .llm_processor import LLMProcessor, ThreatInfo
from .geocoder import get_geocoder

@dataclass
class AutoThreat:
    id: int
    type: str  # "drone" or "missile"
    lat: float
    lng: float
    angle: float
    count: int
    region: str
    trajectoryLength: float = 50  # km - short trajectory line
    source_msg_id: Optional[int] = None
    source_channel: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

class AutoController:
    """
    Main controller for AUTO mode.
    Coordinates alert monitoring, telegram monitoring, and LLM processing.
    """
    
    def __init__(self, config: AutoModeConfig, 
                 on_threat_add: Optional[Callable] = None,
                 on_threat_remove: Optional[Callable] = None,
                 on_threat_update: Optional[Callable] = None,
                 on_state_change: Optional[Callable] = None):
        self.config = config
        self.on_threat_add = on_threat_add
        self.on_threat_remove = on_threat_remove
        self.on_threat_update = on_threat_update
        self.on_state_change = on_state_change
        
        # Components
        self.alert_monitor = AlertMonitor(on_alert_change=self._on_alert_change)
        self.telegram_monitor: Optional[TelegramMonitor] = None
        self.llm = LLMProcessor(config.openrouter_api_key, config.llm_model)
        
        # State
        self.threats: Dict[int, AutoThreat] = {}
        self.active_alerts: set = set()
        self.is_running = False
        self._next_threat_id = 1
        self._tasks: List[asyncio.Task] = []
        
        # Region coordinates (approximate centers)
        self.region_coords = {
            "Київська": (50.45, 30.52),
            "Харківська": (49.99, 36.23),
            "Одеська": (46.48, 30.73),
            "Дніпропетровська": (48.46, 35.04),
            "Львівська": (49.84, 24.03),
            "Запорізька": (47.84, 35.14),
            "Донецька": (48.00, 37.80),
            "Луганська": (48.57, 39.31),
            "Миколаївська": (46.97, 32.00),
            "Полтавська": (49.59, 34.55),
            "Чернігівська": (51.49, 31.29),
            "Черкаська": (49.44, 32.06),
            "Сумська": (50.91, 34.80),
            "Херсонська": (46.64, 32.62),
            "Вінницька": (49.23, 28.47),
            "Житомирська": (50.25, 28.66),
            "Хмельницька": (49.42, 27.00),
            "Рівненська": (50.62, 26.25),
            "Івано-Франківська": (48.92, 24.71),
            "Тернопільська": (49.55, 25.59),
            "Волинська": (50.75, 25.34),
            "Закарпатська": (48.62, 22.29),
            "Чернівецька": (48.29, 25.94),
            "Кіровоградська": (48.51, 32.26),
        }
        
        # City coordinates for precise placement
        self.city_coords = {
            # Major cities
            "київ": (50.45, 30.52),
            "киев": (50.45, 30.52),
            "харків": (49.99, 36.23),
            "харьков": (49.99, 36.23),
            "одеса": (46.48, 30.73),
            "одесса": (46.48, 30.73),
            "дніпро": (48.46, 35.04),
            "днепр": (48.46, 35.04),
            "львів": (49.84, 24.03),
            "львов": (49.84, 24.03),
            "запоріжжя": (47.84, 35.14),
            "запорожье": (47.84, 35.14),
            "миколаїв": (46.97, 32.00),
            "николаев": (46.97, 32.00),
            "полтава": (49.59, 34.55),
            "чернігів": (51.49, 31.29),
            "чернигов": (51.49, 31.29),
            "черкаси": (49.44, 32.06),
            "черкассы": (49.44, 32.06),
            "суми": (50.91, 34.80),
            "сумы": (50.91, 34.80),
            "херсон": (46.64, 32.62),
            "вінниця": (49.23, 28.47),
            "винница": (49.23, 28.47),
            "житомир": (50.25, 28.66),
            "хмельницький": (49.42, 27.00),
            "хмельницкий": (49.42, 27.00),
            "рівне": (50.62, 26.25),
            "ровно": (50.62, 26.25),
            "івано-франківськ": (48.92, 24.71),
            "ивано-франковск": (48.92, 24.71),
            "тернопіль": (49.55, 25.59),
            "тернополь": (49.55, 25.59),
            "луцьк": (50.75, 25.34),
            "луцк": (50.75, 25.34),
            "ужгород": (48.62, 22.29),
            "чернівці": (48.29, 25.94),
            "черновцы": (48.29, 25.94),
            "кропивницький": (48.51, 32.26),
            "кировоград": (48.51, 32.26),
            # Other important cities
            "бровари": (50.51, 30.79),
            "бровары": (50.51, 30.79),
            "біла церква": (49.80, 30.12),
            "белая церковь": (49.80, 30.12),
            "маріуполь": (47.10, 37.55),
            "мариуполь": (47.10, 37.55),
            "краматорськ": (48.72, 37.56),
            "краматорск": (48.72, 37.56),
            "кременчук": (49.07, 33.42),
            "кременчуг": (49.07, 33.42),
            "умань": (48.75, 30.22),
            "павлоград": (48.53, 35.87),
            "кривий ріг": (47.91, 33.39),
            "кривой рог": (47.91, 33.39),
            "шостка": (51.86, 33.47),
            "конотоп": (51.24, 33.20),
            "ніжин": (51.05, 31.89),
            "нежин": (51.05, 31.89),
            "прилуки": (50.59, 32.39),
            "борисполь": (50.35, 30.95),
            "бориспіль": (50.35, 30.95),
            "фастів": (50.08, 29.92),
            "фастов": (50.08, 29.92),
            "васильків": (50.18, 30.32),
            "васильков": (50.18, 30.32),
            "ізмаїл": (45.35, 28.84),
            "измаил": (45.35, 28.84),
            "мелітополь": (46.84, 35.37),
            "мелитополь": (46.84, 35.37),
            "бердянськ": (46.76, 36.78),
            "бердянск": (46.76, 36.78),
            "енергодар": (47.50, 34.66),
            "энергодар": (47.50, 34.66),
            "слов'янськ": (48.85, 37.62),
            "славянск": (48.85, 37.62),
            "покровськ": (48.28, 37.18),
            "покровск": (48.28, 37.18),
        }
    
    async def start(self):
        """Start AUTO mode"""
        if self.is_running:
            print("[AutoController] Already running")
            return
        
        self.is_running = True
        print("[AutoController] Starting AUTO mode...")
        
        # Start alert monitoring (always runs to know which regions have alerts)
        alert_task = asyncio.create_task(
            self.alert_monitor.start(self.config.alert_poll_interval)
        )
        self._tasks.append(alert_task)
        
        # Start Telegram monitoring if credentials available
        if self.config.api_id and self.config.api_hash:
            self.telegram_monitor = TelegramMonitor(
                self.config.api_id,
                self.config.api_hash,
                on_message=self._on_telegram_message,
                on_reply=self._on_telegram_reply
            )
            
            channels = self.config.get_channels_to_monitor()
            if channels:
                tg_task = asyncio.create_task(
                    self.telegram_monitor.start(channels)
                )
                self._tasks.append(tg_task)
        else:
            print("[AutoController] Telegram credentials not configured, skipping TG monitoring")
        
        # Start TTL cleanup task
        ttl_task = asyncio.create_task(self._ttl_cleanup_loop())
        self._tasks.append(ttl_task)
        
        if self.on_state_change:
            await self.on_state_change({"status": "running", "test_mode": self.config.test_mode})
    
    async def stop(self):
        """Stop AUTO mode"""
        if not self.is_running:
            return
        
        self.is_running = False
        print("[AutoController] Stopping AUTO mode...")
        
        self.alert_monitor.stop()
        
        if self.telegram_monitor:
            await self.telegram_monitor.stop()
        
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        
        if self.on_state_change:
            await self.on_state_change({"status": "stopped"})
    
    async def _on_alert_change(self, active: set, added: set, removed: set):
        """Handle alert status changes"""
        self.active_alerts = active
        print(f"[AutoController] Active alerts: {active}")
        
        # When alert is removed from a region, optionally clear threats there
        for region in removed:
            await self._clear_region_threats(region)
    
    async def _on_telegram_message(self, msg_data: dict):
        """Handle new Telegram message"""
        text = msg_data.get("text", "")
        
        # Quick filter first
        if not self.llm.quick_filter(text, self.config.threat_keywords):
            return
        
        # Process with LLM - now returns list of threats
        threats = await self.llm.process_message(text)
        
        if not threats:
            return
        
        # Process each threat in the message
        for threat_info in threats:
            if threat_info.confidence < 0.5:
                continue
                
            if threat_info.action == "add":
                await self._add_threat(threat_info, msg_data)
            elif threat_info.action == "remove":
                await self._handle_removal(threat_info, msg_data)
    
    async def _on_telegram_reply(self, msg_data: dict):
        """Handle reply message (potential 'minus')"""
        text = msg_data.get("text", "")
        original_text = msg_data.get("original_text", "")
        original_msg_id = msg_data.get("original_msg_id")
        channel = msg_data.get("channel", "")
        
        # Quick check for removal keywords
        if not self.llm.quick_filter(text, self.config.removal_keywords):
            return
        
        # Process with LLM as reply - returns list
        threats = await self.llm.process_message(
            text, 
            is_reply=True, 
            original_text=original_text
        )
        
        for threat_info in threats:
            if threat_info.action == "remove":
                # Find threat by original message ID
                if self.telegram_monitor and original_msg_id:
                    threat_id = self.telegram_monitor.get_threat_for_message(channel, original_msg_id)
                    if threat_id and threat_id in self.threats:
                        await self._remove_threat(threat_id)
                        continue
                
                # Fallback: remove by region if specified
                if threat_info.target:
                    await self._clear_region_threats(threat_info.target)
    
    async def _add_threat(self, info: ThreatInfo, msg_data: dict):
        """Add a new threat to the map using origin -> target logic"""
        target_name = info.target or self._guess_region_from_channel(msg_data.get("channel", ""))
        
        if not target_name:
            print(f"[AutoController] Cannot determine target for threat")
            return
        
        # Get TARGET coordinates (where threat is heading)
        target_coords = await self._get_coords_for_location(target_name)
        if not target_coords:
            print(f"[AutoController] Cannot geocode target: {target_name}")
            return
        target_lat, target_lng = target_coords
        
        # Get ORIGIN coordinates based on origin_type
        origin_coords = await self._get_origin_coords(
            info.origin, 
            info.origin_type, 
            target_lat, 
            target_lng
        )
        marker_lat, marker_lng = origin_coords
        
        # Calculate angle FROM origin TO target (marker should point toward target)
        to_angle = self._calculate_bearing(marker_lat, marker_lng, target_lat, target_lng)
        
        # Add small randomness to avoid stacking
        marker_lat += random.uniform(-0.05, 0.05)
        marker_lng += random.uniform(-0.05, 0.05)
        
        threat = AutoThreat(
            id=self._next_threat_id,
            type=info.threat_type or "drone",
            lat=marker_lat,
            lng=marker_lng,
            angle=to_angle,
            count=info.count,
            region=target_name,
            source_msg_id=msg_data.get("id"),
            source_channel=msg_data.get("channel")
        )
        
        print(f"[AutoController] Origin: {info.origin}({info.origin_type}) -> Target: {target_name}")
        print(f"[AutoController] Marker at ({marker_lat:.4f}, {marker_lng:.4f}) pointing {to_angle:.1f}° toward ({target_lat:.4f}, {target_lng:.4f})")
        
        self.threats[threat.id] = threat
        self._next_threat_id += 1
        
        # Register message-threat association for reply tracking
        if self.telegram_monitor and msg_data.get("id") and msg_data.get("channel"):
            self.telegram_monitor.register_threat_message(
                msg_data["channel"], 
                msg_data["id"], 
                threat.id
            )
        
        if self.on_threat_add:
            await self.on_threat_add(self._threat_to_dict(threat))
    
    async def _remove_threat(self, threat_id: int):
        """Remove a specific threat"""
        if threat_id not in self.threats:
            return
        
        threat = self.threats.pop(threat_id)
        print(f"[AutoController] Removed threat: {threat_id}")
        
        if self.on_threat_remove:
            await self.on_threat_remove({"id": threat_id})
    
    async def _handle_removal(self, info: ThreatInfo, msg_data: dict):
        """Handle removal action from LLM"""
        if info.target:
            await self._clear_region_threats(info.target)
    
    async def _clear_region_threats(self, region: str):
        """Clear all threats in a region"""
        to_remove = [tid for tid, t in self.threats.items() 
                     if t.region.lower() == region.lower() or region.lower() in t.region.lower()]
        
        for tid in to_remove:
            await self._remove_threat(tid)
    
    async def _ttl_cleanup_loop(self):
        """Periodically remove threats that exceeded TTL"""
        while self.is_running:
            await asyncio.sleep(60)  # Check every minute
            
            now = datetime.now()
            ttl = timedelta(minutes=self.config.threat_ttl_minutes)
            
            to_remove = [tid for tid, t in self.threats.items() 
                         if now - t.updated_at > ttl]
            
            for tid in to_remove:
                print(f"[AutoController] TTL expired for threat {tid}")
                await self._remove_threat(tid)
    
    def _offset_coords(self, lat: float, lng: float, angle_deg: float, distance_km: float) -> tuple:
        """
        Calculate new coordinates offset from a point.
        
        Args:
            lat, lng: Starting coordinates
            angle_deg: Direction in degrees (0=North, 90=East, 180=South, 270=West)
            distance_km: Distance in kilometers
        
        Returns:
            (new_lat, new_lng) tuple
        """
        import math
        
        # Convert to radians - angle_deg is compass style (0=N, 90=E)
        # Math uses 0=E, 90=N, so convert: math_angle = 90 - compass_angle
        angle_rad = math.radians(90 - angle_deg)
        
        # Convert km to degrees (approx: 1 degree = 111 km)
        distance_deg = distance_km / 111
        
        # Calculate offset
        delta_lat = distance_deg * math.sin(angle_rad)
        delta_lng = distance_deg * math.cos(angle_rad) / math.cos(math.radians(lat))
        
        return (lat + delta_lat, lng + delta_lng)
    
    async def _get_origin_coords(self, origin: str, origin_type: str, 
                                  target_lat: float, target_lng: float) -> tuple:
        """
        Get origin coordinates based on origin_type.
        
        Args:
            origin: Origin name (city, direction, region, or "море")
            origin_type: Type of origin ("city", "sea", "direction", "region")
            target_lat, target_lng: Target coordinates for calculating offset
            
        Returns:
            (lat, lng) tuple for marker placement
        """
        offset_km = 80  # Distance from target for direction-based origins
        
        if origin_type == "city":
            # Geocode the origin city
            coords = await self._get_coords_for_location(origin)
            if coords:
                return coords
            # Fallback to direction-based offset
            print(f"[AutoController] Could not geocode origin city: {origin}, using direction fallback")
            origin_type = "direction"
        
        if origin_type == "sea":
            # Sea is south of most Ukrainian cities (Black Sea)
            # Place marker south of target
            return self._offset_coords(target_lat, target_lng, 180, offset_km)
        
        if origin_type == "region":
            # Try to extract direction from region description
            # e.g., "північ Київської" -> north of target
            origin_lower = origin.lower() if origin else ""
            
            if "північ" in origin_lower or "север" in origin_lower:
                return self._offset_coords(target_lat, target_lng, 0, offset_km)
            elif "південь" in origin_lower or "юг" in origin_lower or "южн" in origin_lower:
                return self._offset_coords(target_lat, target_lng, 180, offset_km)
            elif "схід" in origin_lower or "восток" in origin_lower or "восточн" in origin_lower:
                return self._offset_coords(target_lat, target_lng, 90, offset_km)
            elif "захід" in origin_lower or "запад" in origin_lower or "западн" in origin_lower:
                return self._offset_coords(target_lat, target_lng, 270, offset_km)
            
            # Try to geocode the region name
            coords = await self._get_coords_for_location(origin)
            if coords:
                return coords
        
        # origin_type == "direction" or fallback
        # If origin is None/empty, default to Russia (northeast = 45°)
        if not origin:
            print(f"[AutoController] No origin specified, defaulting to Russia (45°)")
            return self._offset_coords(target_lat, target_lng, 45, offset_km)
        
        # Use direction_to_angle to get angle from cardinal direction
        from_angle = LLMProcessor.direction_to_angle(origin)
        return self._offset_coords(target_lat, target_lng, from_angle, offset_km)
    
    def _calculate_bearing(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculate bearing (angle) from point 1 to point 2.
        
        Returns:
            Bearing in degrees (0=North, 90=East, 180=South, 270=West)
        """
        import math
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lng = math.radians(lng2 - lng1)
        
        x = math.sin(delta_lng) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lng)
        
        bearing = math.atan2(x, y)
        bearing_deg = math.degrees(bearing)
        
        # Normalize to 0-360
        return (bearing_deg + 360) % 360
    
    async def _get_coords_for_location(self, location: str) -> tuple:
        """Get coordinates for a location (city or region) using geocoder"""
        location_lower = location.lower().strip()
        
        # 1. Quick check in local cache (major cities)
        if location_lower in self.city_coords:
            print(f"[AutoController] Found city in local cache: {location_lower}")
            return self.city_coords[location_lower]
        
        # 2. Partial city match in local cache
        for city, coords in self.city_coords.items():
            if city in location_lower or location_lower in city:
                print(f"[AutoController] Partial city match: {location_lower} -> {city}")
                return coords
        
        # 3. Try geocoding API (for any location in Ukraine)
        geocoder = get_geocoder()
        coords = await geocoder.get_coordinates(location)
        if coords:
            return coords
        
        # 4. Fallback to region match
        if location in self.region_coords:
            return self.region_coords[location]
        
        for name, coords in self.region_coords.items():
            if location_lower in name.lower() or name.lower() in location_lower:
                print(f"[AutoController] Region match: {location_lower} -> {name}")
                return coords
        
        # 5. Default to center of Ukraine
        print(f"[AutoController] Unknown location: {location}, using Ukraine center")
        return (48.38, 31.17)
    
    def _guess_region_from_channel(self, channel: str) -> Optional[str]:
        """Try to guess region from channel name"""
        channel_lower = channel.lower()
        
        for region, ch in self.config.region_channels.items():
            if ch.lower() in channel_lower or channel_lower in ch.lower():
                return region
        
        return None
    
    def _threat_to_dict(self, threat: AutoThreat) -> dict:
        """Convert AutoThreat to dict for API"""
        return {
            "id": threat.id,
            "type": threat.type,
            "lat": threat.lat,
            "lng": threat.lng,
            "angle": threat.angle,
            "count": threat.count,
            "region": threat.region,
            "trajectoryLength": threat.trajectoryLength
        }
    
    def get_all_threats(self) -> List[dict]:
        """Get all current threats as list of dicts"""
        return [self._threat_to_dict(t) for t in self.threats.values()]
    
    def get_status(self) -> dict:
        """Get current AUTO mode status"""
        return {
            "is_running": self.is_running,
            "test_mode": self.config.test_mode,
            "active_alerts": list(self.active_alerts),
            "threat_count": len(self.threats),
            "monitored_channels": self.config.get_channels_to_monitor()
        }
