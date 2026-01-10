from fastapi import APIRouter, Request
from app.core.config import VERIFY_TOKEN, WHATSAPP_TOKEN, PHONE_NUMBER_ID
import requests

router = APIRouter()

# 🔹 Webhook verification
@router.get("/webhook")
def verify_webhook(
    hub_mode: str = None,
    hub_challenge: int = None,
    hub_verify_token: str = None
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return hub_challenge
    return {"error": "Verification failed"}

# 🔹 Receive messages
@router.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    print("Incoming WhatsApp data:", data)

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = message["from"]
        text = message["text"]["body"].lower()

        if text == "hi":
            send_message(sender, "👋 Welcome to Printaria!\nSend your document to print.")

    except Exception as e:
        print("Error:", e)

    return {"status": "ok"}


# 🔹 Send WhatsApp message
def send_message(to: str, text: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": text}
    }
    requests.post(url, headers=headers, json=payload)
