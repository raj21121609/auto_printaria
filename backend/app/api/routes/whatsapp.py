from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
from app.core.config import VERIFY_TOKEN, WHATSAPP_TOKEN, PHONE_NUMBER_ID
import requests

router = APIRouter()

# 🔹 Webhook verification
@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    # Check if mode and token are correct
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        # Respond with the challenge token from the request
        return PlainTextResponse(content=hub_challenge, status_code=200)
    
    # Responds with '403 Forbidden' if verify tokens do not match
    raise HTTPException(status_code=403, detail="Verification failed")

# 🔹 Receive messages
@router.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    print("Incoming WhatsApp data:", data)

    try:
        if "object" in data and "entry" in data:
            for entry in data["entry"]:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        for message in value["messages"]:
                            sender = message["from"]
                            text = message.get("text", {}).get("body", "").lower()

                            if text == "hi":
                                send_message(sender, "👋 Welcome to Printaria!\nSend your document to print.")

    except Exception as e:
        print("Error processing webhook:", e)

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
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")
