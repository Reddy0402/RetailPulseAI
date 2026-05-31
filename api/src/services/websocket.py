from fastapi import WebSocket
from typing import List
from src.utils.logger import logger

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New dashboard WebSocket client connected", {
            "active_connections_count": len(self.active_connections)
        })

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Dashboard WebSocket client disconnected", {
                "active_connections_count": len(self.active_connections)
            })

    async def broadcast(self, message: dict):
        """
        Pushes a real-time event/metric update payload to all active browser dashboard clients.
        """
        logger.debug(f"Broadcasting websocket message: {message}")
        disconnected_sockets = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send JSON to websocket: {e}")
                disconnected_sockets.append(connection)

        # Cleanup dead sockets
        for socket in disconnected_sockets:
            self.disconnect(socket)

websocket_manager = WebSocketManager()
