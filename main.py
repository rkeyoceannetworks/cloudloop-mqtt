import os
import json
import base64
import ssl
import time
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# 1. Load Environment Variables
load_dotenv()

# --- Configuration ---
BROKER_HOST = "mqtt.cloudloop.com"
BROKER_PORT = 8883

# IDs and Certificate paths from .env
ACCOUNT_ID = os.getenv("CL_ACCOUNT_ID")
THING_ID = os.getenv("CL_THING_ID")
CA_CERT = os.getenv("CERT_CA")
CLIENT_CERT = os.getenv("CERT_CLIENT")
PRIVATE_KEY = os.getenv("CERT_KEY")

# Topics
TOPIC_MO = f"lingo/{ACCOUNT_ID}/{THING_ID}/MO"
TOPIC_MT = f"lingo/{ACCOUNT_ID}/{THING_ID}/MT"

# --- Callback: Connection ---
def on_connect(client, userdata, flags, rc, properties=None):
    """Triggered when the client connects to the Cloudloop broker."""
    if rc == 0:
        print(f"✅ SUCCESS: Connected to Cloudloop Broker")
        print(f"📡 Subscribing to MO Topic: {TOPIC_MO}")
        client.subscribe(TOPIC_MO)
    else:
        print(f"❌ CONNECTION FAILED: Result code {rc}")
        # Note: rc 5 usually means unauthorized (check your certs/IDs)

# --- Callback: Message Received (MO) ---
def on_message(client, userdata, msg):
    """Triggered when a message arrives from the Iridium device."""
    print(f"\n--- New Message from Satellite ---")
    try:
        # Cloudloop sends a JSON payload
        raw_payload = msg.payload.decode('utf-8')
        data = json.loads(raw_payload)
        
        # The actual device data is Base64 encoded in the 'message' field
        b64_message = data.get("message", "")
        
        if b64_message:
            decoded_bytes = base64.b64decode(b64_message)
            # Attempt to decode as UTF-8 string; fallback to hex if binary
            try:
                decoded_text = decoded_bytes.decode('utf-8')
                print(f"📥 Decoded Text: {decoded_text}")
            except UnicodeDecodeError:
                print(f"📥 Binary Data (Hex): {decoded_bytes.hex()}")
        
        # Useful metadata provided by Cloudloop/Iridium
        if "sbd" in data:
            loc = data["sbd"].get("location", {})
            print(f"📍 Device Location: Lat {loc.get('latitude')}, Lon {loc.get('longitude')}")

    except Exception as e:
        print(f"⚠️ Error processing message: {e}")

# --- Function: Send Message (MT) ---
def send_device_message(client, text):
    """Encodes and publishes a message to be sent TO the Iridium device."""
    try:
        # 1. Base64 encode the string payload
        encoded_payload = base64.b64encode(text.encode('utf-8')).decode('utf-8')
        
        # 2. Wrap in Cloudloop's required JSON format
        payload = {"message": encoded_payload}
        
        # 3. Publish to the MT topic
        result = client.publish(TOPIC_MT, json.dumps(payload))
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"📤 Sent to queue: '{text}'")
        else:
            print(f"❌ Failed to send message. Error code: {result.rc}")
            
    except Exception as e:
        print(f"⚠️ Error sending message: {e}")

# --- Main Logic ---
if __name__ == "__main__":
    # Check for required environment variables
    if not all([ACCOUNT_ID, THING_ID, CA_CERT, CLIENT_CERT, PRIVATE_KEY]):
        print("❌ CRITICAL ERROR: Missing configuration in .env file.")
        exit(1)

    # Initialize Client with Callback API v2
    client = mqtt.Client(CallbackAPIVersion.VERSION2)

    # Configure TLS/SSL Security
    try:
        client.tls_set(
            ca_certs=CA_CERT,
            certfile=CLIENT_CERT,
            keyfile=PRIVATE_KEY,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
    except FileNotFoundError as e:
        print(f"❌ CERTIFICATE ERROR: Could not find files.\n   Details: {e}")
        exit(1)

    # Attach Callbacks
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to Broker
    print(f"🔄 Connecting to {BROKER_HOST}...")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)

    # Start the network loop in the background
    client.loop_start()

    print("🚀 System Ready. Use Ctrl+C to stop.")
    
    try:
        while True:
            # Simple interactive loop to send messages while listening
            msg_to_send = input("\nEnter message to send to device (or 'q' to quit): ")
            if msg_to_send.lower() == 'q':
                break
            if msg_to_send:
                send_device_message(client, msg_to_send)
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    finally:
        client.loop_stop()
        client.disconnect()
