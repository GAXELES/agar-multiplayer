import asyncio, json, math, os, random, re, string, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

W, H = 3000, 3000
FOOD_TARGET = 260
MAX_CELLS = 16
TICK = 1 / 30
ROOM_RE = re.compile(r"^[A-Z0-9]{4,8}$")
rooms = {}

def rand_food():
    return {"x": random.uniform(15, W-15), "y": random.uniform(15, H-15), "mass": random.uniform(1.2, 2.5), "color": random.choice(["#ffcf5a", "#f879a8", "#6ee7b7", "#b8a2ff", "#64d8ff", "#ff9966"])}

def new_room():
    rid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    while rid in rooms: rid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    rooms[rid] = {"players": {}, "food": [rand_food() for _ in range(FOOD_TARGET)], "created": time.time()}
    return rid

def rad(m): return math.sqrt(max(1, m)) * 4.0
def clamp(v, lo, hi): return max(lo, min(hi, v))
def distance(a,b): return math.hypot(a["x"]-b["x"], a["y"]-b["y"])
def total_mass(p): return sum(c["mass"] for c in p["cells"])
def new_player(pid, name, ws):
    x, y = random.uniform(250, W-250), random.uniform(250, H-250)
    return {"id":pid, "name":name[:18] or "Jugador", "ws":ws, "cells":[{"x":x,"y":y,"mass":25,"vx":0,"vy":0,"boost":0,"merge":0}], "input":{"x":0,"y":0,"aimx":1,"aimy":0,"split":False}, "color":random.choice(["#35d6f5", "#ff6b8a", "#8be36b", "#ffc857", "#b69cff", "#ff9f68", "#68a7ff"]), "last_split":0}

def clean_state(room):
    out_players=[]
    for p in room["players"].values():
        out_players.append({"id":p["id"],"name":p["name"],"color":p["color"],"mass":round(total_mass(p)),"cells":[{"x":round(c["x"],1),"y":round(c["y"],1),"mass":round(c["mass"],1)} for c in p["cells"]]})
    out_players.sort(key=lambda p:p["mass"], reverse=True)
    return {"type":"state","world":{"w":W,"h":H},"food":room["food"],"players":out_players,"ranking":[{"name":p["name"],"mass":p["mass"]} for p in out_players[:10]]}

async def send_json(ws, obj):
    await ws.send_text(json.dumps(obj, separators=(",", ":")))

async def game_loop(rid, room):
    last = time.monotonic()
    last_broadcast = 0.0
    try:
        while rooms.get(rid) is room:
            now = time.monotonic(); dt = min(now-last, 0.05); last = now
            players = list(room["players"].values())
            # Movement is calculated on the server, not trusted to clients.
            for p in players:
                inp=p["input"]
                if inp.get("split"):
                    inp["split"] = False
                    if len(p["cells"]) < MAX_CELLS and now-p["last_split"] > 0.18:
                        additions=[]
                        for c in list(p["cells"]):
                            if len(p["cells"])+len(additions)>=MAX_CELLS: break
                            if c["mass"] < 36: continue
                            half=c["mass"]/2; c["mass"]=half; c["merge"]=8
                            ux,uy=inp.get("aimx",1),inp.get("aimy",0); ln=math.hypot(ux,uy) or 1; ux/=ln; uy/=ln
                            additions.append({"x":clamp(c["x"]+ux*rad(half)*1.5,rad(half),W-rad(half)),"y":clamp(c["y"]+uy*rad(half)*1.5,rad(half),H-rad(half)),"mass":half,"vx":ux*680,"vy":uy*680,"boost":0.55,"merge":8})
                        p["cells"].extend(additions); p["last_split"]=now
                for c in p["cells"]:
                    speed=clamp(2300/(math.sqrt(c["mass"])+9),70,225)
                    tx=inp.get("x",0)*speed; ty=inp.get("y",0)*speed
                    c["vx"]+=(tx-c["vx"])*min(1,dt*6); c["vy"]+=(ty-c["vy"])*min(1,dt*6)
                    c["x"]+=c["vx"]*dt; c["y"]+=c["vy"]*dt
                    if c["boost"]>0:
                        c["boost"]-=dt; damp=math.pow(0.10,dt); c["vx"]*=damp; c["vy"]*=damp
                    c["x"]=clamp(c["x"],rad(c["mass"]),W-rad(c["mass"]))
                    c["y"]=clamp(c["y"],rad(c["mass"]),H-rad(c["mass"]))
                    c["merge"]=max(0,c["merge"]-dt)
                    # Eat food.
                    for i in range(len(room["food"])-1,-1,-1):
                        f=room["food"][i]
                        if math.hypot(c["x"]-f["x"],c["y"]-f["y"]) < rad(c["mass"])+4:
                            c["mass"]+=f["mass"]*0.85; room["food"].pop(i)
                while len(room["food"])<FOOD_TARGET: room["food"].append(rand_food())
                # Recombine a player's own cells after cooldown.
                for i in range(len(p["cells"])):
                    a=p["cells"][i]
                    for j in range(len(p["cells"])-1,i,-1):
                        b=p["cells"][j]
                        if a["merge"]<=0 and b["merge"]<=0 and distance(a,b)<max(rad(a["mass"]),rad(b["mass"]))*0.62:
                            total=a["mass"]+b["mass"]
                            a["x"]=(a["x"]*a["mass"]+b["x"]*b["mass"])/total
                            a["y"]=(a["y"]*a["mass"]+b["y"]*b["mass"])/total
                            a["mass"]=total; p["cells"].pop(j)
            # Player-vs-player eating. Small cells respawn after being eaten.
            for eater in players:
                if not eater["cells"]:
                    x,y=random.uniform(200,W-200),random.uniform(200,H-200)
                    eater["cells"]=[{"x":x,"y":y,"mass":25,"vx":0,"vy":0,"boost":0,"merge":0}]
                    continue
                for victim in players:
                    if eater is victim or not victim["cells"]: continue
                    for ec in eater["cells"]:
                        for vc in list(victim["cells"]):
                            if ec["mass"] > vc["mass"]*1.16 and distance(ec,vc)<rad(ec["mass"])*0.70:
                                ec["mass"] += vc["mass"]*0.72
                                victim["cells"].remove(vc)
                # Respawn a fully eaten player.
                if not eater["cells"]:
                    x,y=random.uniform(200,W-200),random.uniform(200,H-200)
                    eater["cells"]=[{"x":x,"y":y,"mass":25,"vx":0,"vy":0,"boost":0,"merge":0}]
            # Merge/collision ordering can leave a cell eaten in this tick; broadcast.
            if players and now-last_broadcast >= 1/12:
                last_broadcast = now
                state=clean_state(room)
                dead=[]
                for p in players:
                    try: await send_json(p["ws"], state)
                    except Exception: dead.append(p["id"])
                for pid in dead: room["players"].pop(pid,None)
            await asyncio.sleep(max(0,TICK-(time.monotonic()-now)))
    except asyncio.CancelledError:
        pass

@asynccontextmanager
async def lifespan(app):
    yield
    for room in rooms.values():
        task=room.get("task")
        if task: task.cancel()

app=FastAPI(title="Agar Multiplayer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")

@app.post("/api/rooms")
async def create_room():
    rid=new_room()
    return {"room":rid,"url":f"/?room={rid}"}

@app.get("/health")
async def health(): return {"ok":True,"rooms":len(rooms)}

@app.websocket("/ws/{rid}")
async def websocket_endpoint(ws: WebSocket, rid: str):
    rid=rid.upper()
    if not ROOM_RE.fullmatch(rid):
        await ws.close(code=1008); return
    await ws.accept()
    if rid not in rooms:
        # Joining an unused valid code creates a room, useful for manual room codes.
        rooms[rid]={"players":{},"food":[rand_food() for _ in range(FOOD_TARGET)],"created":time.time()}
    room=rooms[rid]
    if len(room["players"])>=24:
        await send_json(ws,{"type":"error","message":"La sala está llena (máximo 24 jugadores)."})
        await ws.close(code=1008); return
    if "task" not in room or room["task"].done(): room["task"]=asyncio.create_task(game_loop(rid,room))
    pid=''.join(random.choices(string.ascii_lowercase+string.digits,k=10))
    name=ws.query_params.get("name","Jugador")[:18].strip() or "Jugador"
    p=new_player(pid,name,ws); room["players"][pid]=p
    await send_json(ws,{"type":"welcome","id":pid,"room":rid,"name":name})
    try:
        while True:
            msg=json.loads(await ws.receive_text())
            if msg.get("type")=="input":
                inp=p["input"]
                x=float(msg.get("x",0)); y=float(msg.get("y",0))
                ln=math.hypot(x,y)
                if ln>1: x/=ln; y/=ln
                inp["x"]=clamp(x,-1,1); inp["y"]=clamp(y,-1,1)
                ax=float(msg.get("aimx",1)); ay=float(msg.get("aimy",0)); al=math.hypot(ax,ay) or 1
                inp["aimx"]=clamp(ax/al,-1,1); inp["aimy"]=clamp(ay/al,-1,1)
                if msg.get("split"): inp["split"]=True
    except (WebSocketDisconnect, ValueError, json.JSONDecodeError):
        pass
    finally:
        room["players"].pop(pid,None)
        if not room["players"]:
            task=room.get("task")
            if task: task.cancel()
            rooms.pop(rid,None)
