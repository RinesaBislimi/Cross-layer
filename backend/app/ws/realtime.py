import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        # Capture the running event loop so background threads can post to it
        self._loop = asyncio.get_event_loop()

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for c in dead:
            self.disconnect(c)

    def broadcast_sync(self, message: dict) -> None:
        """Thread-safe broadcast — safe to call from any background thread."""
        if not self.active_connections:
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.debug("WS broadcast_sync: no running event loop — skipping")
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)


manager = ConnectionManager()


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json({"message": "connected"})
        while True:
            # Lexon mesazhe nga klienti (opsionale)
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
