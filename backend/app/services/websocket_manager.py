from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._socket_matches: dict[WebSocket, int] = {}

    async def connect(self, user_id: int, match_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)
        self._socket_matches[websocket] = match_id

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        self._socket_matches.pop(websocket, None)
        if not sockets:
            self._connections.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))

    def is_in_match(self, user_id: int, match_id: int) -> bool:
        return any(self._socket_matches.get(socket) == match_id for socket in self._connections.get(user_id, set()))

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        stale: list[WebSocket] = []
        for socket in list(self._connections.get(user_id, set())):
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.disconnect(user_id, socket)

    async def send_to_users(self, user_ids: set[int], payload: dict) -> None:
        for user_id in user_ids:
            await self.send_to_user(user_id, payload)


manager = ConnectionManager()
