import os
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class AutoModeConfig:
    # Telegram API credentials (from my.telegram.org)
    api_id: int = field(default_factory=lambda: int(os.getenv("TELEGRAM_API_ID", "0")))
    api_hash: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH", ""))
    
    # OpenRouter API
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    llm_model: str = "anthropic/claude-3-haiku"
    
    # Alert channel (official air raid alerts)
    alert_channel: str = "air_alert_ua"
    
    # Test mode
    test_mode: bool = True
    test_channel: str = "raketa_trevoga"
    
    # Production channels (region -> channel)
    # Will be filled with real channels later
    region_channels: Dict[str, str] = field(default_factory=lambda: {
        "Київська": "kyiv_operativ",
        "Харківська": "kharkiv_operativ", 
        "Одеська": "odesa_operativ",
        # Add more regions as needed
    })
    
    # TTL for threats in minutes (auto-remove after this time if no update)
    threat_ttl_minutes: int = 30
    
    # Polling intervals
    alert_poll_interval: int = 30  # seconds
    
    # Keywords for quick filtering (before LLM)
    threat_keywords: List[str] = field(default_factory=lambda: [
        # БПЛА / Дроны
        "бпла", "шахед", "shahed", "мопед", "герань", "дрон", "безпілотник", "uav",
        # Крылатые ракеты
        "ракет", "кр ", "калібр", "калибр", "х-101", "x-101", "х-555", "крилат", "крылат",
        # Баллистика
        "баліст", "балист", "КАБ", "іскандер", "искандер", "точка-у",
        # Гиперзвук
        "кінжал", "кинжал", "гіперзвук", "гиперзвук", "сверхзвук", "циркон",
        # Ядерная
        "ядерн",
        # Общие
        "курс", "напрямок", "входить", "рухається", "летить"
    ])
    
    removal_keywords: List[str] = field(default_factory=lambda: [
        "мінус", "минус", "збито", "сбито", "знищено", "уничтожено",
        "впав", "упав", "вийшов", "вышел", "покинув"
    ])
    
    def get_active_channel(self) -> str:
        """Returns test channel in test mode, otherwise first production channel"""
        if self.test_mode:
            return self.test_channel
        return list(self.region_channels.values())[0] if self.region_channels else ""
    
    def get_channels_to_monitor(self) -> List[str]:
        """Returns list of channels to monitor"""
        if self.test_mode:
            return [self.test_channel]
        return list(self.region_channels.values())
