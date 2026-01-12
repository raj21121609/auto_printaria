from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv
from typing import Optional
import os

load_dotenv()


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AMP K - Automated Print System"
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    SECRET_KEY: str = "changeme"
    WORKER_API_KEY: str = "worker-secret-key"  # For print worker auth
    
    # Razorpay
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    
    # Twilio (WhatsApp Sandbox)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""  # e.g., "whatsapp:+14155238886"
    
    # Backend public URL (for Razorpay callbacks, file downloads)
    BACKEND_PUBLIC_URL: str = "https://your-tunnel.trycloudflare.com"
    
    # File storage
    FILE_STORAGE_PATH: str = "./uploads"
    
    # Printer
    PRINTER_NAME: str = "Default_Printer"
    
    # Default shop ID (for single-shop setup)
    DEFAULT_SHOP_ID: Optional[str] = None
    
    # Pricing defaults (in INR)
    PRICE_PER_PAGE_BW: float = 2.0
    PRICE_PER_PAGE_COLOR: float = 10.0

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields


@lru_cache()
def get_settings():
    return Settings()
