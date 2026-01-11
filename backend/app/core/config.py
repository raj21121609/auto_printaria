from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Printaria Backend"
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    
    # Security
    SECRET_KEY: str = "changeme"
    
    # Razorpay
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    
    # Gupshup
    GUPSHUP_API_KEY: str
    GUPSHUP_APP_NAME: str
    GUPSHUP_WHATSAPP_NUMBER: str
    
    # Printer
    PRINTER_NAME: str = "Default_Printer"

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()
