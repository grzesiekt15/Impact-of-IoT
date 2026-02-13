# protocol_client.py
import asyncio, os, time, json, sys
from asyncio_mqtt import Client

from write_results import write_metric
import os
# from dotenv import load_dotenv

# load_dotenv()
API_TOKEN = os.environ.get("API_TOKEN")
AUTH_MODE = os.environ.get("AUTH_MODE")
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASS = os.environ.get("MQTT_PASS")

ID = os.environ.get("ID", "1")
FREQ = float(os.environ.get("FREQ", "1.0"))
BROKER = os.environ.get("BROKER", "127.0.0.1")
PROTO = os.environ.get("PROTO", "mqtt")  # mqtt / http / coap
HTTP_URL = os.environ.get("HTTP_URL", "http://127.0.0.1:5000/post")
COAP_HOST = os.environ.get("COAP_HOST", "127.0.0.1")
COAP_PORT = int(os.environ.get("COAP_PORT", "5683"))
COAP_RESOURCE = os.environ.get("COAP_RESOURCE", "sensors")
MAX_SAMPLES = int(os.environ.get("MAX_SAMPLES", "0"))

# wyniki
RUN_ID = os.environ.get("RUN_ID", "run")
OUT_DIR = os.environ.get("OUT_DIR", "/results")
CSV_PATH = os.path.join(OUT_DIR, f"metrics_{RUN_ID}_{PROTO}_id{ID}.csv")
START_FILE = os.environ.get("START_FILE")
START_FILE_TIMEOUT = float(os.environ.get("START_FILE_TIMEOUT", "300"))
READY_FILE = os.environ.get("READY_FILE")
STOP_FILE = os.environ.get("STOP_FILE")

def log(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

def emit(ts, rtt=None, status="", error=""):
    write_metric(CSV_PATH, RUN_ID, PROTO, ID, ts, rtt=rtt, status=status, error=error)

def write_ready_file():
    if not READY_FILE:
        return
    try:
        with open(READY_FILE, "w", encoding="utf-8") as f:
            f.write(f"{ID}\\n")
        log(f"READY_FILE written: {READY_FILE}")
    except Exception as e:
        log(f"READY_FILE write failed: {e}")

def wait_for_start_file():
    if not START_FILE:
        return
    log(f"WAIT FOR START_FILE={START_FILE} timeout={START_FILE_TIMEOUT}s")
    start = time.time()
    while True:
        if os.path.exists(START_FILE):
            log("START_FILE detected, begin traffic")
            return
        if START_FILE_TIMEOUT > 0 and time.time() - start > START_FILE_TIMEOUT:
            log("START_FILE timeout, begin traffic anyway")
            return
        time.sleep(0.2)

def should_stop() -> bool:
    return bool(STOP_FILE) and os.path.exists(STOP_FILE)

def http_loop():
    import requests
    log(f"HTTP LOOP START id={ID} url={HTTP_URL}")
    samples = 0
    while True:
        if should_stop():
            log(f"HTTP LOOP STOP id={ID} stop_file={STOP_FILE}")
            return
        if MAX_SAMPLES > 0 and samples >= MAX_SAMPLES:
            log(f"HTTP LOOP DONE id={ID} samples={samples}")
            return
        payload = {"id": ID, "ts": time.time(), "val": 42}
        t0 = time.time()
        try:
            headers = {}
            if AUTH_MODE == "auth":
                headers["Authorization"] = f"Bearer {API_TOKEN}"
            r = requests.post(HTTP_URL, json=payload, headers=headers, timeout=5)
            t1 = time.time()
            rtt = t1 - t0
            log(f"METRIC RTT http id={ID} ts={t1:.6f} rtt={rtt:.6f} status={r.status_code}")
            emit(t1, rtt=rtt, status=str(r.status_code))
        except Exception as e:
            log(f"ERR HTTP id={ID} {e}")
            emit(time.time(), error=str(e))
        samples += 1
        time.sleep(FREQ)

def mqtt_loop():
    import paho.mqtt.client as mqtt

    topic = f"sensors/{ID}"
    log(f"MQTT LOOP START id={ID} broker={BROKER}")
    samples = 0

    def on_connect(client, userdata, flags, rc):
        client.subscribe(topic)

    def on_message(client, userdata, msg):
        try:
            t1 = time.time()
            data = json.loads(msg.payload.decode())
            t0 = float(data.get("t0", t1))
            rtt = t1 - t0
            log(f"METRIC RTT mqtt id={ID} ts={t1:.6f} rtt={rtt:.6f}")
            emit(t1, rtt=rtt, status="OK")
        except Exception as e:
            emit(time.time(), error=str(e))

    client = mqtt.Client()
    if AUTH_MODE == "auth":
        client.username_pw_set(MQTT_USER, MQTT_PASS) 
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=5)

    while True:
        try:
            client.connect(BROKER, 1883, 60)
            break
        except Exception as e:
            # Keep retrying instead of exiting the container when the broker is down
            log(f"MQTT connect failed id={ID} broker={BROKER}: {e}")
            emit(time.time(), error=f"mqtt_connect_failed:{e}")
            time.sleep(2)

    client.loop_start()

    while True:
        if should_stop():
            log(f"MQTT LOOP STOP id={ID} stop_file={STOP_FILE}")
            client.loop_stop()
            client.disconnect()
            return
        if MAX_SAMPLES > 0 and samples >= MAX_SAMPLES:
            log(f"MQTT LOOP DONE id={ID} samples={samples}")
            client.loop_stop()
            client.disconnect()
            return
        t0 = time.time()
        info = client.publish(topic, json.dumps({"id": ID, "t0": t0}))
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log(f"MQTT publish failed id={ID} rc={info.rc}")
            emit(time.time(), error=f"mqtt_publish_failed:{info.rc}")
        samples += 1
        time.sleep(FREQ)


async def coap_loop():
    from aiocoap import Message, Context, Code
    protocol = await Context.create_client_context()
    base_uri = f"coap://{COAP_HOST}:{COAP_PORT}/{COAP_RESOURCE}"
    log(f"COAP LOOP START id={ID} uri={base_uri}")
    samples = 0
    while True:
        if should_stop():
            log(f"COAP LOOP STOP id={ID} stop_file={STOP_FILE}")
            return
        if MAX_SAMPLES > 0 and samples >= MAX_SAMPLES:
            log(f"COAP LOOP DONE id={ID} samples={samples}")
            return
        payload = {"id": ID, "ts": time.time(), "val": 42}
        uri = base_uri
        if AUTH_MODE == "auth" and API_TOKEN:
            uri = f"{base_uri}?token={API_TOKEN}"

        request = Message(code=Code.POST, uri=uri, payload=json.dumps(payload).encode())
        t0 = time.time()
        try:
            _ = await protocol.request(request).response
            t1 = time.time()
            rtt = t1 - t0
            log(f"METRIC RTT coap id={ID} ts={t1:.6f} rtt={rtt:.6f}")
            emit(t1, rtt=rtt, status="OK")
        except Exception as e:
            log(f"ERR COAP id={ID} {e}")
            emit(time.time(), error=str(e))
        samples += 1
        await asyncio.sleep(FREQ)

if __name__ == "__main__":
    log(f"CLIENT START id={ID} proto={PROTO} freq={FREQ} run_id={RUN_ID} out={OUT_DIR}")
    write_ready_file()
    wait_for_start_file()

    if PROTO == "http":
        http_loop()
    elif PROTO == "coap":
        asyncio.run(coap_loop())
    else:
        mqtt_loop()
