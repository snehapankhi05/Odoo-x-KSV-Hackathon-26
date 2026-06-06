-- VendorBridge PostgreSQL DDL Database Schema
-- Target Database: PostgreSQL 15+
-- Author: Principal Database Architect & ERP Solution Designer

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =========================================================================
-- 1. SEQUENCES FOR HUMAN-READABLE DOCUMENT NUMBERS
-- =========================================================================

CREATE SEQUENCE rfq_seq START WITH 1;
CREATE SEQUENCE qtn_seq START WITH 1;
CREATE SEQUENCE po_seq START WITH 1;
CREATE SEQUENCE inv_seq START WITH 1;

-- =========================================================================
-- 2. CORE TABLES DEFINITION
-- =========================================================================

-- Table: users
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone_number VARCHAR(30) NOT NULL,
    CONSTRAINT chk_phone_length CHECK (length(phone_number) >= 10),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CONSTRAINT chk_user_role CHECK (role IN ('admin', 'officer', 'manager', 'vendor')),
    created_by_id UUID REFERENCES users(user_id) ON DELETE SET NULL, -- Audits manager/vendor creations
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Table: vendors
CREATE TABLE vendors (
    vendor_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    company_name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(150) NOT NULL,
    gst_number VARCHAR(15) NOT NULL UNIQUE,
    category VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CONSTRAINT chk_vendor_status CHECK (status IN ('pending', 'active', 'blocked')),
    created_by_id UUID REFERENCES users(user_id) ON DELETE SET NULL, -- Audits Admin/Officer creator
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_gst_length CHECK (length(gst_number) = 15)
);

-- Table: vendor_verification_tokens
CREATE TABLE vendor_verification_tokens (
    token_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vendor_id UUID NOT NULL REFERENCES vendors(vendor_id) ON DELETE CASCADE,
    token_string VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table: rfqs
CREATE TABLE rfqs (
    rfq_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_number VARCHAR(50) NOT NULL UNIQUE,
    created_by_id UUID NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT, -- Audits creating Officer
    status VARCHAR(50) NOT NULL DEFAULT 'draft' CONSTRAINT chk_rfq_status CHECK (status IN ('draft', 'open', 'closed', 'cancelled')),
    deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT chk_rfq_deadline_future CHECK (deadline > CURRENT_TIMESTAMP),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Table: rfq_items
CREATE TABLE rfq_items (
    rfq_item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(rfq_id) ON DELETE CASCADE,
    item_name VARCHAR(255) NOT NULL,
    description TEXT,
    quantity NUMERIC(15,4) NOT NULL,
    unit_of_measure VARCHAR(30) NOT NULL,
    CONSTRAINT chk_rfq_qty CHECK (quantity > 0)
);

-- Table: rfq_vendors
CREATE TABLE rfq_vendors (
    rfq_id UUID NOT NULL REFERENCES rfqs(rfq_id) ON DELETE CASCADE,
    vendor_id UUID NOT NULL REFERENCES vendors(vendor_id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rfq_id, vendor_id)
);

-- Table: quotations
CREATE TABLE quotations (
    quotation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_number VARCHAR(50) NOT NULL UNIQUE,
    rfq_id UUID NOT NULL REFERENCES rfqs(rfq_id) ON DELETE RESTRICT,
    vendor_id UUID NOT NULL REFERENCES vendors(vendor_id) ON DELETE RESTRICT,
    status VARCHAR(50) NOT NULL DEFAULT 'draft' CONSTRAINT chk_quotation_status CHECK (status IN ('draft', 'submitted', 'selected', 'rejected')),
    total_amount NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_quote_total CHECK (total_amount >= 0),
    CONSTRAINT uq_rfq_vendor UNIQUE (rfq_id, vendor_id) -- Restricts vendor to one bid per RFQ
);

-- Table: quotation_items
CREATE TABLE quotation_items (
    quotation_item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quotation_id UUID NOT NULL REFERENCES quotations(quotation_id) ON DELETE CASCADE,
    rfq_item_id UUID NOT NULL REFERENCES rfq_items(rfq_item_id) ON DELETE RESTRICT,
    unit_price NUMERIC(15,2) NOT NULL,
    quantity NUMERIC(15,4) NOT NULL,
    total_price NUMERIC(15,2) NOT NULL,
    CONSTRAINT chk_qtn_qty CHECK (quantity > 0),
    CONSTRAINT chk_qtn_price CHECK (unit_price >= 0),
    CONSTRAINT chk_qtn_total CHECK (total_price = quantity * unit_price)
);

-- Table: approvals
CREATE TABLE approvals (
    approval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quotation_id UUID NOT NULL UNIQUE REFERENCES quotations(quotation_id) ON DELETE RESTRICT,
    manager_id UUID NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT, -- Audits approving Manager
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CONSTRAINT chk_approval_status CHECK (status IN ('pending', 'approved', 'rejected')),
    remarks TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table: purchase_orders
CREATE TABLE purchase_orders (
    po_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_number VARCHAR(50) NOT NULL UNIQUE,
    quotation_id UUID NOT NULL UNIQUE REFERENCES quotations(quotation_id) ON DELETE RESTRICT,
    created_by_id UUID NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT, -- Audits generating Officer
    status VARCHAR(50) NOT NULL DEFAULT 'generated' CONSTRAINT chk_po_status CHECK (status IN ('generated', 'completed', 'cancelled')),
    total_amount NUMERIC(15,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    tax_rate NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_po_amount CHECK (total_amount >= 0),
    CONSTRAINT chk_po_tax CHECK (tax_rate >= 0 AND tax_rate <= 100)
);

-- Table: purchase_order_items (Line snapshotted history)
CREATE TABLE purchase_order_items (
    po_item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    po_id UUID NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    item_name VARCHAR(255) NOT NULL,
    description TEXT,
    quantity NUMERIC(15,4) NOT NULL,
    unit_price NUMERIC(15,2) NOT NULL,
    total_price NUMERIC(15,2) NOT NULL,
    CONSTRAINT chk_po_item_qty CHECK (quantity > 0),
    CONSTRAINT chk_po_item_price CHECK (unit_price >= 0),
    CONSTRAINT chk_po_item_total CHECK (total_price = quantity * unit_price)
);

-- Table: invoices
CREATE TABLE invoices (
    invoice_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_number VARCHAR(50) NOT NULL UNIQUE,
    po_id UUID NOT NULL UNIQUE REFERENCES purchase_orders(po_id) ON DELETE RESTRICT,
    vendor_id UUID NOT NULL REFERENCES vendors(vendor_id) ON DELETE RESTRICT,
    created_by_id UUID NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT, -- Audits processing Officer
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CONSTRAINT chk_invoice_status CHECK (status IN ('pending', 'paid', 'cancelled')),
    amount_due NUMERIC(15,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_inv_due CHECK (amount_due >= 0)
);

-- Table: invoice_items (Line snapshotted history)
CREATE TABLE invoice_items (
    invoice_item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id UUID NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    item_name VARCHAR(255) NOT NULL,
    quantity NUMERIC(15,4) NOT NULL,
    unit_price NUMERIC(15,2) NOT NULL,
    total_price NUMERIC(15,2) NOT NULL,
    CONSTRAINT chk_inv_item_qty CHECK (quantity > 0),
    CONSTRAINT chk_inv_item_price CHECK (unit_price >= 0),
    CONSTRAINT chk_inv_item_total CHECK (total_price = quantity * unit_price)
);

-- Table: notifications
CREATE TABLE notifications (
    notification_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table: activity_logs
CREATE TABLE activity_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_name VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 3. PERFORMANCE INDEXING
-- =========================================================================

-- Foreign Key Lookup Optimization Indexes
CREATE INDEX idx_users_creator ON users(created_by_id);
CREATE INDEX idx_vendors_user ON vendors(user_id);
CREATE INDEX idx_vendors_creator ON vendors(created_by_id);
CREATE INDEX idx_rfqs_creator ON rfqs(created_by_id);
CREATE INDEX idx_rfq_items_rfq ON rfq_items(rfq_id);
CREATE INDEX idx_quotations_rfq ON quotations(rfq_id);
CREATE INDEX idx_quotations_vendor ON quotations(vendor_id);
CREATE INDEX idx_quotation_items_quote ON quotation_items(quotation_id);
CREATE INDEX idx_approvals_quote ON approvals(quotation_id);
CREATE INDEX idx_purchase_orders_quote ON purchase_orders(quotation_id);
CREATE INDEX idx_purchase_orders_creator ON purchase_orders(created_by_id);
CREATE INDEX idx_purchase_order_items_po ON purchase_order_items(po_id);
CREATE INDEX idx_invoices_po ON invoices(po_id);
CREATE INDEX idx_invoices_vendor ON invoices(vendor_id);
CREATE INDEX idx_invoices_creator ON invoices(created_by_id);
CREATE INDEX idx_invoice_items_inv ON invoice_items(invoice_id);
CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_activity_logs_user ON activity_logs(user_id);

-- Composite Query Optimization Indexes
CREATE INDEX idx_rfqs_status_date ON rfqs(status, deadline);
CREATE INDEX idx_quotations_status_amount ON quotations(status, total_amount);
CREATE INDEX idx_activity_logs_search ON activity_logs(entity_name, entity_id);

-- Partial Indexes for Non-Deleted Items (Soft Delete Performance)
CREATE INDEX idx_users_active_not_deleted ON users(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_vendors_active_not_deleted ON vendors(vendor_id) WHERE deleted_at IS NULL;

-- =========================================================================
-- 4. TRIGGER FUNCTIONS FOR AUTOMATED DOCUMENT SEQUENCING (3-Digit Zero Padding)
-- =========================================================================

-- Trigger function for RFQ document code sequence (e.g. RFQ-2026-001)
CREATE OR REPLACE FUNCTION set_rfq_doc_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.doc_number IS NULL OR NEW.doc_number = '' THEN
        NEW.doc_number := 'RFQ-' || to_char(CURRENT_DATE, 'YYYY') || '-' || lpad(nextval('rfq_seq')::text, 3, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_rfq_doc_number
BEFORE INSERT ON rfqs
FOR EACH ROW
EXECUTE FUNCTION set_rfq_doc_number();


-- Trigger function for Quotation document code sequence (e.g. QTN-2026-001)
CREATE OR REPLACE FUNCTION set_qtn_doc_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.doc_number IS NULL OR NEW.doc_number = '' THEN
        NEW.doc_number := 'QTN-' || to_char(CURRENT_DATE, 'YYYY') || '-' || lpad(nextval('qtn_seq')::text, 3, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_qtn_doc_number
BEFORE INSERT ON quotations
FOR EACH ROW
EXECUTE FUNCTION set_qtn_doc_number();


-- Trigger function for Purchase Order document code sequence (e.g. PO-2026-001)
CREATE OR REPLACE FUNCTION set_po_doc_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.doc_number IS NULL OR NEW.doc_number = '' THEN
        NEW.doc_number := 'PO-' || to_char(CURRENT_DATE, 'YYYY') || '-' || lpad(nextval('po_seq')::text, 3, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_po_doc_number
BEFORE INSERT ON purchase_orders
FOR EACH ROW
EXECUTE FUNCTION set_po_doc_number();


-- Trigger function for Invoice document code sequence (e.g. INV-2026-001)
CREATE OR REPLACE FUNCTION set_inv_doc_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.doc_number IS NULL OR NEW.doc_number = '' THEN
        NEW.doc_number := 'INV-' || to_char(CURRENT_DATE, 'YYYY') || '-' || lpad(nextval('inv_seq')::text, 3, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_inv_doc_number
BEFORE INSERT ON invoices
FOR EACH ROW
EXECUTE FUNCTION set_inv_doc_number();

-- =========================================================================
-- 5. SYSTEM UPDATE TIMESTAMPS AUTOMATION TRIGGERS
-- =========================================================================

CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_users_timestamp BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_modified_column();
CREATE TRIGGER trg_update_vendors_timestamp BEFORE UPDATE ON vendors FOR EACH ROW EXECUTE FUNCTION update_modified_column();
CREATE TRIGGER trg_update_rfqs_timestamp BEFORE UPDATE ON rfqs FOR EACH ROW EXECUTE FUNCTION update_modified_column();
CREATE TRIGGER trg_update_quotations_timestamp BEFORE UPDATE ON quotations FOR EACH ROW EXECUTE FUNCTION update_modified_column();
CREATE TRIGGER trg_update_purchase_orders_timestamp BEFORE UPDATE ON purchase_orders FOR EACH ROW EXECUTE FUNCTION update_modified_column();
CREATE TRIGGER trg_update_invoices_timestamp BEFORE UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION update_modified_column();
