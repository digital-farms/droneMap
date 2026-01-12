import asyncio
import sys
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Set
from playwright.async_api import async_playwright
import uvicorn
import os
import datetime
import httpx
import json
from dotenv import load_dotenv

from auto_mode import AutoModeConfig, AutoController

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# AUTO mode configuration
auto_config = AutoModeConfig()
auto_controller: Optional[AutoController] = None

# WebSocket connections
active_websockets: Set[WebSocket] = set()

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data Models
class Threat(BaseModel):
    id: int
    type: str  # 'drone' or 'missile'
    lat: float
    lng: float
    angle: float
    count: int = 1

class MapState(BaseModel):
    threats: List[Threat]
    alerts: List[str] = []

# In-memory storage
current_state = MapState(threats=[], alerts=[])
auto_mode_enabled = False

async def send_to_telegram(file_path: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not found. Skipping upload.")
        return {"status": "skipped", "reason": "no_credentials"}

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    async with httpx.AsyncClient() as client:
        try:
            with open(file_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": f"⚠️ Актуальна карта загроз станом на {datetime.datetime.now().strftime('%H:%M')}"}
                response = await client.post(url, data=data, files=files)
                response.raise_for_status()
                return {"status": "sent", "telegram_response": response.json()}
        except Exception as e:
            print(f"Failed to send to Telegram: {e}")
            return {"status": "error", "error": str(e)}

# API Endpoints
@app.get("/api/state")
async def get_state():
    # Merge manual state with AUTO mode threats
    state = current_state.model_dump()
    if auto_controller and auto_mode_enabled:
        auto_threats = auto_controller.get_all_threats()
        state["auto_threats"] = auto_threats
    return state

@app.post("/api/state")
async def update_state(state: MapState):
    global current_state
    current_state = state
    return {"status": "updated", "count": len(state.threats)}

@app.post("/api/screenshot")
async def take_screenshot():
    """
    Launches a headless browser, opens the map in 'view mode', and takes a screenshot.
    """
    print("Screenshot request received...")
    filename = ""
    try:
        async with async_playwright() as p:
            print("Launching browser...")
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            
            # URL of the local server (we assume it's running on port 8000)
            url = "http://localhost:8000/?view=true"
            print(f"Navigating to {url}...")
            
            await page.goto(url)
            
            # Wait for map to load (leaflet usually takes a moment)
            await page.wait_for_timeout(3000) 
            
            # Create screenshots directory
            if not os.path.exists("screenshots"):
                os.makedirs("screenshots")
                
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshots/map_{timestamp}.png"
            
            print(f"Saving screenshot to {filename}...")
            await page.screenshot(path=filename)
            await browser.close()
        
        # Send to Telegram
        tg_status = await send_to_telegram(filename)
            
        return {"status": "success", "file": filename, "telegram": tg_status}

    except Exception as e:
        print(f"Screenshot failed: {e}")
        # Return 500 error so frontend handles it, or return json with error
        return {"status": "error", "message": str(e)}

# ==================== AUTO MODE ENDPOINTS ====================

async def broadcast_to_websockets(message: dict):
    """Send message to all connected WebSocket clients"""
    if not active_websockets:
        return
    
    data = json.dumps(message)
    disconnected = set()
    
    for ws in active_websockets:
        try:
            await ws.send_text(data)
        except:
            disconnected.add(ws)
    
    active_websockets.difference_update(disconnected)

async def on_auto_threat_add(threat: dict):
    """Callback when AUTO mode adds a threat"""
    # Broadcast to WebSocket clients (don't add to current_state - it's managed by auto_controller)
    await broadcast_to_websockets({
        "type": "threat_add",
        "data": threat
    })

async def on_auto_threat_remove(data: dict):
    """Callback when AUTO mode removes a threat"""
    threat_id = data["id"]
    
    await broadcast_to_websockets({
        "type": "threat_remove",
        "data": {"id": threat_id}
    })

async def on_auto_state_change(data: dict):
    """Callback when AUTO mode state changes"""
    await broadcast_to_websockets({
        "type": "auto_status",
        "data": data
    })

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    print(f"[WS] Client connected. Total: {len(active_websockets)}")
    
    try:
        # Send current state on connect
        await websocket.send_text(json.dumps({
            "type": "init",
            "data": {
                "auto_mode": auto_mode_enabled,
                "threats": [t.dict() for t in current_state.threats],
                "status": auto_controller.get_status() if auto_controller else None
            }
        }))
        
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                
    except WebSocketDisconnect:
        pass
    finally:
        active_websockets.discard(websocket)
        print(f"[WS] Client disconnected. Total: {len(active_websockets)}")

@app.post("/api/auto/start")
async def start_auto_mode():
    """Start AUTO mode monitoring"""
    global auto_controller, auto_mode_enabled
    
    if auto_mode_enabled:
        return {"status": "already_running"}
    
    auto_controller = AutoController(
        auto_config,
        on_threat_add=on_auto_threat_add,
        on_threat_remove=on_auto_threat_remove,
        on_state_change=on_auto_state_change
    )
    
    # Start in background
    asyncio.create_task(auto_controller.start())
    auto_mode_enabled = True
    
    return {
        "status": "started",
        "test_mode": auto_config.test_mode,
        "channels": auto_config.get_channels_to_monitor()
    }

@app.post("/api/auto/stop")
async def stop_auto_mode():
    """Stop AUTO mode monitoring"""
    global auto_controller, auto_mode_enabled
    
    if not auto_mode_enabled or not auto_controller:
        return {"status": "not_running"}
    
    await auto_controller.stop()
    auto_mode_enabled = False
    
    return {"status": "stopped"}

@app.get("/api/auto/status")
async def get_auto_status():
    """Get AUTO mode status"""
    return {
        "enabled": auto_mode_enabled,
        "status": auto_controller.get_status() if auto_controller else None
    }

# ==================== STATIC FILES ====================

@app.get("/viewer")
async def viewer_page():
    """Serve read-only viewer page"""
    return FileResponse("viewer.html")

# Auto-start AUTO mode on startup (always enabled by default)
@app.on_event("startup")
async def startup_event():
    print("[Startup] Starting AUTO mode...")
    # Small delay to let server fully start
    await asyncio.sleep(2)
    try:
        await start_auto_mode()
        print("[Startup] AUTO mode started successfully")
    except Exception as e:
        print(f"[Startup] Failed to start AUTO mode: {e}")

# Serve main files with no-cache headers
@app.get("/")
async def serve_index():
    return FileResponse("index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/index.html")
async def serve_index_html():
    return FileResponse("index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/styles.css")
async def serve_styles():
    return FileResponse("styles.css", media_type="text/css", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/script.js")
async def serve_script():
    return FileResponse("script.js", media_type="application/javascript", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

# Serve static files (Frontend) - for other assets
app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
