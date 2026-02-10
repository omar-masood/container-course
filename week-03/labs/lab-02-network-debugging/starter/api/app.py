from flask import Flask, jsonify
import os
import mysql.connector
import time
import socket

app = Flask(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "db"),
    "user": os.environ.get("DB_USER", "appuser"),
    "password": os.environ.get("DB_PASSWORD", "apppass"),
    "database": os.environ.get("DB_NAME", "appdb"),
}


def get_db_connection():
    """Get a database connection with retry logic."""
    for attempt in range(5):
        try:
            return mysql.connector.connect(**DB_CONFIG)
        except mysql.connector.Error as e:
            print(f"DB connection attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    raise Exception("Could not connect to database after 5 attempts")


def init_db():
    """Create the items table if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Seed some data if empty
    cursor.execute("SELECT COUNT(*) FROM items")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO items (name) VALUES (%s)",
            [("Widget",), ("Gadget",), ("Doohickey",)]
        )
    conn.commit()
    cursor.close()
    conn.close()


@app.route("/health")
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"status": "healthy", "hostname": socket.gethostname()})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route("/api/items")
def get_items():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, created_at FROM items")
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    # Convert datetime objects for JSON serialization
    for item in items:
        item["created_at"] = item["created_at"].isoformat()
    return jsonify({"items": items, "count": len(items)})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
