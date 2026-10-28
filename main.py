import random
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

class GameServer:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.players = {}
        self.foods = [
            {
                "x": random.randint(20, 1800),
                "y": random.randint(20, 900),
                "color": f"hsl({random.randint(0, 360)}, 70%, 50%)"
            }
            for _ in range(50)
        ]

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.active_connections[player_id] = websocket
        self.players[player_id] = {
            "x": random.randint(100, 800),
            "y": random.randint(100, 600),
            "radius": 20,
            "color": f"hsl({random.randint(0, 360)}, 80%, 60%)",
            "name": f"Jugador {len(self.players) + 1}"
        }

    def disconnect(self, player_id: str):
        if player_id in self.active_connections:
            del self.active_connections[player_id]
        if player_id in self.players:
            del self.players[player_id]

    async def broadcast(self):
        state = {
            "type": "state",
            "players": self.players,
            "foods": self.foods
        }
        for connection in list(self.active_connections.values()):
            try:
                await connection.send_json(state)
            except Exception:
                pass

    def update_player_pos(self, player_id: str, x: int, y: int):
        if player_id in self.players:
            self.players[player_id]["x"] = x
            self.players[player_id]["y"] = y

game = GameServer()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    player_id = str(id(websocket))
    await game.connect(websocket, player_id)
    try:
        while True:
            data = await websocket.receive_json()
            game.update_player_pos(player_id, data.get("x", 0), data.get("y", 0))
            await game.broadcast()
    except WebSocketDisconnect:
        game.disconnect(player_id)
        await game.broadcast()
    
