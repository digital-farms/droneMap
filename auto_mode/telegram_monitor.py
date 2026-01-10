import asyncio
from typing import Callable, Optional, Dict, List, Any
from telethon import TelegramClient, events
from telethon.tl.types import Message
import os

class TelegramMonitor:
    """
    Monitors Telegram channels for threat-related messages using Telethon.
    Requires user account (not bot) to read public channels.
    """
    
    def __init__(self, api_id: int, api_hash: str, 
                 on_message: Optional[Callable] = None,
                 on_reply: Optional[Callable] = None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.on_message = on_message
        self.on_reply = on_reply
        self.client: Optional[TelegramClient] = None
        self.channels: List[str] = []
        self._running = False
        
        # Store message IDs for tracking replies
        # channel -> {message_id -> threat_id}
        self.message_threat_map: Dict[str, Dict[int, int]] = {}
        
    async def start(self, channels: List[str]):
        """Start monitoring specified channels"""
        self.channels = channels
        self._running = True
        
        session_path = os.path.join(os.path.dirname(__file__), '..', 'telegram_session')
        self.client = TelegramClient(session_path, self.api_id, self.api_hash)
        
        await self.client.start()
        
        print(f"[TelegramMonitor] Connected as {(await self.client.get_me()).username}")
        print(f"[TelegramMonitor] Monitoring channels: {channels}")
        
        # Set up event handlers
        @self.client.on(events.NewMessage(chats=channels))
        async def handle_new_message(event: events.NewMessage.Event):
            await self._process_message(event.message)
        
        # Keep running
        await self.client.run_until_disconnected()
    
    async def _process_message(self, message: Message):
        """Process incoming message"""
        if not message.text:
            return
        
        channel = await self._get_channel_name(message)
        
        # Check if this is a reply
        is_reply = message.reply_to is not None
        original_text = None
        original_msg_id = None
        
        if is_reply and message.reply_to.reply_to_msg_id:
            original_msg_id = message.reply_to.reply_to_msg_id
            try:
                original_msg = await self.client.get_messages(
                    message.chat_id, 
                    ids=original_msg_id
                )
                if original_msg:
                    original_text = original_msg.text
            except Exception as e:
                print(f"[TelegramMonitor] Failed to fetch original message: {e}")
        
        msg_data = {
            "id": message.id,
            "text": message.text,
            "channel": channel,
            "date": message.date,
            "is_reply": is_reply,
            "original_msg_id": original_msg_id,
            "original_text": original_text
        }
        
        print(f"[TelegramMonitor] New message from {channel}: {message.text[:100]}...")
        
        if is_reply and self.on_reply:
            await self.on_reply(msg_data)
        elif self.on_message:
            await self.on_message(msg_data)
    
    async def _get_channel_name(self, message: Message) -> str:
        """Get channel username from message"""
        try:
            chat = await message.get_chat()
            return chat.username or str(chat.id)
        except:
            return str(message.chat_id)
    
    def register_threat_message(self, channel: str, message_id: int, threat_id: int):
        """Register association between message and threat for reply tracking"""
        if channel not in self.message_threat_map:
            self.message_threat_map[channel] = {}
        self.message_threat_map[channel][message_id] = threat_id
    
    def get_threat_for_message(self, channel: str, message_id: int) -> Optional[int]:
        """Get threat ID associated with a message"""
        return self.message_threat_map.get(channel, {}).get(message_id)
    
    async def stop(self):
        """Stop monitoring"""
        self._running = False
        if self.client:
            await self.client.disconnect()
            print("[TelegramMonitor] Disconnected")
    
    async def send_test_message(self, channel: str, text: str):
        """Send a test message to a channel (for testing purposes)"""
        if self.client:
            await self.client.send_message(channel, text)
