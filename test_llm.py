"""
Test script for LLM processor with claude-3.5-haiku
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from auto_mode.llm_processor import LLMProcessor

async def test_llm():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in .env")
        return
    
    llm = LLMProcessor(api_key)
    print(f"📦 Model: {llm.model}")
    print("=" * 60)
    
    # Test messages
    test_messages = [
        # Test 1: Messages without threat type (should be drone)
        """Житомирщина:
2 на Житомир 
1 на Коростишів
1 на Народичі

Київщина:
1 на Іванків 

Дніпропетровщина:
1 на Павлоград
2 на Богуслав""",
        
        # Test 2: Mixed types
        "3 шахеди на Одесу, КР на Київ",
        
        # Test 3: Ballistic
        "Цель на Харків",
        
        # Test 4: With direction
        "5 БПЛА північніше Києва західним курсом",
    ]
    
    for i, msg in enumerate(test_messages, 1):
        print(f"\n🧪 Test {i}:")
        print(f"Input: {msg[:100]}{'...' if len(msg) > 100 else ''}")
        print("-" * 40)
        
        try:
            results = await llm.process_batch([msg])
            
            if results:
                for r in results:
                    print(f"  ✅ {r.threat_type} x{r.count} → {r.target}")
                    if r.heading:
                        print(f"     курс: {r.heading}")
                    if r.target_offset:
                        print(f"     offset: {r.target_offset}")
            else:
                print("  ⚠️ No threats found")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        print()

if __name__ == "__main__":
    asyncio.run(test_llm())
