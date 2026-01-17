#  - WhatsApp Automated Print System

Production-grade WhatsApp-based print ordering system with automated printing on a local Windows PC.

## System Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   WhatsApp   │────▶│   FastAPI    │────▶│  PostgreSQL  │     │  Local PC    │
│   (Twilio)   │◀────│   Backend    │────▶│    Redis     │────▶│   Worker     │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │                                         │
                            ▼                                         ▼
                     ┌──────────────┐                          ┌──────────────┐
                     │  Razorpay    │                          │   Printer    │
                     │  Payments    │                          │              │
                     └──────────────┘                          └──────────────┘
```

## Features

- **WhatsApp Bot**: Button-driven order flow via Twilio
- **File Upload**: Accepts PDF, Word, Images
- **Print Options**: Color / Black & White / Both
- **Online Payments**: Razorpay Payment Links
- **Auto Print**: Jobs queued to local Windows printer
- **Status Notifications**: WhatsApp updates on payment & print completion
- **Dashboard API**: Order tracking & revenue analytics

## Architecture

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | Python FastAPI | Stateless API server |
| Database | PostgreSQL | Transactional data (ACID) |
| Queue | Redis | Print job queue (FIFO) |
| WhatsApp | Twilio Sandbox | Customer messaging |
| Payments | Razorpay | Payment processing |
| Print Worker | Python (Windows) | Local printer automation |

### Order Flow

1. Customer sends message on WhatsApp
2. Bot asks for document upload
3. Customer uploads file (PDF/Word/Image)
4. Bot shows print type options (Color/BW/Both)
5. Customer selects print type
6. Bot asks for number of copies
7. Customer enters copies (1-100)
8. Backend calculates price & generates Razorpay link
9. Customer pays via payment link
10. Razorpay webhook confirms payment
11. Print job queued to Redis
12. Local worker picks up job
13. File downloaded & printed
14. Customer notified on WhatsApp

## Project Structure

```
automation/
├── backend/                 # FastAPI Backend
│   ├── app/
│   │   ├── api/routes/      # API endpoints
│   │   │   ├── twilio.py    # WhatsApp webhook
│   │   │   ├── webhooks.py  # Razorpay webhook
│   │   │   ├── print_jobs.py
│   │   │   ├── dashboard.py
│   │   │   └── files.py
│   │   ├── core/            # Configuration
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── redis_client.py
│   │   ├── services/        # Business logic
│   │   │   ├── order_service.py
│   │   │   ├── razorpay_service.py
│   │   │   ├── session_service.py
│   │   │   ├── twilio_service.py
│   │   │   └── queue_service.py
│   │   ├── models.py        # SQLAlchemy models
│   │   └── main.py          # App entry point
│   ├── schema.sql           # Database schema
│   ├── requirements.txt
│   └── .env                 # Configuration (create from .env.example)
│
└── print_worker/            # Windows Print Worker
    ├── main.py              # Worker entry point
    ├── backend_client.py    # API client
    ├── file_downloader.py   # File download
    ├── printer.py           # Print execution
    ├── config.json          # Worker configuration
    └── requirements.txt
```

## Setup Instructions

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Redis 6+
- Twilio Account (WhatsApp Sandbox)
- Razorpay Account
- Cloudflare Tunnel (for public webhook URLs)

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
copy .env.example .env
# Edit .env with your credentials

# Initialize database
psql -U postgres -c "CREATE DATABASE ampk;"
psql -U postgres -d ampk -f schema.sql

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Cloudflare Tunnel

```bash
# Install cloudflared
# Download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

# Start tunnel
cloudflared tunnel --url http://localhost:8000
```

Update `BACKEND_PUBLIC_URL` in `.env` with your tunnel URL.

### 3. Twilio Configuration

1. Go to [Twilio Console](https://console.twilio.com/)
2. Navigate to Messaging → Try it out → Send a WhatsApp message
3. Follow sandbox setup instructions
4. Set webhook URL: `https://your-tunnel.trycloudflare.com/webhook/twilio`
5. Add credentials to `.env`

### 4. Razorpay Configuration

1. Go to [Razorpay Dashboard](https://dashboard.razorpay.com/)
2. Get API keys from Settings → API Keys
3. Create webhook:
   - URL: `https://your-tunnel.trycloudflare.com/api/webhooks/razorpay-webhook`
   - Events: `payment_link.paid`
4. Add credentials to `.env`

### 5. Print Worker Setup (Windows PC)

```bash
cd print_worker

# Install dependencies
pip install -r requirements.txt

# Edit config.json
# Update backend_url, api_key, redis_url

# (Optional) Install SumatraPDF for better PDF printing
# Download from: https://www.sumatrapdfreader.org/download-free-pdf-viewer

# Run worker
python main.py
```

## Configuration

### Backend (.env)

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ampk

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key
WORKER_API_KEY=your-worker-api-key

# Razorpay
RAZORPAY_KEY_ID=rzp_test_xxx
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=xxx

# Twilio
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Backend URL (Cloudflare tunnel)
BACKEND_PUBLIC_URL=https://xxx.trycloudflare.com

# Pricing (INR)
PRICE_PER_PAGE_BW=2.0
PRICE_PER_PAGE_COLOR=10.0

# Default shop
DEFAULT_SHOP_ID=a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
```

### Print Worker (config.json)

```json
{
    "backend_url": "http://localhost:8000",
    "api_key": "your-worker-api-key",
    "redis_url": "redis://localhost:6379/0",
    "queue_name": "print_queue",
    "printer_name": "",
    "poll_timeout": 30
}
```

## API Endpoints

### WhatsApp Webhook
- `POST /webhook/twilio` - Twilio WhatsApp messages

### Payment Webhook
- `POST /api/webhooks/razorpay-webhook` - Razorpay payment events
- `GET /api/webhooks/razorpay-callback` - Payment redirect

### Print Jobs (Worker API)
- `GET /api/v1/print_jobs/{job_id}` - Get job details
- `PUT /api/v1/print_jobs/{job_id}/status` - Update status
- `POST /api/v1/print_jobs/{job_id}/retry` - Retry failed job

### Dashboard
- `GET /api/v1/dashboard/stats` - Order & revenue stats
- `GET /api/v1/dashboard/orders` - List orders
- `GET /api/v1/dashboard/orders/{order_id}` - Order details
- `GET /api/v1/dashboard/pending-jobs` - Pending print jobs
- `GET /api/v1/dashboard/failed-jobs` - Failed print jobs

### Files
- `GET /files/{path}` - Serve uploaded files

### Health
- `GET /` - Service info
- `GET /health` - Health check

## Database Schema

### Tables

- **shops** - Print shop configuration
- **orders** - Customer orders
- **payments** - Payment records
- **print_jobs** - Print queue mirror
- **user_sessions** - Conversation state
- **webhook_logs** - Idempotency log

## Scalability

### Why This Architecture Works

1. **Stateless Backend**: Any instance can handle any request
2. **Redis Queue**: Absorbs traffic bursts, decouples processing
3. **Serial Printing**: One job at a time prevents printer conflicts
4. **Webhook Idempotency**: Duplicate events handled safely
5. **PostgreSQL ACID**: Data integrity guaranteed

### Handling 30+ Concurrent Users

- WhatsApp messages hit backend in parallel
- Each creates/updates order in PostgreSQL
- Payment confirmations queue jobs to Redis
- Single worker processes jobs sequentially
- No race conditions on printer

## Troubleshooting

### Common Issues

**Twilio webhook not working**
- Check Cloudflare tunnel is running
- Verify webhook URL in Twilio console
- Check backend logs for errors

**Payments not confirming**
- Verify Razorpay webhook secret
- Check webhook URL is accessible
- Look at webhook_logs table for duplicates

**Print jobs stuck in QUEUED**
- Ensure print worker is running
- Check Redis connection
- Verify worker API key matches

**Printing fails**
- Install SumatraPDF for PDF files
- Check printer is online and default
- Review print_worker.log for errors

## License

MIT License
