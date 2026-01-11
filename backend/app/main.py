from fastapi import FastAPI
from app.api.routes import whatsapp, webhooks
from app.core.config import get_settings
from app.core.database import engine, Base
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title=settings.PROJECT_NAME)

# Include Routers
app.include_router(whatsapp.router, prefix="/api/whatsapp", tags=["WhatsApp"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Printaria Backend...")
    # Create Tables
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Uncomment to reset DB
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created.")

@app.get("/")
def read_root():
    return {"message": "Welcome to Printaria Backend"}
