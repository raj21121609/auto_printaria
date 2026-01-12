-- =============================================================================
-- AMP K - Automated Print System Database Schema
-- PostgreSQL 14+
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. SHOPS
-- =============================================================================
CREATE TABLE IF NOT EXISTS shops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    location TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Pricing configuration
    price_per_page_bw NUMERIC(10,2) DEFAULT 2.00,
    price_per_page_color NUMERIC(10,2) DEFAULT 10.00,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 2. ORDERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_phone VARCHAR(50) NOT NULL,
    
    -- File information
    file_name TEXT,
    file_url TEXT,
    file_media_id VARCHAR(255),
    file_hash VARCHAR(64),
    page_count INTEGER DEFAULT 1,
    
    -- Print configuration
    print_type VARCHAR(20) CHECK (print_type IN ('COLOR', 'BW', 'BOTH')),
    copies INTEGER DEFAULT 1 CHECK (copies >= 1),
    
    -- Pricing
    amount NUMERIC(10,2) DEFAULT 0 CHECK (amount >= 0),
    
    -- Razorpay binding
    razorpay_payment_link_id VARCHAR(255) UNIQUE,
    razorpay_payment_link_url TEXT,
    
    -- Status
    order_status VARCHAR(30) NOT NULL DEFAULT 'DRAFT'
        CHECK (order_status IN ('DRAFT', 'PAYMENT_PENDING', 'PAID', 'CANCELLED')),
    
    -- Shop reference
    shop_id UUID REFERENCES shops(id) ON DELETE SET NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(customer_phone);
CREATE INDEX IF NOT EXISTS idx_orders_shop_status ON orders(shop_id, order_status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_link ON orders(razorpay_payment_link_id);

-- =============================================================================
-- 3. PAYMENTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    
    -- Razorpay references
    provider_reference VARCHAR(255),  -- razorpay_payment_id (pay_xxx)
    payment_link_id VARCHAR(255),     -- plink_xxx for lookup
    
    payment_status VARCHAR(20) DEFAULT 'INITIATED'
        CHECK (payment_status IN ('INITIATED', 'SUCCESS', 'FAILED')),
    amount NUMERIC(10,2) NOT NULL,
    
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_payment_order UNIQUE(order_id)
);

CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(payment_status);
CREATE INDEX IF NOT EXISTS idx_payments_link_id ON payments(payment_link_id);

-- =============================================================================
-- 4. PRINT_JOBS
-- =============================================================================
CREATE TABLE IF NOT EXISTS print_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    shop_id UUID NOT NULL REFERENCES shops(id),
    
    printer_name VARCHAR(100),
    print_status VARCHAR(20) DEFAULT 'QUEUED'
        CHECK (print_status IN ('QUEUED', 'PRINTING', 'COMPLETED', 'FAILED')),
    
    -- Retry handling
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error TEXT,
    
    printed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_print_job_order UNIQUE(order_id)
);

CREATE INDEX IF NOT EXISTS idx_print_jobs_queue ON print_jobs(shop_id, print_status, created_at);

-- =============================================================================
-- 5. USER_SESSIONS (Conversation State)
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(50) NOT NULL UNIQUE,
    
    -- Conversation state machine
    state VARCHAR(30) DEFAULT 'IDLE'
        CHECK (state IN ('IDLE', 'AWAITING_FILE', 'AWAITING_PRINT_TYPE', 'AWAITING_COPIES', 'AWAITING_PAYMENT')),
    
    -- Draft order reference
    draft_order_id UUID REFERENCES orders(id) ON DELETE SET NULL,
    
    -- Temporary storage during conversation
    temp_file_url TEXT,
    temp_file_name TEXT,
    temp_file_media_id VARCHAR(255),
    temp_print_type VARCHAR(20),
    
    -- Session timing
    last_activity TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_phone ON user_sessions(phone);

-- =============================================================================
-- 6. WEBHOOK_LOGS (Idempotency)
-- =============================================================================
CREATE TABLE IF NOT EXISTS webhook_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Unique identifier from provider
    event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    
    -- Processing info
    processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    payload_hash VARCHAR(64),
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_webhook_logs_event ON webhook_logs(event_id);

-- =============================================================================
-- 7. AUTO UPDATE TRIGGERS
-- =============================================================================
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Orders trigger
DROP TRIGGER IF EXISTS trg_orders_updated ON orders;
CREATE TRIGGER trg_orders_updated
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- Print jobs trigger
DROP TRIGGER IF EXISTS trg_print_jobs_updated ON print_jobs;
CREATE TRIGGER trg_print_jobs_updated
BEFORE UPDATE ON print_jobs
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =============================================================================
-- 8. DEFAULT DATA
-- =============================================================================
-- Insert a default shop if none exists
INSERT INTO shops (id, name, location, is_active, price_per_page_bw, price_per_page_color)
SELECT 
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::UUID,
    'Default Print Shop',
    'Main Location',
    TRUE,
    2.00,
    10.00
WHERE NOT EXISTS (SELECT 1 FROM shops LIMIT 1);
