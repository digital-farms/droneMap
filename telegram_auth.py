"""
Telegram Authentication Script
Run this ONCE to create the session file before starting the server.
"""
import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")

async def main():
    print("=" * 50)
    print("Telegram Authentication")
    print("=" * 50)
    
    if not API_ID or not API_HASH:
        print("ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH not found in .env")
        return
    
    session_path = "telegram_session"
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    print(f"\nConnecting to Telegram...")
    await client.start()
    
    me = await client.get_me()
    print(f"\n✓ Successfully authenticated as: {me.username or me.phone}")
    print(f"✓ Session saved to: {session_path}.session")
    print("\nYou can now run the server with: python run.py")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
