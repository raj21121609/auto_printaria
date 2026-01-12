from fastapi import APIRouter, Request, Response
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("")
async def handle_gupshup_webhook(request: Request):
    """
    Handle Gupshup Webhook Validation & Events.
    POST /webhook/gupshup
    """
    try:
        # Read raw body safely
        body = await request.body()
        logger.info(f"Received Webhook Body: {body.decode('utf-8', errors='ignore')}")
        
        # Return plain text "OK" immediately
        return Response(content="OK", media_type="text/plain", status_code=200)
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        # Always return 200 OK to satisfy provider
        return Response(content="OK", media_type="text/plain", status_code=200)
