import uvicorn
import sys
import asyncio
import os

if __name__ == "__main__":
    # Fix for Windows asyncio loop policy with Playwright
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run Uvicorn programmatically
    # We use "main:app" string to enable reload support
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
