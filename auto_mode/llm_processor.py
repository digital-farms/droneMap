import aiohttp
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ThreatInfo:
    action: str  # "add", "update", "remove", "ignore"
    threat_type: Optional[str] = None  # "drone", "missile", "ballistic", "hypersonic", "nuclear"
    count: int = 1
    target: Optional[str] = None  # City/region WHERE threat is heading
    origin: Optional[str] = None  # City/region/direction WHERE threat is coming FROM
    origin_type: str = "direction"  # "city", "sea", "direction", "region"
    confidence: float = 0.0
    raw_response: Optional[str] = None

class LLMProcessor:
    """
    Processes Telegram messages using OpenRouter LLM API
    to extract threat information.
    """
    
    def __init__(self, api_key: str, model: str = "anthropic/claude-3-haiku"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
    async def process_message(self, text: str, is_reply: bool = False, 
                             original_text: Optional[str] = None) -> list:
        """
        Process a message and extract threat information.
        
        Args:
            text: The message text to analyze
            is_reply: Whether this is a reply to another message
            original_text: If is_reply, the original message being replied to
            
        Returns:
            List of ThreatInfo objects (can be empty if no threats found)
        """
        
        if not self.api_key:
            print("[LLM] No API key configured")
            return []
        
        prompt = self._build_prompt(text, is_reply, original_text)
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://dronemap.local",
                    "X-Title": "DroneMap"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2000
                }
                
                async with session.post(self.api_url, headers=headers, 
                                        json=payload, timeout=30) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"[LLM] API error {response.status}: {error_text}")
                        return []
                    
                    result = await response.json()
                    return self._parse_response(result)
                    
        except Exception as e:
            print(f"[LLM] Error processing message: {e}")
            return []
    
    def _get_system_prompt(self) -> str:
        return """Ти аналізуєш повідомлення з українських телеграм-каналів про повітряну тривогу та загрози.
Твоя задача - витягти ВСІ загрози з повідомлення (може бути кілька).

Відповідай ТІЛЬКИ валідним JSON без додаткового тексту.

Формат відповіді - МАСИВ загроз:
{
  "threats": [
    {
      "action": "add" | "remove" | "ignore",
      "threat_type": "drone" | "missile" | "ballistic" | "hypersonic" | "nuclear",
      "count": число,
      "target": "місто/область КУДИ летить",
      "origin": "місто/область/напрямок ЗВІДКИ летить",
      "origin_type": "city" | "sea" | "direction" | "region"
    }
  ]
}

ПРИКЛАДИ:

1. "ракета від Черкас до Києва":
{"threats": [{"action": "add", "threat_type": "missile", "count": 1, "target": "Київ", "origin": "Черкаси", "origin_type": "city"}]}

2. "10 з моря в сторону Одеси":
{"threats": [{"action": "add", "threat_type": "drone", "count": 10, "target": "Одеса", "origin": "море", "origin_type": "sea"}]}

3. "5 на півночі Київської, летять на Житомир":
{"threats": [{"action": "add", "threat_type": "drone", "count": 5, "target": "Житомир", "origin": "північ Київської", "origin_type": "region"}]}

4. "3 західніше Запоріжжя":
{"threats": [{"action": "add", "threat_type": "drone", "count": 3, "target": "Запоріжжя", "origin": "захід", "origin_type": "direction"}]}

5. "2 від Черкас, 18 курсом на Дніпро з півдня":
{"threats": [
  {"action": "add", "threat_type": "drone", "count": 2, "target": "Черкаси", "origin": "південь", "origin_type": "direction"},
  {"action": "add", "threat_type": "drone", "count": 18, "target": "Дніпро", "origin": "південь", "origin_type": "direction"}
]}

6. "3 над Києвом/Вишгородом/Броварами" - ВАЖЛИВО: створи ОДНУ угрозу з ПЕРШИМ містом:
{"threats": [{"action": "add", "threat_type": "drone", "count": 3, "target": "Київ", "origin": "Росія", "origin_type": "direction"}]}

7. "18 з Бериславського району в сторону Казанки/Широкого":
{"threats": [{"action": "add", "threat_type": "drone", "count": 18, "target": "Казанка", "origin": "Бериславський район", "origin_type": "region"}]}

8. "5 крутятся на севере Киевской области" - ВАЖЛИВО: коли немає конкретного міста, використай ОБЛАСТЬ:
{"threats": [{"action": "add", "threat_type": "drone", "count": 5, "target": "Київська область", "origin": "північ", "origin_type": "direction"}]}

9. "2 в Криворізькому районі":
{"threats": [{"action": "add", "threat_type": "drone", "count": 2, "target": "Кривий Ріг", "origin": "Росія", "origin_type": "direction"}]}

10. "балістика на Харків" - ВАЖЛИВО: ВСІ загрози БЕЗ уточнення напрямку завжди летять з РОСІЇ (північний схід):
{"threats": [{"action": "add", "threat_type": "ballistic", "count": 1, "target": "Харків", "origin": "Росія", "origin_type": "direction"}]}

11. "КР на Київ":
{"threats": [{"action": "add", "threat_type": "missile", "count": 1, "target": "Київ", "origin": "Росія", "origin_type": "direction"}]}

12. "шахеди на Одесу" (без напрямку):
{"threats": [{"action": "add", "threat_type": "drone", "count": 1, "target": "Одеса", "origin": "Росія", "origin_type": "direction"}]}

ТИПИ ЗАГРОЗ:
- "drone" - БПЛА, шахед, герань, мопед, дрон, безпілотник
- "missile" - крылатая ракета, КР, калібр, х-101, х-555
- "ballistic" - балістична, балистика, іскандер, точка-у
- "hypersonic" - кінжал, кинжал, гіперзвук, сверхзвук, циркон
- "nuclear" - ядерна, ядерная

ORIGIN_TYPE:
- "city" - конкретне місто/село (Черкаси, Бровари, Апостолове)
- "sea" - море, узбережжя
- "direction" - сторона світу (північ, захід, північний схід)
- "region" - область або район (північ Київської, Криворізький район)

Правила:
- "add" - загроза виявлена/рухається
- "remove" - збито/мінус/знищено
- Якщо немає загроз: {"threats": []}"""

    def _build_prompt(self, text: str, is_reply: bool, original_text: Optional[str]) -> str:
        if is_reply and original_text:
            return f"""Це РЕПЛАЙ на попереднє повідомлення.

Оригінальне повідомлення:
"{original_text}"

Реплай (відповідь):
"{text}"

Проаналізуй, чи означає реплай що загрозу збито/мінус. Якщо так - action="remove"."""
        
        return f"""Проаналізуй повідомлення з телеграм-каналу:

"{text}"

Витягни інформацію про загрози."""

    def _parse_response(self, result: Dict[str, Any]) -> list:
        """Parse LLM response and extract list of ThreatInfo"""
        try:
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Try to extract JSON from response
            content = content.strip()
            if content.startswith("```"):
                # Remove markdown code blocks
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            data = json.loads(content)
            
            # Handle new array format
            threats_data = data.get("threats", [])
            if not threats_data:
                # Fallback: maybe old format with single threat
                if data.get("action") and data.get("action") != "ignore":
                    threats_data = [data]
                else:
                    return []
            
            threats = []
            for t in threats_data:
                if t.get("action") == "ignore":
                    continue
                threats.append(ThreatInfo(
                    action=t.get("action", "add"),
                    threat_type=t.get("threat_type", "drone"),
                    count=t.get("count", 1),
                    target=t.get("target"),
                    origin=t.get("origin"),
                    origin_type=t.get("origin_type", "direction"),
                    confidence=t.get("confidence", 0.7),
                    raw_response=content
                ))
            
            print(f"[LLM] Parsed {len(threats)} threats from message")
            return threats
            
        except json.JSONDecodeError as e:
            print(f"[LLM] Failed to parse JSON: {e}")
            print(f"[LLM] Raw content: {content[:200]}")
            return []
        except Exception as e:
            print(f"[LLM] Error parsing response: {e}")
            return []
    
    def quick_filter(self, text: str, keywords: list) -> bool:
        """Quick keyword-based filter before sending to LLM"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    @staticmethod
    def direction_to_angle(direction: Optional[str]) -> float:
        """Convert direction text to angle in degrees (where the threat is coming FROM)"""
        if not direction:
            return 180.0  # Default: coming from south
        
        direction_map = {
            # === UKRAINIAN ===
            # North
            "північ": 0, "північн": 0, "пн": 0,
            # Northeast  
            "північний схід": 45, "північно-східн": 45, "пн-сх": 45, "північносхідн": 45,
            # East
            "схід": 90, "східн": 90, "сх": 90,
            # Southeast
            "південний схід": 135, "південно-східн": 135, "пд-сх": 135, "південносхідн": 135,
            # South
            "південь": 180, "південн": 180, "пд": 180,
            # Southwest
            "південний захід": 225, "південно-західн": 225, "пд-зх": 225, "південнозахідн": 225,
            # West
            "захід": 270, "західн": 270, "зх": 270,
            # Northwest
            "північний захід": 315, "північно-західн": 315, "пн-зх": 315, "північнозахідн": 315,
            
            # === RUSSIAN ===
            # North
            "север": 0, "северн": 0, "сев": 0,
            # Northeast (with and without hyphen)
            "северо-восток": 45, "северо-восточн": 45, "св": 45,
            "северовосток": 45, "северовосточн": 45,  # северовосточным, северовосточнее
            # East
            "восток": 90, "восточн": 90, "вост": 90,
            # Southeast
            "юго-восток": 135, "юго-восточн": 135, "юв": 135,
            "юговосток": 135, "юговосточн": 135,
            # South
            "юг": 180, "южн": 180, "юга": 180,
            # Southwest
            "юго-запад": 225, "юго-западн": 225, "юз": 225,
            "югозапад": 225, "югозападн": 225,
            # West
            "запад": 270, "западн": 270, "зап": 270,
            # Northwest
            "северо-запад": 315, "северо-западн": 315, "сз": 315,
            "северозапад": 315, "северозападн": 315,  # северозападнее, северозападней
            
            # === COUNTRIES/REGIONS AS DIRECTIONS ===
            "росі": 45,         # Russia - northeast
            "росс": 45,         # Россия
            "рф": 45,
            "білорус": 0,       # Belarus - north
            "беларус": 0,
            "крим": 180,        # Crimea - south
            "крым": 180,
            "море": 180,        # Sea - south (Black Sea)
            "азов": 135,        # Azov Sea - southeast
        }
        
        direction_lower = direction.lower().strip()
        for key, angle in direction_map.items():
            if key in direction_lower:
                print(f"[LLM] Direction '{direction}' -> {angle}°")
                return float(angle)
        
        print(f"[LLM] Unknown direction '{direction}', defaulting to 180° (south)")
        return 180.0  # Default to south if unknown
