import os
import json
import base64
import ssl
import time
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# 1. Load Environment Variables
load_dotenv()

# --- Configuration ---
BROKER_HOST = "mqtt.cloudloop.com"
BROKER_PORT = 8883
DB_FILE = "cloudloop_messages.db"
DOWNLOAD_DIR = "downloads"

# Credentials and Paths from .env
ACCOUNT_ID = os.getenv("CL_ACCOUNT_ID")
THING_ID = os.getenv("CL_THING_ID")
CA_CERT = os.getenv("CERT_CA")
CLIENT_CERT = os.getenv("CERT_CLIENT")
PRIVATE_KEY = os.getenv("CERT_KEY")

# MQTT Topics
TOPIC_MO = f"lingo/{ACCOUNT_ID}/{THING_ID}/MO"
TOPIC_MT = f"lingo/{ACCOUNT_ID}/{THING_ID}/MT"

# --- Database & File Logic ---
def init_db():
    """Initializes the SQLite database with a unique ID constraint for deduplication."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # cl_id is the Cloudloop UUID, used as the Primary Key to prevent duplicates
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            cl_id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            topic TEXT,
            momsn INTEGER,
            decoded_text TEXT,
            file_path TEXT,
            latitude REAL,
            longitude REAL,
            raw_json TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_to_db(cl_id, topic, momsn, decoded_text, file_path, lat, lon, raw_json):
    """Saves the message to SQLite. Returns True if new, False if it was a duplicate."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # INSERT OR IGNORE avoids errors if the cl_id already exists
        cursor.execute('''
            INSERT OR IGNORE INTO messages 
            (cl_id, topic, momsn, decoded_text, file_path, latitude, longitude, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cl_id, topic, momsn, decoded_text, file_path, lat, lon, json.dumps(raw_json)))
        
        is_new = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return is_new
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return False

# --- Sending Logic ---
def send_device_message(client, text):
    """Encodes and publishes a text message to the Iridium device."""
    try:
        encoded_payload = base64.b64encode(text.encode('utf-8')).decode('utf-8')
        payload = {"message": encoded_payload}
        result = client.publish(TOPIC_MT, json.dumps(payload))
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"📤 Queued for satellite: '{text}'")
        else:
            print(f"❌ Publish failed. Error code: {result.rc}")
    except Exception as e:
        print(f"⚠️ Error sending: {e}")

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ Connected to Cloudloop Broker")
        client.subscribe(TOPIC_MO)
        print(f"📡 Subscribed to: {TOPIC_MO}")
        print("🚀 Ready! Type a message and press Enter to send. Type 'q' to quit.")
    else:
        print(f"❌ Connection failed: Code {rc}")

def on_message(client, userdata, msg):
    try:
        # Parse the Cloudloop JSON Wrapper
        data = json.loads(msg.payload.decode('utf-8'))
        cl_id = data.get("id")  # Unique Cloudloop UUID
        b64_message = data.get("message", "")
        
        if not cl_id or not b64_message:
            return

        # Decode the actual Iridium payload
        raw_bytes = base64.b64decode(b64_message)
        
        # Metadata extraction
        sbd_data = data.get("sbd", {})
        momsn = sbd_data.get("momsn")
        loc = sbd_data.get("location", {})
        
        file_path = None
        decoded_text = ""

        # Binary Detection & Saving
        try:
            # Try to treat as plain text first
            decoded_text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # If it fails, treat as binary and save to file
            ext = ".gz" if raw_bytes.startswith(b'\x1f\x8b') else ".bin"
            filename = f"msg_{cl_id}{ext}"
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            
            # Deduplication: only write if the file doesn't exist yet
            if not os.path.exists(file_path):
                with open(file_path, "wb") as f:
                    f.write(raw_bytes)
            decoded_text = f"[BINARY SAVED: {filename}]"

        # Final Persistence with Deduplication check
        is_new = save_to_db(cl_id, msg.topic, momsn, decoded_text, file_path, 
                            loc.get("latitude"), loc.get("longitude"), data)
        
        if is_new:
            print(f"\n📩 NEW MESSAGE [{momsn}]: {decoded_text}")
            if file_path:
                print(f"💾 File stored at: {file_path}")
        else:
            # This happens if Iridium retries a message you've already received
            print(f"♻️  Duplicate ignored: {cl_id}")

    except Exception as e:
        print(f"⚠️ Error processing incoming message: {e}")

# --- Execution ---
if __name__ == "__main__":
    # Check for required variables
    if not all([ACCOUNT_ID, THING_ID, CA_CERT, CLIENT_CERT, PRIVATE_KEY]):
        print("❌ Error: Missing configuration in .env file.")
        exit(1)

    init_db()

    client = mqtt.Client(CallbackAPIVersion.VERSION2)

    # Security Setup
    try:
        client.tls_set(
            ca_certs=CA_CERT,
            certfile=CLIENT_CERT,
            keyfile=PRIVATE_KEY,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
    except FileNotFoundError as e:
        print(f"❌ Certificate Error: {e}")
        exit(1)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"🔄 Connecting to {BROKER_HOST}...")
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    
    # Start the network loop in a non-blocking thread
    client.loop_start()

    try:
        while True:
            # Allow user to send MT messages via the console
            val = input("> ")
            if val.lower() == 'q':
                break
            if val:
                send_device_message(client, val)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n🛑 Shutting down...")
        client.loop_stop()
        client.disconnect()
