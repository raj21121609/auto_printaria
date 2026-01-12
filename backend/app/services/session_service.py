"""
Session Service for AMP K

Manages user conversation state for WhatsApp bot flow.
Implements a state machine for order creation process.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import UserSession, ConversationState, Order, PrintType
from app.core.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

# Session timeout in minutes
SESSION_TIMEOUT_MINUTES = 30


async def get_or_create_session(db: AsyncSession, phone: str) -> UserSession:
    """
    Get existing session or create a new one for the phone number.
    
    Args:
        db: Database session
        phone: Customer phone number (with whatsapp: prefix)
        
    Returns:
        UserSession object
    """
    # Normalize phone number
    normalized_phone = phone.strip()
    
    result = await db.execute(
        select(UserSession).where(UserSession.phone == normalized_phone)
    )
    session = result.scalars().first()
    
    if session:
        # Check if session is expired
        if is_session_expired(session):
            # Reset expired session
            session.state = ConversationState.IDLE
            session.draft_order_id = None
            session.temp_file_url = None
            session.temp_file_name = None
            session.temp_file_media_id = None
            session.temp_print_type = None
            logger.info(f"Reset expired session for {phone}")
        
        session.last_activity = datetime.utcnow()
        await db.commit()
        await db.refresh(session)
        return session
    
    # Create new session
    session = UserSession(
        phone=normalized_phone,
        state=ConversationState.IDLE,
        last_activity=datetime.utcnow()
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    logger.info(f"Created new session for {phone}")
    return session


def is_session_expired(session: UserSession) -> bool:
    """Check if session has expired due to inactivity."""
    if not session.last_activity:
        return True
    
    expiry_time = session.last_activity + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    return datetime.utcnow() > expiry_time


async def update_session_state(
    db: AsyncSession,
    session: UserSession,
    new_state: ConversationState
) -> UserSession:
    """Update session to new state."""
    old_state = session.state
    session.state = new_state
    session.last_activity = datetime.utcnow()
    
    await db.commit()
    await db.refresh(session)
    
    logger.info(f"Session {session.phone}: {old_state} -> {new_state}")
    return session


async def store_temp_file(
    db: AsyncSession,
    session: UserSession,
    file_url: str,
    file_name: str,
    media_id: str = None
) -> UserSession:
    """Store temporary file info in session."""
    session.temp_file_url = file_url
    session.temp_file_name = file_name
    session.temp_file_media_id = media_id
    session.state = ConversationState.AWAITING_PRINT_TYPE
    session.last_activity = datetime.utcnow()
    
    await db.commit()
    await db.refresh(session)
    
    return session


async def store_temp_print_type(
    db: AsyncSession,
    session: UserSession,
    print_type: PrintType
) -> UserSession:
    """Store selected print type in session."""
    session.temp_print_type = print_type
    session.state = ConversationState.AWAITING_COPIES
    session.last_activity = datetime.utcnow()
    
    await db.commit()
    await db.refresh(session)
    
    return session


async def link_order_to_session(
    db: AsyncSession,
    session: UserSession,
    order: Order
) -> UserSession:
    """Link a draft order to the session."""
    session.draft_order_id = order.id
    session.state = ConversationState.AWAITING_PAYMENT
    session.last_activity = datetime.utcnow()
    
    await db.commit()
    await db.refresh(session)
    
    return session


async def clear_session(db: AsyncSession, session: UserSession) -> UserSession:
    """Reset session to idle state after order completion or cancellation."""
    session.state = ConversationState.IDLE
    session.draft_order_id = None
    session.temp_file_url = None
    session.temp_file_name = None
    session.temp_file_media_id = None
    session.temp_print_type = None
    session.last_activity = datetime.utcnow()
    
    await db.commit()
    await db.refresh(session)
    
    logger.info(f"Cleared session for {session.phone}")
    return session


async def get_session_by_phone(db: AsyncSession, phone: str) -> Optional[UserSession]:
    """Get session by phone number without creating one."""
    result = await db.execute(
        select(UserSession).where(UserSession.phone == phone)
    )
    return result.scalars().first()
