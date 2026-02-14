#!/usr/bin/env python3
"""Minimal WebSocket server test to isolate the issue."""

import asyncio
from fastapi import FastAPI, WebSocket
import uvicorn

app = FastAPI()

@app.get("/test")
async def test():
    return {"message": "HTTP working"}

@app.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    print("WebSocket connection received!")
    await websocket.accept()
    print("WebSocket accepted!")
    await websocket.send_json({"message": "Connected to test WebSocket!"})
    
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"echo": data})
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    print("Starting minimal WebSocket test server on port 7557...")
    uvicorn.run(app, host="0.0.0.0", port=7557, log_level="info")