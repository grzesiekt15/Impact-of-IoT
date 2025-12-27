from flask import Flask, request
import os
# from dotenv import load_dotenv
# load_dotenv()

AUTH_MODE = os.environ.get("AUTH_MODE", "open")
API_TOKEN = os.getenv("API_TOKEN")
app = Flask(__name__)

@app.route("/post", methods=["POST"])
def p():
    if AUTH_MODE == "auth":
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {API_TOKEN}"
        if auth != expected:
            return "Unauthorized", 401

    # tutaj możesz potem dodać logowanie payloadu jeśli chcesz
    return "OK", 200

if __name__ == "__main__":
    # serwer HTTP będzie nasłuchiwał na 0.0.0.0:5000
    app.run(host="0.0.0.0", port=5000)
