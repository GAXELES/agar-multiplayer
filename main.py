<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Juego Agar.io Multijugador</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            overflow: hidden;
            background-color: #111;
            font-family: Arial, sans-serif;
            color: white;
        }
        #gameCanvas {
            display: block;
        }
        #ui {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0, 0, 0, 0.7);
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
            pointer-events: none;
        }
    </style>
</head>
<body>
    <div id="ui">
        <div><strong>Jugadores en línea:</strong> <span id="playerCount">0</span></div>
        <div>Masa: <span id="playerSize">0</span></div>
        <div>Controles: <strong>W</strong> (Arriba), <strong>S</strong> (Abajo), <strong>A</strong> (Izquierda), <strong>D</strong> (Derecha)</div>
    </div>

    <canvas id="gameCanvas"></canvas>

    <script>
        const canvas = document.getElementById("gameCanvas");
        const ctx = canvas.getContext("2d");

        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;

        window.addEventListener("resize", () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        });

        const MAP_WIDTH = 3000;
        const MAP_HEIGHT = 3000;

        const keys = { w: false, a: false, s: false, d: false };

        window.addEventListener("keydown", (e) => {
            const k = e.key.toLowerCase();
            if (k in keys) keys[k] = true;
        });

        window.addEventListener("keyup", (e) => {
            const k = e.key.toLowerCase();
            if (k in keys) keys[k] = false;
        });

        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${protocol}//${location.host}/ws`);

        let players = {};
        let foods = [];
        let myId = null;

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "init") {
                myId = data.id;
            } else if (data.type === "state") {
                players = data.players || {};
                foods = data.foods || [];
                document.getElementById("playerCount").innerText = Object.keys(players).length;
                if (myId && players[myId]) {
                    document.getElementById("playerSize").innerText = Math.round(players[myId].radius);
                }
            }
        };

        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(keys));
            }
        }, 1000 / 60);

        function drawGrid(me) {
            ctx.strokeStyle = "#222";
            ctx.lineWidth = 1;
            const gridSize = 60;

            const startX = Math.floor((me.x - canvas.width / 2) / gridSize) * gridSize;
            const endX = startX + canvas.width + gridSize * 2;
            const startY = Math.floor((me.y - canvas.height / 2) / gridSize) * gridSize;
            const endY = startY + canvas.height + gridSize * 2;

            for (let x = startX; x < endX; x += gridSize) {
                ctx.beginPath();
                ctx.moveTo(x, startY);
                ctx.lineTo(x, endY);
                ctx.stroke();
            }
            for (let y = startY; y < endY; y += gridSize) {
                ctx.beginPath();
                ctx.moveTo(startX, y);
                ctx.lineTo(endX, y);
                ctx.stroke();
            }
        }

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const me = players[myId];

            if (me) {
                ctx.save();
                ctx.translate(canvas.width / 2 - me.x, canvas.height / 2 - me.y);

                drawGrid(me);

                // Borde rojo del mapa grande
                ctx.strokeStyle = "#ff0000";
                ctx.lineWidth = 8;
                ctx.strokeRect(0, 0, MAP_WIDTH, MAP_HEIGHT);

                // Dibujar puntos de comida
                foods.forEach(food => {
                    ctx.beginPath();
                    ctx.arc(food.x, food.y, food.radius || 5, 0, Math.PI * 2);
                    ctx.fillStyle = food.color || "#00ff00";
                    ctx.fill();
                    ctx.closePath();
                });

                // Dibujar jugadores
                Object.values(players).forEach(player => {
                    ctx.beginPath();
                    ctx.arc(player.x, player.y, player.radius, 0, Math.PI * 2);
                    ctx.fillStyle = player.color || "#00ccff";
                    ctx.fill();
                    ctx.closePath();

                    if (player.id === myId) {
                        ctx.strokeStyle = "#ffffff";
                        ctx.lineWidth = 4;
                        ctx.stroke();
                    }

                    ctx.fillStyle = "#ffffff";
                    ctx.font = "bold 14px Arial";
                    ctx.textAlign = "center";
                    ctx.fillText(player.name, player.x, player.y - player.radius - 8);
                });

                ctx.restore();
            }

            requestAnimationFrame(draw);
        }

        draw();
    </script>
</body>
</html>
