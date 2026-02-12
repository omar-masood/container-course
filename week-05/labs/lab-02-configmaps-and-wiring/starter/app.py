from flask import Flask
import os
import socket
import redis

app = Flask(__name__)

# Application config
GREETING = os.environ.get("GREETING", "Hello")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
STUDENT_NAME = os.environ.get("STUDENT_NAME", "YOUR_NAME_HERE")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "YOUR_GITHUB_USERNAME")
APP_VERSION = os.environ.get("APP_VERSION", "v5")

# Kubernetes Downward API fields
POD_NAME = os.environ.get("POD_NAME", socket.gethostname())
POD_NAMESPACE = os.environ.get("POD_NAMESPACE", "unknown")
NODE_NAME = os.environ.get("NODE_NAME", "unknown")
POD_IP = os.environ.get("POD_IP", "unknown")

# Redis configuration — read from environment (ConfigMap + Secret)
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")

# Connect to Redis
def get_redis():
    """Create a Redis connection. Returns None if Redis is unavailable."""
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        r.ping()
        return r
    except (redis.ConnectionError, redis.TimeoutError):
        return None

@app.route("/")
def home():
    r = get_redis()
    visit_count = "unavailable"
    if r:
        visit_count = r.incr(f"visits:{GITHUB_USERNAME}")

    return f"""
    <html>
    <head>
        <title>{STUDENT_NAME}'s App</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); max-width: 600px; }}
            h1 {{ color: #326CE5; }}
            .info {{ background: #e8f0fe; padding: 15px; border-radius: 5px; margin-top: 20px; }}
            .info p {{ margin: 5px 0; }}
            code {{ background: #263238; color: #80cbc4; padding: 2px 6px; border-radius: 3px; }}
            .redis {{ background: #fce4ec; padding: 15px; border-radius: 5px; margin-top: 15px; }}
            .redis.connected {{ background: #e8f5e9; }}
            .nav {{ margin-top: 20px; }}
            .nav a {{ display: inline-block; margin-right: 10px; padding: 8px 16px; background: #326CE5; color: white; text-decoration: none; border-radius: 5px; }}
            .nav a:hover {{ background: #1a4db0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{GREETING} from Kubernetes! ☸️</h1>
            <div class="info">
                <p><strong>Student:</strong> {STUDENT_NAME}</p>
                <p><strong>Version:</strong> <code>{APP_VERSION}</code></p>
                <p><strong>Environment:</strong> {ENVIRONMENT}</p>
                <p><strong>Pod:</strong> <code>{POD_NAME}</code></p>
            </div>
            <div class="redis {'connected' if r else ''}">
                <p><strong>Redis:</strong> {'🟢 Connected' if r else '🔴 Disconnected'}</p>
                <p><strong>Visits:</strong> {visit_count}</p>
            </div>
            <div class="nav">
                <a href="/info">/info</a>
                <a href="/visits">/visits</a>
                <a href="/health">/health</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/visits")
def visits():
    """Visit counter backed by Redis"""
    r = get_redis()
    if not r:
        return {"error": "Redis unavailable", "redis_host": REDIS_HOST}, 503

    count = r.incr(f"visits:{GITHUB_USERNAME}")
    return {
        "visits": count,
        "pod_name": POD_NAME,
        "student": GITHUB_USERNAME,
        "redis_host": REDIS_HOST,
    }

@app.route("/info")
def info():
    """Pod and configuration info"""
    r = get_redis()
    return {
        "pod_name": POD_NAME,
        "pod_namespace": POD_NAMESPACE,
        "pod_ip": POD_IP,
        "node_name": NODE_NAME,
        "hostname": socket.gethostname(),
        "app_version": APP_VERSION,
        "student": STUDENT_NAME,
        "github_username": GITHUB_USERNAME,
        "redis_connected": r is not None,
        "redis_host": REDIS_HOST,
        "config_source": "environment",
    }

@app.route("/health")
def health():
    """Health check — app is healthy even if Redis is down (graceful degradation)"""
    r = get_redis()
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "redis": "connected" if r else "disconnected",
    }

@app.route("/student")
def student():
    """Student information endpoint"""
    return {
        "name": STUDENT_NAME,
        "github_username": GITHUB_USERNAME,
        "app_version": APP_VERSION,
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting {STUDENT_NAME}'s app on port {port} (version {APP_VERSION})...")
    print(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
    app.run(host="0.0.0.0", port=port)
