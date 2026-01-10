import requests
import os
from dotenv import load_dotenv

load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
if not VERIFY_TOKEN:
    print("Warning: VERIFY_TOKEN not set in .env")
    VERIFY_TOKEN = "test_token" # Fallback for local testing if env is missing

url = "http://127.0.0.1:8000/webhook"
params = {
    "hub.mode": "subscribe",
    "hub.verify_token": VERIFY_TOKEN,
    "hub.challenge": "123456789"
}

try:
    response = requests.get(url, params=params)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
    
    if response.status_code == 200 and response.text == "123456789":
        print("✅ Webhook verification SUCCESS")
    else:
        print("❌ Webhook verification FAILED")
except Exception as e:
    print(f"Error: {e}")
