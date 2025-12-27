import asyncio
import json
import logging
import os
import sys
import time

from aiocoap import Message, Context, resource, Code, error as aiocoap_error
from dotenv import load_dotenv

load_dotenv()
AUTH_MODE = os.environ.get("AUTH_MODE", "open")
API_TOKEN = os.environ.get("API_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class SensorResource(resource.Resource):
    async def render_post(self, request: Message) -> Message:
        payload = request.payload.decode() if request.payload else ""
        try:
            data = json.loads(payload)
            if AUTH_MODE == "auth":
                q = (request.opt.uri_query or [])
                token = ""
                for item in q:
                    if item.startswith("token="):
                        token = item.split("=", 1)[1]
                        break
                if token != API_TOKEN:
                    logging.info("Unauthorized CoAP (bad token)")
                    return Message(code=Code.UNAUTHORIZED, payload=b"UNAUTHORIZED")

        except Exception:
            data = payload
        logging.info("Received CoAP POST: %s", data)
        return Message(code=Code.CHANGED, payload=b"OK")


class Root(resource.Site):
    def __init__(self):
        super().__init__()
        self.add_resource(("sensors",), SensorResource())


async def main():
    site = Root()
    bind_host = os.environ.get("COAP_BIND", "0.0.0.0")
    bind_port = int(os.environ.get("COAP_PORT", "5683"))
    try:
        await Context.create_server_context(site, bind=(bind_host, bind_port))
    except aiocoap_error.ResolutionError as exc:
        if bind_host != "0.0.0.0":
            logging.warning(
                "Failed to bind to %s (%s), retrying on 0.0.0.0", bind_host, exc
            )
            bind_host = "0.0.0.0"
            await Context.create_server_context(site, bind=(bind_host, bind_port))
        else:
            raise
    logging.info("CoAP server listening on udp/%s (bind %s)", bind_port, bind_host)
    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
