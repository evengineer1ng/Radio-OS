#!/usr/bin/env python3
"""
Simple WebSocket test to verify websockets library works
"""

import asyncio
import websockets
import sys

async def simple_handler(websocket, path):
    print(f"Handler called: path={path}")
    try:
        async for message in websocket:
            print(f"Got message: {message}")
            await websocket.send(f"Echo: {message}")
            print(f"Sent echo response")
    except Exception as e:
        print(f"Handler exception: {e}")

async def main():
    print("Starting simple WebSocket server on port 9999...")
    try:
        server = await websockets.serve(simple_handler, "127.0.0.1", 9999)
        print("Server started! Connect to ws://127.0.0.1:9999")
        await server.wait_closed()
    except Exception as e:
        print(f"Server failed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")