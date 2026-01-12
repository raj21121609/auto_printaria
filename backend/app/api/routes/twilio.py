"""
Twilio WhatsApp Webhook Handler for AMP K

Implements the complete conversation state machine:
1. IDLE -> User sends message -> Welcome + ask for file
2. AWAITING_FILE -> User uploads file -> Ask for print type
3. AWAITING_PRINT_TYPE -> User selects 1/2/3 -> Ask for copies
4. AWAITING_COPIES -> User enters number -> Create order, show summary, send payment link
5. AWAITING_PAYMENT -> Payment confirmed via webhook -> Notify user
"""

from fastapi import APIRouter, Form, Response, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.twiml.messaging_response import MessagingResponse
import logging
from typing import Optional
from decimal import Decimal

from app.core.database import get_db
from app.models import ConversationState, PrintType, Order
from app.services import session_service, order_service, twilio_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("")
async def handle_twilio_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    # Standard Twilio webhook fields
    From: str = Form(...),
    Body: str = Form(default=""),
    # Media fields (optional, present when user sends file)
    NumMedia: str = Form(default="0"),
    MediaUrl0: Optional[str] = Form(default=None),
    MediaContentType0: Optional[str] = Form(default=None),
):
    """
    Handle Twilio WhatsApp Webhook.
    POST /webhook/twilio
    
    Implements conversation state machine for print order flow.
    """
    try:
        logger.info(f"Twilio message from {From}: '{Body}' (Media: {NumMedia})")
        
        # Get or create user session
        session = await session_service.get_or_create_session(db, From)
        
        # Check if user sent a file
        has_media = int(NumMedia) > 0 and MediaUrl0
        
        # Normalize message body
        message = Body.strip().lower()
        
        # Process based on current state
        response_text = await process_message(
            db=db,
            session=session,
            phone=From,
            message=message,
            has_media=has_media,
            media_url=MediaUrl0,
            media_type=MediaContentType0
        )
        
        # Create TwiML response
        resp = MessagingResponse()
        if response_text:
            resp.message(response_text)
        
        return Response(content=str(resp), media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error handling Twilio webhook: {e}", exc_info=True)
        resp = MessagingResponse()
        resp.message("Sorry, something went wrong. Please try again.")
        return Response(content=str(resp), media_type="application/xml")


async def process_message(
    db: AsyncSession,
    session,
    phone: str,
    message: str,
    has_media: bool,
    media_url: Optional[str],
    media_type: Optional[str]
) -> str:
    """
    Process incoming message based on conversation state.
    
    Returns response message to send back to user.
    """
    current_state = session.state
    
    logger.info(f"Processing: state={current_state}, message='{message}', has_media={has_media}")
    
    # ==========================================================================
    # STATE: IDLE - Waiting for user to start
    # ==========================================================================
    if current_state == ConversationState.IDLE:
        if has_media:
            # User sent a file - process it
            return await handle_file_upload(db, session, phone, media_url, media_type)
        else:
            # Any text message - send welcome
            await session_service.update_session_state(db, session, ConversationState.AWAITING_FILE)
            return twilio_service.msg_welcome()
    
    # ==========================================================================
    # STATE: AWAITING_FILE - Waiting for file upload
    # ==========================================================================
    elif current_state == ConversationState.AWAITING_FILE:
        if has_media:
            return await handle_file_upload(db, session, phone, media_url, media_type)
        else:
            return twilio_service.msg_welcome()
    
    # ==========================================================================
    # STATE: AWAITING_PRINT_TYPE - Waiting for 1/2/3 selection
    # ==========================================================================
    elif current_state == ConversationState.AWAITING_PRINT_TYPE:
        if has_media:
            # User sent another file - start over with new file
            return await handle_file_upload(db, session, phone, media_url, media_type)
        
        # Parse print type selection
        print_type = parse_print_type_selection(message)
        
        if print_type:
            await session_service.store_temp_print_type(db, session, print_type)
            return twilio_service.msg_print_type_selected(print_type.value)
        else:
            return twilio_service.msg_invalid_input() + "\n\n" + twilio_service.msg_file_received(session.temp_file_name or "your file")
    
    # ==========================================================================
    # STATE: AWAITING_COPIES - Waiting for number of copies
    # ==========================================================================
    elif current_state == ConversationState.AWAITING_COPIES:
        if has_media:
            # User sent another file - start over
            return await handle_file_upload(db, session, phone, media_url, media_type)
        
        # Parse copies number
        copies = parse_copies_input(message)
        
        if copies:
            return await finalize_order(db, session, phone, copies)
        else:
            return twilio_service.msg_invalid_copies()
    
    # ==========================================================================
    # STATE: AWAITING_PAYMENT - Payment link sent, waiting for confirmation
    # ==========================================================================
    elif current_state == ConversationState.AWAITING_PAYMENT:
        if has_media:
            # User sent another file - start new order
            return await handle_file_upload(db, session, phone, media_url, media_type)
        
        # Check for cancel command
        if message in ["cancel", "stop", "exit"]:
            await session_service.clear_session(db, session)
            return "Order cancelled. Send a document to start a new order."
        
        # Remind about payment
        return (
            "⏳ Waiting for payment...\n\n"
            "Please complete payment using the link sent earlier.\n\n"
            "_Reply 'cancel' to cancel this order._"
        )
    
    # Default fallback
    await session_service.update_session_state(db, session, ConversationState.IDLE)
    return twilio_service.msg_welcome()


async def handle_file_upload(
    db: AsyncSession,
    session,
    phone: str,
    media_url: str,
    media_type: str
) -> str:
    """
    Handle file upload from user.
    Downloads file, saves it, and updates session.
    """
    try:
        # Extract media SID from URL for logging
        # Twilio URL format: https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages/{MessageSid}/Media/{MediaSid}
        media_sid = media_url.split("/")[-1] if media_url else "unknown"
        
        # Download file from Twilio
        result = await twilio_service.download_media_file(media_url, media_sid)
        
        if not result:
            return "❌ Failed to download file. Please try sending it again."
        
        file_content, content_type, filename = result
        
        # Validate file type
        if not is_supported_file_type(content_type):
            return (
                f"❌ Unsupported file type: {content_type}\n\n"
                "_Supported: PDF, Word, Images (JPG, PNG)_"
            )
        
        # Save file locally
        file_path, file_url = await order_service.save_uploaded_file(
            file_content=file_content,
            filename=filename,
            customer_phone=phone
        )
        
        # Store in session
        await session_service.store_temp_file(
            db=db,
            session=session,
            file_url=file_url,
            file_name=filename,
            media_id=media_sid
        )
        
        logger.info(f"File uploaded: {filename} -> {file_url}")
        
        return twilio_service.msg_file_received(filename)
        
    except Exception as e:
        logger.error(f"Error handling file upload: {e}", exc_info=True)
        return "❌ Error processing file. Please try again."


async def finalize_order(
    db: AsyncSession,
    session,
    phone: str,
    copies: int
) -> str:
    """
    Finalize order with print configuration and generate payment link.
    """
    try:
        # Create order from session data
        order = await order_service.create_draft_order(db, phone)
        
        # Add file info
        await order_service.update_order_file(
            db=db,
            order=order,
            file_name=session.temp_file_name,
            file_url=session.temp_file_url,
            file_media_id=session.temp_file_media_id,
            page_count=1  # TODO: Implement page count detection
        )
        
        # Add print configuration
        await order_service.update_order_print_config(
            db=db,
            order=order,
            print_type=session.temp_print_type,
            copies=copies
        )
        
        # Generate payment link
        order, payment_url = await order_service.finalize_order_with_payment_link(db, order)
        
        # Link order to session
        await session_service.link_order_to_session(db, session, order)
        
        # Build response
        summary = twilio_service.msg_order_summary(
            filename=order.file_name,
            print_type=order.print_type.value,
            copies=order.copies,
            amount=float(order.amount)
        )
        
        payment_msg = twilio_service.msg_payment_link(payment_url)
        
        return f"{summary}\n\n{payment_msg}"
        
    except Exception as e:
        logger.error(f"Error finalizing order: {e}", exc_info=True)
        return "❌ Error creating order. Please try again."


def parse_print_type_selection(message: str) -> Optional[PrintType]:
    """
    Parse print type from user input.
    Accepts: 1/2/3, color/bw/both, or various aliases.
    """
    message = message.strip().lower()
    
    # Number selections
    if message in ["1", "one"]:
        return PrintType.COLOR
    elif message in ["2", "two"]:
        return PrintType.BW
    elif message in ["3", "three"]:
        return PrintType.BOTH
    
    # Text selections
    if message in ["color", "colour", "color xerox", "colour xerox", "color print"]:
        return PrintType.COLOR
    elif message in ["bw", "b&w", "black", "black and white", "black & white", "black white"]:
        return PrintType.BW
    elif message in ["both", "color and bw", "color + bw", "all"]:
        return PrintType.BOTH
    
    return None


def parse_copies_input(message: str) -> Optional[int]:
    """
    Parse number of copies from user input.
    Returns None if invalid.
    """
    message = message.strip()
    
    try:
        # Handle spelled numbers
        word_to_num = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }
        
        if message.lower() in word_to_num:
            copies = word_to_num[message.lower()]
        else:
            copies = int(message)
        
        # Validate range
        if 1 <= copies <= 100:
            return copies
        
        return None
        
    except ValueError:
        return None


def is_supported_file_type(content_type: str) -> bool:
    """Check if file type is supported for printing."""
    supported_types = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/gif",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
    ]
    
    # Check main type (ignore parameters like charset)
    main_type = content_type.split(";")[0].strip().lower()
    return main_type in supported_types
