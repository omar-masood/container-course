from flask import Flask
import redis
import os
import socket

app = Flask(__name__)

cache = redis.Redis(
    host=os.environ.get("REDIS_HOST", "redis"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
)


@app.route("/")
def home():
    count = cache.incr("hits")
    hostname = socket.gethostname()
    return f"Welcome! You are visitor number {count}.\nHostname: {hostname}\n"


@app.route("/health")
def health():
    try:
        cache.ping()
        return {"status": "healthy", "redis": "connected"}
    except redis.ConnectionError:
        return {"status": "unhealthy", "redis": "disconnected"}, 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
