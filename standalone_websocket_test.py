#!/usr/bin/env python3
"""Standalone minimal FastAPI + WebSocket test to verify base functionality."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
import asyncio

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Standalone test server", "websocket": "/ws/test"}

@app.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    print("WebSocket connection received!")
    await websocket.accept()
    print("WebSocket accepted!")
    await websocket.send_text("Standalone WebSocket working!")
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received: {data}")
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    print("🧪 Starting standalone FastAPI WebSocket test on port 7558...")
    uvicorn.run(app, host="127.0.0.1", port=7558, log_level="info")