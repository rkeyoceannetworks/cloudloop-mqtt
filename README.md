# Cloudloop Iridium MQTT Bridge

A Python-based interface for interacting with the Cloudloop MQTT Broker. This tool allows you to send (MT) and receive (MO) messages from remote Iridium satellite devices using an authenticated TLS connection.

## 🚀 Features
- **Real-time Monitoring**: Subscribes to Mobile Originated (MO) messages.
- **Bi-directional Comm**: Interactive terminal to send Mobile Terminated (MT) messages.
- **Secure**: Uses Certificate-based authentication (TLS 1.2).
- **Environment Driven**: Decoupled configuration using `.env` files.

---

## 🛠️ Setup & Installation

### 1. Clone & Environment
git clone https://github.com/YOUR_USERNAME/cloudloop-mqtt.git
cd cloudloop-mqtt
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

### 2. Certificates
Create a certs/ directory and place your Cloudloop-provided certificates inside:
- CloudloopMQTT.pem (CA Root)
- XXXXXXXX-certificate.pem.crt (Client Cert)
- XXXXXXXX-private.pem.crt (Private Key)

### 3. Configuration
Copy the example environment file:
cp .env.example .env

Edit .env and fill in your specific Account ID, Thing ID, and the filenames of your certificates.

---

## 📖 Usage
Run the main script to start the bridge:
python main.py

- Incoming messages from your Iridium device will print to the console automatically.
- Outgoing messages can be typed directly into the prompt. Type 'q' to exit.

---

## 🔒 Security Notice
This repository is configured to ignore sensitive files. Ensure your .gitignore includes:
- .env
- certs/
- venv/

Never commit your private keys or .pem files to a public repository.
