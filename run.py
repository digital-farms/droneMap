import uvicorn
import sys
import asyncio
import os

if __name__ == "__main__":
    # Fix for Windows asyncio loop policy with Playwright
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run Uvicorn programmatically
    # Use PORT env var for cloud deployment (Render, Heroku, etc.)
    port = int(os.getenv("PORT", 8080))
    reload = os.getenv("AUTO_START") != "true"  # Disable reload in production
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
