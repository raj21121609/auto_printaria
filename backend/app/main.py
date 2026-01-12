from fastapi import FastAPI
from app.api.routes import gupshup, webhooks, print_jobs, twilio
from app.core.config import get_settings
from app.core.database import engine, Base
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title=settings.PROJECT_NAME)

# Include Routers
app.include_router(gupshup.router, prefix="/webhook/gupshup", tags=["Gupshup"])
app.include_router(twilio.router, prefix="/webhook/twilio", tags=["Twilio"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(print_jobs.router, prefix="/api/v1/print_jobs", tags=["Print Jobs"])

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Printaria Backend...")
    
    # Safe logging of DATABASE_URL
    db_url = settings.DATABASE_URL
    if db_url:
        safe_url = db_url.split("@")[-1] if "@" in db_url else "********"
        logger.info(f"Using DATABASE_URL: ...@{safe_url}")

    # Create Tables
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Uncomment to reset DB
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created.")

@app.get("/")
def read_root():
    return {"message": "Welcome to Printaria Backend"}
