import random
import math
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

MAP_WIDTH = 3000
MAP_HEIGHT = 3000

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

class GameServer:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.players = {}
        self.foods = [self.create_food() for _ in range(300)]

    def create_food(self):
        return {
            "x": random.randint(20, MAP_WIDTH - 20),
            "y": random.randint(20, MAP_HEIGHT - 20),
            "radius": 5,
            "color": f"hsl({random.randint(0, 360)}, 80%, 60%)"
        }

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.active_connections[player_id] = websocket
        self.players[player_id] = {
            "x": random.randint(100, MAP_WIDTH - 100),
            "y": random.randint(100, MAP_HEIGHT - 100),
            "radius": 20,
            "speed": 5,
            "color": f"hsl({random.randint(0, 360)}, 90%, 55%)",
            "name": f"Jugador {len(self.players) + 1}"
        }
        await websocket.send_json({"type": "init", "id": player_id})

    def disconnect(self, player_id: str):
        if player_id in self.active_connections:
            del self.active_connections[player_id]
        if player_id in self.players:
            del self.players[player_id]

    def update_player_input(self, player_id: str, keys: dict):
        if player_id not in self.players:
            return

        p = self.players[player_id]
        speed = max(2, 8 - (p["radius"] * 0.05)) # A mayor tamaño, menor velocidad

        if keys.get("w"): p["y"] -= speed
        if keys.get("s"): p["y"] += speed
        if keys.get("a"): p["x"] -= speed
        if keys.get("d"): p["x"] += speed

        # Limitar dentro del mapa
        p["x"] = max(p["radius"], min(MAP_WIDTH - p["radius"], p["x"]))
        p["y"] = max(p["radius"], min(MAP_HEIGHT - p["radius"], p["y"]))

        # Lógica para comer comida
        for food in self.foods[:]:
            dist = math.hypot(p["x"] - food["x"], p["y"] - food["y"])
            if dist < p["radius"]:
                self.foods.remove(food)
                p["radius"] += 0.4
                self.foods.append(self.create_food())

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

game = GameServer()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    player_id = str(id(websocket))
    await game.connect(websocket, player_id)
    try:
        while True:
            data = await websocket.receive_json()
            game.update_player_input(player_id, data)
            await game.broadcast()
            await asyncio.sleep(0.016) # ~60 FPS
    except WebSocketDisconnect:
        game.disconnect(player_id)
        await game.broadcast()
      
          
