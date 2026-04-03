import httpx
import asyncio
import math
import random

API_URL="http://localhost:8000/api/v1/ingest/telemetry"
DRONE_ID="drone-1"

async def simulate():
    async with httpx.AsyncClient() as client:
        t = 0
        while True:
            battery = max(20, 100 - t * 0.1)
            payload = {
                "drone_id": DRONE_ID,
                "lat": 28.6139 + 0.001 * math.sin(t * 0.1),
                "lon": 77.2090 + 0.001 * math.cos(t * 0.1),
                "alt": 40 + 10 * math.sin(t * 0.05),
                "speed": 8 + 4 * random.random(),
                "heading": int((math.degrees(math.atan2(math.cos(t * 0.1), -math.sin(t * 0.1))) + 360) % 360),
                "battery": battery,
                "voltage": round(14.0 + (battery / 100) * 2.8, 2),
                "armed": False,
                "flight_mode": "STABILIZE",
                "gps_fix_type": 3,
                "satellites": random.randint(6, 12),
            }

            try:
                await client.post(API_URL, json=payload)
                print(f"t={t}: alt={payload['alt']:.1f}m  spd={payload['speed']:.1f}m/s bat={payload['battery']:.1f}%")
            except httpx.ConnectError:
                print("Server not reachable, retrying")
        
            t += 1
            await asyncio.sleep(1)

asyncio.run(simulate())