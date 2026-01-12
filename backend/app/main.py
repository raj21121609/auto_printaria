"""
AMP K - Automated Print System Backend

Main FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from app.api.routes import twilio, webhooks, print_jobs, dashboard, files
from app.core.config import get_settings
from app.core.database import engine, Base

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # === STARTUP ===
    logger.info("Starting AMP K Backend...")
    
    # Log configuration (safely)
    db_url = settings.DATABASE_URL
    if db_url:
        safe_url = db_url.split("@")[-1] if "@" in db_url else "********"
        logger.info(f"Database: ...@{safe_url}")
    
    logger.info(f"Redis: {settings.REDIS_URL}")
    logger.info(f"Public URL: {settings.BACKEND_PUBLIC_URL}")
    
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")
    
    # Create uploads directory
    os.makedirs(settings.FILE_STORAGE_PATH, exist_ok=True)
    logger.info(f"Upload directory: {os.path.abspath(settings.FILE_STORAGE_PATH)}")
    
    # Initialize default shop if configured
    if settings.DEFAULT_SHOP_ID:
        await ensure_default_shop()
    
    logger.info("AMP K Backend started successfully!")
    
    yield  # Application runs here
    
    # === SHUTDOWN ===
    logger.info("Shutting down AMP K Backend...")


async def ensure_default_shop():
    """
    Ensure default shop exists in database.
    """
    from sqlalchemy.future import select
    from app.core.database import AsyncSessionLocal
    from app.models import Shop
    import uuid
    
    try:
        shop_id = uuid.UUID(settings.DEFAULT_SHOP_ID)
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Shop).where(Shop.id == shop_id))
            if not result.scalars().first():
                shop = Shop(
                    id=shop_id,
                    name="Default Shop",
                    location="Main Location",
                    is_active=True
                )
                db.add(shop)
                await db.commit()
                logger.info(f"Created default shop: {shop_id}")
            else:
                logger.info(f"Default shop exists: {shop_id}")
                
    except Exception as e:
        logger.error(f"Error ensuring default shop: {e}")


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="WhatsApp-based automated printing system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# ROUTES
# =============================================================================

# WhatsApp webhook (Twilio)
app.include_router(
    twilio.router,
    prefix="/webhook/twilio",
    tags=["WhatsApp - Twilio"]
)

# Payment webhooks (Razorpay)
app.include_router(
    webhooks.router,
    prefix="/api/webhooks",
    tags=["Webhooks"]
)

# Print jobs API (for worker and dashboard)
app.include_router(
    print_jobs.router,
    prefix="/api/v1/print_jobs",
    tags=["Print Jobs"]
)

# Dashboard API
app.include_router(
    dashboard.router,
    prefix="/api/v1/dashboard",
    tags=["Dashboard"]
)

# File serving
app.include_router(
    files.router,
    prefix="/files",
    tags=["Files"]
)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/", tags=["Health"])
def root():
    """Root endpoint - health check."""
    return {
        "service": "AMP K Backend",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Detailed health check endpoint.
    Checks database and Redis connectivity.
    """
    from app.core.redis_client import get_redis_client
    from app.core.database import AsyncSessionLocal
    
    health = {
        "status": "healthy",
        "database": "unknown",
        "redis": "unknown"
    }
    
    # Check database
    try:
        async with AsyncSessionLocal() as db:
            await db.execute("SELECT 1")
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"error: {str(e)}"
        health["status"] = "degraded"
    
    # Check Redis
    try:
        redis = get_redis_client()
        redis.ping()
        health["redis"] = "connected"
    except Exception as e:
        health["redis"] = f"error: {str(e)}"
        health["status"] = "degraded"
    
    return health
