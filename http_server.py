from flask import Flask, request

app = Flask(__name__)

@app.route("/post", methods=["POST"])
def p():
    # tutaj możesz potem dodać logowanie payloadu jeśli chcesz
    return "OK", 200

if __name__ == "__main__":
    # serwer HTTP będzie nasłuchiwał na 0.0.0.0:5000
    app.run(host="0.0.0.0", port=5000)
