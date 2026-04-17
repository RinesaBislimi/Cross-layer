from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        for connection in self.active_connections:
            await connection.send_json(message)


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
