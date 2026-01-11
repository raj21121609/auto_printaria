-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =========================
-- 1. SHOPS
-- =========================
CREATE TABLE shops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    location TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- 2. ORDERS (Business State)
-- =========================
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_phone VARCHAR(50) NOT NULL,
    file_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    copies INTEGER NOT NULL CHECK (copies >= 1),
    amount NUMERIC(10,2) NOT NULL CHECK (amount >= 0),

    order_status VARCHAR(30) NOT NULL
      CHECK (order_status IN ('CREATED','PAYMENT_PENDING','PAID','CANCELLED')),

    shop_id UUID REFERENCES shops(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_shop_status
ON orders(shop_id, order_status);

-- =========================
-- 3. PAYMENTS
-- =========================
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    provider_reference VARCHAR(255),
    payment_status VARCHAR(20)
      CHECK (payment_status IN ('INITIATED','SUCCESS','FAILED')),
    amount NUMERIC(10,2) NOT NULL,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_payment_order UNIQUE(order_id)
);

CREATE INDEX idx_payments_status
ON payments(payment_status);

-- =========================
-- 4. PRINT_JOBS (QUEUE MIRROR)
-- =========================
CREATE TABLE print_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    shop_id UUID NOT NULL REFERENCES shops(id),

    printer_name VARCHAR(100),
    print_status VARCHAR(20)
      CHECK (print_status IN ('QUEUED','PRINTING','COMPLETED','FAILED')),

    retry_count INTEGER DEFAULT 0,
    printed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_print_jobs_queue
ON print_jobs(shop_id, print_status, created_at);

-- =========================
-- 5. AUTO UPDATE updated_at
-- =========================
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orders_updated
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER trg_print_jobs_updated
BEFORE UPDATE ON print_jobs
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
