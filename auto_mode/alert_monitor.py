import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Set, Callable, Optional
from datetime import datetime
import re

class AlertMonitor:
    """
    Monitors @air_alert_ua channel for air raid alerts by parsing public web view.
    No API key required.
    """
    
    def __init__(self, on_alert_change: Optional[Callable] = None):
        self.base_url = "https://t.me/s/air_alert_ua"
        self.active_alerts: Set[str] = set()
        self.on_alert_change = on_alert_change
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def fetch_alerts(self) -> Set[str]:
        """Fetch current active alerts from Telegram channel web view"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, timeout=10) as response:
                    if response.status != 200:
                        print(f"[AlertMonitor] Failed to fetch: {response.status}")
                        return self.active_alerts
                    
                    html = await response.text()
                    return self._parse_alerts(html)
        except Exception as e:
            print(f"[AlertMonitor] Error fetching alerts: {e}")
            return self.active_alerts
    
    def _parse_alerts(self, html: str) -> Set[str]:
        """Parse HTML to extract active alerts"""
        soup = BeautifulSoup(html, 'html.parser')
        messages = soup.find_all('div', class_='tgme_widget_message_text')
        
        active = set()
        alert_on = set()
        alert_off = set()
        
        # Process messages (they come in chronological order on the page)
        for msg in messages:
            text = msg.get_text()
            
            # 🔴 = alert ON
            if '🔴' in text:
                region = self._extract_region(text)
                if region:
                    alert_on.add(region)
                    
            # 🟢 = alert OFF
            elif '🟢' in text:
                region = self._extract_region(text)
                if region:
                    alert_off.add(region)
        
        # Regions with alert ON but not OFF in recent messages
        active = alert_on - alert_off
        
        return active
    
    def _extract_region(self, text: str) -> Optional[str]:
        """Extract region name from alert message"""
        # Pattern: "Повітряна тривога в <region>"
        # or "Відбій тривоги в <region>"
        
        patterns = [
            r'(?:тривога|Відбій тривоги)\s+(?:в|у)\s+(.+?)(?:\.|$)',
            r'(?:область|області)\s*[:\-]?\s*(.+?)(?:\.|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                region = match.group(1).strip()
                # Clean up common suffixes
                region = re.sub(r'\s*(область|області|та район|район).*$', '', region, flags=re.IGNORECASE)
                return self._normalize_region(region)
        
        # Fallback: look for known region names
        known_regions = [
            "Київ", "Харків", "Одес", "Дніпр", "Львів", "Запоріж",
            "Донец", "Луган", "Миколаїв", "Полтав", "Черніг", "Черкас",
            "Сум", "Херсон", "Вінниц", "Житомир", "Хмельниц", "Рівн",
            "Івано-Франків", "Тернопіл", "Волин", "Закарпат", "Чернівец", "Кіровоград"
        ]
        
        for region in known_regions:
            if region.lower() in text.lower():
                return self._normalize_region(region)
        
        return None
    
    def _normalize_region(self, region: str) -> str:
        """Normalize region name to standard format"""
        region_map = {
            "київ": "Київська",
            "харків": "Харківська",
            "одес": "Одеська",
            "дніпр": "Дніпропетровська",
            "львів": "Львівська",
            "запоріж": "Запорізька",
            "донец": "Донецька",
            "луган": "Луганська",
            "миколаїв": "Миколаївська",
            "полтав": "Полтавська",
            "черніг": "Чернігівська",
            "черкас": "Черкаська",
            "сум": "Сумська",
            "херсон": "Херсонська",
            "вінниц": "Вінницька",
            "житомир": "Житомирська",
            "хмельниц": "Хмельницька",
            "рівн": "Рівненська",
            "івано-франків": "Івано-Франківська",
            "тернопіл": "Тернопільська",
            "волин": "Волинська",
            "закарпат": "Закарпатська",
            "чернівец": "Чернівецька",
            "кіровоград": "Кіровоградська",
        }
        
        region_lower = region.lower()
        for key, value in region_map.items():
            if key in region_lower:
                return value
        
        return region
    
    async def start(self, poll_interval: int = 30):
        """Start monitoring alerts"""
        self._running = True
        print(f"[AlertMonitor] Starting with {poll_interval}s interval")
        
        while self._running:
            new_alerts = await self.fetch_alerts()
            
            # Check for changes
            added = new_alerts - self.active_alerts
            removed = self.active_alerts - new_alerts
            
            if added or removed:
                print(f"[AlertMonitor] Alert change - Added: {added}, Removed: {removed}")
                self.active_alerts = new_alerts
                
                if self.on_alert_change:
                    await self.on_alert_change(self.active_alerts, added, removed)
            
            await asyncio.sleep(poll_interval)
    
    def stop(self):
        """Stop monitoring"""
        self._running = False
        if self._task:
            self._task.cancel()
    
    def is_region_active(self, region: str) -> bool:
        """Check if a region has active alert"""
        return region in self.active_alerts or any(
            region.lower() in alert.lower() for alert in self.active_alerts
        )
