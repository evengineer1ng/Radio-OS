#!/usr/bin/env python3
"""Debug WebSocket handler to isolate the issue."""

import asyncio
from fastapi import FastAPI, WebSocket
import uvicorn

app = FastAPI()

@app.websocket("/ws/live")
async def websocket_debug(websocket: WebSocket):
    print("🔌 WebSocket connection attempt...")
    try:
        await websocket.accept()
        print("✅ WebSocket accepted successfully!")
        
        await websocket.send_json({"type": "connected", "message": "Debug WebSocket working"})
        
        while True:
            data = await websocket.receive_text()
            print(f"📥 Received: {data}")
            await websocket.send_json({"type": "echo", "data": data})
            
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Starting debug WebSocket server on port 7556...")
    uvicorn.run(app, host="0.0.0.0", port=7556, log_level="info")