-- Enable UUID extension (if using PostgreSQL < 13, otherwise gen_random_uuid() is built-in)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. SHOPS TABLE
CREATE TABLE shops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    location TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. ORDERS TABLE
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_phone VARCHAR(50) NOT NULL,
    file_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    copies INTEGER NOT NULL CHECK (copies >= 1),
    amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
    status VARCHAR(50) NOT NULL CHECK (status IN ('CREATED', 'PAYMENT_PENDING', 'PAID', 'PRINTING', 'PRINTED', 'PAYMENT_FAILED', 'PRINT_FAILED')),
    shop_id UUID REFERENCES shops(id) ON DELETE SET NULL, -- Nullable as per requirements
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for frequent queries by status (e.g., finding pending orders)
CREATE INDEX idx_orders_status ON orders(status);
-- Index for customer lookups
CREATE INDEX idx_orders_customer_phone ON orders(customer_phone);
-- Index for shop lookups
CREATE INDEX idx_orders_shop_id ON orders(shop_id);


-- 3. PAYMENTS TABLE
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    payment_provider_reference VARCHAR(255),
    payment_status VARCHAR(50) NOT NULL CHECK (payment_status IN ('INITIATED', 'SUCCESS', 'FAILED')),
    amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- Enforce one payment per order (1:1 relationship)
    CONSTRAINT uq_payments_order_id UNIQUE (order_id)
);

-- Index for payment lookups by order
CREATE INDEX idx_payments_order_id ON payments(order_id);
-- Index for payment status
CREATE INDEX idx_payments_status ON payments(payment_status);


-- 4. PRINT_JOBS TABLE
CREATE TABLE print_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    printer_name VARCHAR(100) NOT NULL,
    print_status VARCHAR(50) NOT NULL CHECK (print_status IN ('QUEUED', 'PRINTING', 'COMPLETED', 'FAILED')),
    printed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for querying jobs for a specific order
CREATE INDEX idx_print_jobs_order_id ON print_jobs(order_id);
-- Index for finding queued jobs
CREATE INDEX idx_print_jobs_status ON print_jobs(print_status);


-- TRIGGER FOR UPDATED_AT
-- Automatically update 'updated_at' column on orders
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
