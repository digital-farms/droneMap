"""
Geocoder module using OpenStreetMap Nominatim API.
Converts location names to coordinates with caching.
"""

import aiohttp
import asyncio
import json
import os
from typing import Optional, Tuple, Dict
from pathlib import Path


class Geocoder:
    """
    Geocodes Ukrainian location names to coordinates using OSM Nominatim.
    Results are cached in memory and persisted to file.
    """
    
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    CACHE_FILE = Path(__file__).parent / "geocache.json"
    
    # Rate limiting: 1 request per second for Nominatim
    _last_request_time = 0
    _rate_limit_delay = 1.1  # seconds
    
    def __init__(self):
        self._cache: Dict[str, Tuple[float, float]] = {}
        self._load_cache()
        
        # Fallback coordinates for oblasts (centers)
        self._oblast_fallbacks = {
            "київ": (50.4501, 30.5234),
            "харків": (49.9935, 36.2304),
            "одес": (46.4825, 30.7233),
            "дніпр": (48.4647, 35.0462),
            "днепр": (48.4647, 35.0462),
            "запоріж": (47.8388, 35.1396),
            "запорож": (47.8388, 35.1396),
            "львів": (49.8397, 24.0297),
            "крив": (47.9086, 33.3433),  # Kryvyi Rih
            "полтав": (49.5883, 34.5514),
            "черкас": (49.4444, 32.0598),
            "вінниц": (49.2331, 28.4682),
            "житомир": (50.2547, 28.6587),
            "сум": (50.9077, 34.7981),
            "черніг": (51.4982, 31.2893),
            "чернig": (51.4982, 31.2893),
            "херсон": (46.6354, 32.6169),
            "миколаїв": (46.9750, 31.9946),
            "николаев": (46.9750, 31.9946),
            "кропивниц": (48.5079, 32.2623),
            "кіровоград": (48.5079, 32.2623),
            "хмельниц": (49.4230, 26.9871),
            "терноп": (49.5535, 25.5948),
            "рівн": (50.6199, 26.2516),
            "ровн": (50.6199, 26.2516),
            "волин": (50.7472, 25.3254),
            "луцьк": (50.7472, 25.3254),
            "івано-франків": (48.9226, 24.7111),
            "ужгород": (48.6208, 22.2879),
            "закарпат": (48.6208, 22.2879),
            "чернівц": (48.2920, 25.9358),
        }
    
    def _load_cache(self):
        """Load cache from file"""
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert lists back to tuples
                    self._cache = {k: tuple(v) for k, v in data.items()}
                print(f"[Geocoder] Loaded {len(self._cache)} cached locations")
        except Exception as e:
            print(f"[Geocoder] Failed to load cache: {e}")
            self._cache = {}
    
    def _save_cache(self):
        """Save cache to file"""
        try:
            with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Geocoder] Failed to save cache: {e}")
    
    def _normalize_name(self, name: str) -> str:
        """Normalize location name for caching"""
        return name.lower().strip()
    
    def _get_fallback(self, location: str) -> Optional[Tuple[float, float]]:
        """Get fallback coordinates from oblast centers"""
        location_lower = location.lower()
        for key, coords in self._oblast_fallbacks.items():
            if key in location_lower:
                print(f"[Geocoder] Using fallback for '{location}': {coords}")
                return coords
        return None
    
    async def _rate_limit(self):
        """Ensure we don't exceed Nominatim rate limits"""
        import time
        now = time.time()
        elapsed = now - Geocoder._last_request_time
        if elapsed < self._rate_limit_delay:
            await asyncio.sleep(self._rate_limit_delay - elapsed)
        Geocoder._last_request_time = time.time()
    
    async def get_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
        """
        Get coordinates for a Ukrainian location.
        
        Args:
            location: Name of city/town/village in Ukrainian or Russian
            
        Returns:
            Tuple of (lat, lng) or None if not found
        """
        if not location:
            return None
        
        normalized = self._normalize_name(location)
        
        # Check cache first
        if normalized in self._cache:
            coords = self._cache[normalized]
            print(f"[Geocoder] Cache hit for '{location}': {coords}")
            return coords
        
        # Try Nominatim API
        coords = await self._query_nominatim(location)
        
        if coords:
            # Cache the result
            self._cache[normalized] = coords
            self._save_cache()
            return coords
        
        # Fallback to oblast center
        fallback = self._get_fallback(location)
        if fallback:
            self._cache[normalized] = fallback
            self._save_cache()
            return fallback
        
        print(f"[Geocoder] Could not find coordinates for '{location}'")
        return None
    
    async def _query_nominatim(self, location: str) -> Optional[Tuple[float, float]]:
        """Query Nominatim API for coordinates"""
        await self._rate_limit()
        
        # Add "Ukraine" to improve search accuracy
        search_query = f"{location}, Україна"
        
        params = {
            "q": search_query,
            "format": "json",
            "limit": 1,
            "countrycodes": "ua",  # Restrict to Ukraine
            "accept-language": "uk,ru",
        }
        
        headers = {
            "User-Agent": "DroneMap/1.0 (https://github.com/dronemap)"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.NOMINATIM_URL, 
                    params=params, 
                    headers=headers,
                    timeout=10
                ) as response:
                    if response.status != 200:
                        print(f"[Geocoder] API error {response.status}")
                        return None
                    
                    results = await response.json()
                    
                    if results:
                        lat = float(results[0]["lat"])
                        lng = float(results[0]["lon"])
                        display_name = results[0].get("display_name", "")
                        print(f"[Geocoder] Found '{location}' -> ({lat:.4f}, {lng:.4f}) [{display_name[:50]}...]")
                        return (lat, lng)
                    else:
                        print(f"[Geocoder] No results for '{location}'")
                        return None
                        
        except asyncio.TimeoutError:
            print(f"[Geocoder] Timeout querying '{location}'")
            return None
        except Exception as e:
            print(f"[Geocoder] Error querying '{location}': {e}")
            return None


# Singleton instance
_geocoder: Optional[Geocoder] = None

def get_geocoder() -> Geocoder:
    """Get or create the singleton geocoder instance"""
    global _geocoder
    if _geocoder is None:
        _geocoder = Geocoder()
    return _geocoder


async def geocode(location: str) -> Optional[Tuple[float, float]]:
    """Convenience function to geocode a location"""
    return await get_geocoder().get_coordinates(location)
