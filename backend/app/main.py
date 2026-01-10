from fastapi import FastAPI
from app.api.routes import whatsapp

app = FastAPI()

app.include_router(whatsapp.router)

@app.get("/")
def home():
    return {"status": "FastAPI working 🚀"}
