import os
import json
import base64
import ssl
import time
import sqlite3  # Built-in, no pip install needed
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

load_dotenv()

# --- Configuration ---
BROKER_HOST = "mqtt.cloudloop.com"
BROKER_PORT = 8883
DB_FILE = "cloudloop_messages.db"

ACCOUNT_ID = os.getenv("CL_ACCOUNT_ID")
THING_ID = os.getenv("CL_THING_ID")
CA_CERT = os.getenv("CERT_CA")
CLIENT_CERT = os.getenv("CERT_CLIENT")
PRIVATE_KEY = os.getenv("CERT_KEY")

TOPIC_MO = f"lingo/{ACCOUNT_ID}/{THING_ID}/MO"
TOPIC_MT = f"lingo/{ACCOUNT_ID}/{THING_ID}/MT"

# --- Database Logic ---
def init_db():
    """Initializes the SQLite database and creates the table if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            topic TEXT,
            device_id TEXT,
            raw_json TEXT,
            decoded_text TEXT,
            latitude REAL,
            longitude REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_to_db(topic, raw_json, decoded_text, lat=None, lon=None):
    """Inserts a received message into the database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (topic, device_id, raw_json, decoded_text, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (topic, THING_ID, json.dumps(raw_json), decoded_text, lat, lon))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Database Error: {e}")

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ Connected to Cloudloop")
        client.subscribe(TOPIC_MO)
    else:
        print(f"❌ Connection failed: {rc}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode('utf-8'))
        b64_message = data.get("message", "")
        decoded_text = ""
        
        if b64_message:
            decoded_text = base64.b64decode(b64_message).decode('utf-8', errors='replace')
            print(f"\n📩 Message: {decoded_text}")
        
        # Extract location if available
        sbd_data = data.get("sbd", {})
        loc = sbd_data.get("location", {})
        lat = loc.get("latitude")
        lon = loc.get("longitude")

        # SAVE TO DATABASE
        save_to_db(msg.topic, data, decoded_text, lat, lon)
        print(f"💾 Saved to {DB_FILE}")

    except Exception as e:
        print(f"⚠️ Error: {e}")

# --- Main Logic ---
if __name__ == "__main__":
    init_db()  # Setup database on start

    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    client.tls_set(
        ca_certs=CA_CERT, 
        certfile=CLIENT_CERT, 
        keyfile=PRIVATE_KEY,
        cert_reqs=ssl.CERT_REQUIRED, 
        tls_version=ssl.PROTOCOL_TLSv1_2
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"🔄 Connecting to {BROKER_HOST}...")
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        client.loop_stop()
        client.disconnect()
