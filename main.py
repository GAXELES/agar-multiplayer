
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
        self.foods = [self.create_food() for _ in range(400)]
        self.bots_initialized = False

    def create_food(self):
        return {
            "x": random.randint(20, MAP_WIDTH - 20),
            "y": random.randint(20, MAP_HEIGHT - 20),
            "radius": 5,
            "color": f"hsl({random.randint(0, 360)}, 80%, 60%)"
        }

    def spawn_bots(self, count=10):
        for i in range(count):
            bot_id = f"bot_{i}"
            if bot_id not in self.players:
                self.players[bot_id] = {
                    "id": bot_id,
                    "x": random.randint(200, MAP_WIDTH - 200),
                    "y": random.randint(200, MAP_HEIGHT - 200),
                    "radius": random.randint(20, 35),
                    "color": f"hsl({random.randint(0, 360)}, 70%, 50%)",
                    "name": f"[Bot] {i+1}",
                    "is_bot": True,
                    "dir_x": random.choice([-1, 1]),
                    "dir_y": random.choice([-1, 1])
                }

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.active_connections[player_id] = websocket

    def add_player(self, player_id: str, name: str, mode: str):
        self.players[player_id] = {
            "id": player_id,
            "x": random.randint(300, MAP_WIDTH - 300),
            "y": random.randint(300, MAP_HEIGHT - 300),
            "radius": 25,
            "color": f"hsl({random.randint(0, 360)}, 90%, 55%)",
            "name": name,
            "is_bot": False
        }

        if mode == "bots" and not self.bots_initialized:
            self.spawn_bots(15)
            self.bots_initialized = True

    def disconnect(self, player_id: str):
        if player_id in self.active_connections:
            del self.active_connections[player_id]
        if player_id in self.players:
            del self.players[player_id]

    def update_game_logic(self):
        # Actualizar Bots
        for p in self.players.values():
            if p.get("is_bot"):
                speed = max(1.5, 5 - (p["radius"] * 0.02))
                if random.random() < 0.02:
                    p["dir_x"] = random.choice([-1, 0, 1])
                    p["dir_y"] = random.choice([-1, 0, 1])

                p["x"] += p["dir_x"] * speed
                p["y"] += p["dir_y"] * speed

                p["x"] = max(p["radius"], min(MAP_WIDTH - p["radius"], p["x"]))
                p["y"] = max(p["radius"], min(MAP_HEIGHT - p["radius"], p["y"]))

        # Lógica de consumo de comida
        for p in list(self.players.values()):
            for food in self.foods[:]:
                dist = math.hypot(p["x"] - food["x"], p["y"] - food["y"])
                if dist < p["radius"]:
                    self.foods.remove(food)
                    p["radius"] += 0.5
                    self.foods.append(self.create_food())

    def update_player_input(self, player_id: str, keys: dict):
        if player_id not in self.players:
            return

        p = self.players[player_id]
        speed = max(2.5, 7 - (p["radius"] * 0.03))

        # Teclas: W (Arriba), S (Abajo), A (Izquierda), D (Derecha)
        if keys.get("w"): p["y"] -= speed
        if keys.get("s"): p["y"] += speed
        if keys.get("a"): p["x"] -= speed
        if keys.get("d"): p["x"] += speed

        p["x"] = max(p["radius"], min(MAP_WIDTH - p["radius"], p["x"]))
        p["y"] = max(p["radius"], min(MAP_HEIGHT - p["radius"], p["y"]))

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
            if data.get("type") == "join":
                game.add_player(player_id, data.get("name", "Jugador"), data.get("mode", "online"))
                await websocket.send_json({"type": "init", "id": player_id})
            elif data.get("type") == "input":
                game.update_player_input(player_id, data.get("keys", {}))

            game.update_game_logic()
            await game.broadcast()
            await asyncio.sleep(0.016)
    except WebSocketDisconnect:
        game.disconnect(player_id)
        await game.broadcast()
