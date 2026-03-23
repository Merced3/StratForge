from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from typing import List
import asyncio
from shared_state import print_log

app = FastAPI()

# Store active WebSocket connections
# clients: List[WebSocket] = []
clients = set()
#clients: set[WebSocket] = set() # top-level

@app.websocket("/ws/chart-updates")
async def chart_updates(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try: # Send one “kick” per TF so Dash callbacks render right away
        for tf in ["2M", "5M", "15M", "zones"]:
            await websocket.send_text(f"chart:{tf}")
        while True:
            await asyncio.sleep(60*60)  # keepalive
    except WebSocketDisconnect:
        clients.discard(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        clients.discard(websocket)

@app.post("/trigger-chart-update")
async def trigger_chart_update(data: dict):
    tfs = data.get("timeframes") or data.get("timeframe") or ["2M"]
    if isinstance(tfs, str):
        tfs = [tfs]
    dead = set()
    for ws in list(clients): # snapshot
        for tf in tfs:
            try:
                await ws.send_text(f"chart:{tf}")
            except Exception:
                dead.add(ws)
                break
    for ws in dead:
        clients.discard(ws)
    return JSONResponse({"status":"broadcasted","timeframes":tfs,"clients":len(clients)})

@app.post("/refresh-chart")
async def refresh_chart(req: Request):
    data = await req.json()
    timeframe  = data.get("timeframe", "2M")
    chart_type = data.get("chart_type", "live")  # "live" or "zones"

    # 1) Broadcast first so UI updates immediately
    tfs = ["zones"] if chart_type == "zones" else [timeframe]
    dead = set()
    for ws in list(clients):           # snapshot
        for tf in tfs:
            try:
                await ws.send_text(f"chart:{tf}")
            except Exception:
                dead.add(ws)
                break
    for ws in dead:
        clients.discard(ws)

    # 2) Save PNG in the background (non-blocking)
    async def _save():
        from web_dash.chart_updater import update_chart
        try:
            await asyncio.to_thread(update_chart, timeframe=timeframe, chart_type=chart_type, notify=False)
        except Exception as exc:
            print_log(f"[refresh_chart] background save failed for {chart_type}:{timeframe}: {exc}")
    asyncio.create_task(_save())

    return JSONResponse({"status": "saved-and-broadcast", "timeframes": tfs, "clients": len(clients)})
