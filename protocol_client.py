# mqtt_client.py
import asyncio, os, time, json, sys
from asyncio_mqtt import Client

ID = os.environ.get("ID","1")
FREQ = float(os.environ.get("FREQ","1.0"))
BROKER = os.environ.get("BROKER","localhost")
PROTO = os.environ.get("PROTO","mqtt")  # mqtt / http / coap
HTTP_URL = os.environ.get("HTTP_URL","http://localhost:5000/post")
COAP_HOST = os.environ.get("COAP_HOST","localhost")
COAP_PORT = int(os.environ.get("COAP_PORT","5683"))
COAP_RESOURCE = os.environ.get("COAP_RESOURCE","sensors")

def log(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

async def mqtt_loop():
    async with Client(BROKER, 1883) as client:
        while True:
            payload = {"id": ID, "ts": time.time(), "val": 42}
            await client.publish(f"sensors/{ID}", json.dumps(payload))
            log(f"MQTT SENT id={ID} ts={payload['ts']:.6f}")
            await asyncio.sleep(FREQ)

async def coap_loop():
    from aiocoap import Message, Context, Code
    protocol = await Context.create_client_context()
    uri = f"coap://{COAP_HOST}:{COAP_PORT}/{COAP_RESOURCE}"
    log(f"COAP LOOP START id={ID} uri={uri}")
    while True:
        payload = {"id": ID, "ts": time.time(), "val": 42}
        request = Message(code=Code.POST, uri=uri, payload=json.dumps(payload).encode())
        t0 = time.time()
        try:
            resp = await protocol.request(request).response
            t1 = time.time()
            rtt = t1 - t0
            log(f"METRIC RTT coap id={ID} ts={t1:.6f} rtt={rtt:.6f}")
        except Exception as e:
            log(f"ERR COAP id={ID} {e}")
        await asyncio.sleep(FREQ)

if __name__ == "__main__":
    if PROTO == "http":
        import requests
        log(f"HTTP LOOP START id={ID} url={HTTP_URL}")
        while True:
            payload = {"id": ID, "ts": time.time(), "val": 42}
            t0 = time.time()
            try:
                r = requests.post(HTTP_URL, json=payload, timeout=5)
                t1 = time.time()
                rtt = t1 - t0
                log(f"METRIC RTT http id={ID} ts={t1:.6f} rtt={rtt:.6f} status={r.status_code}")
            except Exception as e:
                log(f"ERR HTTP id={ID} {e}")
            time.sleep(FREQ)
    elif PROTO == "coap":
        asyncio.run(coap_loop())
    else:
        asyncio.run(mqtt_loop())
