# VendorBridge - Entity Relationship Diagram (ERD)

This document visualizes the database structure of **VendorBridge** Procurement ERP.

## Mermaid ER Diagram

```mermaid
erDiagram
    users ||--o| vendors : "has profile (1:1)"
    users ||--o{ users : "creates manager/user (1:N)"
    users ||--o{ vendors : "registers (1:N)"
    users ||--o{ rfqs : "creates (1:N)"
    users ||--o{ approvals : "authorizes (1:N)"
    users ||--o{ notifications : "receives (1:N)"
    users ||--o{ activity_logs : "triggers (1:N)"
    
    vendors ||--o{ quotations : "submits (1:N)"
    vendors ||--o{ rfq_vendors : "assigned to (1:N)"
    vendors ||--o{ invoices : "bills (1:N)"
    
    rfqs ||--o{ rfq_items : "contains (1:N)"
    rfqs ||--o{ rfq_vendors : "invites (1:N)"
    rfqs ||--o{ quotations : "receives (1:N)"
    
    rfq_items ||--o{ quotation_items : "priced in (1:N)"
    
    quotations ||--o{ quotation_items : "contains (1:N)"
    quotations ||--o| approvals : "evaluated in (1:1)"
    quotations ||--o| purchase_orders : "converts to (1:1)"
    
    purchase_orders ||--o{ purchase_order_items : "contains (1:N)"
    purchase_orders ||--o| invoices : "billed by (1:1)"
    
    invoices ||--o{ invoice_items : "contains (1:N)"
    users ||--o{ invoices : "creates (1:N)"
    users ||--o{ purchase_orders : "creates (1:N)"

    users {
        uuid user_id PK
        varchar email UK
        varchar role
        uuid created_by_id FK
        varchar password_hash
        boolean is_active
        timestamp created_at
    }

    vendors {
        uuid vendor_id PK
        uuid user_id FK "UQ"
        varchar company_name
        varchar gst_number UK
        varchar status
        uuid created_by_id FK
        timestamp verified_at
    }

    rfqs {
        uuid rfq_id PK
        varchar doc_number UK
        uuid created_by_id FK
        varchar status
        timestamp deadline
        timestamp created_at
    }

    rfq_items {
        uuid rfq_item_id PK
        uuid rfq_id FK
        varchar item_name
        varchar description
        numeric quantity
        varchar unit_of_measure
    }

    rfq_vendors {
        uuid rfq_id PK, FK
        uuid vendor_id PK, FK
        timestamp assigned_at
    }

    quotations {
        uuid quotation_id PK
        varchar doc_number UK
        uuid rfq_id FK
        uuid vendor_id FK
        varchar status
        numeric total_amount
        timestamp created_at
    }

    quotation_items {
        uuid quotation_item_id PK
        uuid quotation_id FK
        uuid rfq_item_id FK
        numeric unit_price
        numeric quantity
        numeric total_price
    }

    approvals {
        uuid approval_id PK
        uuid quotation_id FK "UQ"
        uuid manager_id FK
        varchar status
        text remarks
        timestamp created_at
    }

    purchase_orders {
        uuid po_id PK
        varchar doc_number UK
        uuid quotation_id FK "UQ"
        uuid created_by_id FK
        varchar status
        numeric total_amount
        timestamp created_at
    }

    purchase_order_items {
        uuid po_item_id PK
        uuid po_id FK
        varchar item_name
        varchar description
        numeric quantity
        numeric unit_price
        numeric total_price
    }

    invoices {
        uuid invoice_id PK
        varchar doc_number UK
        uuid po_id FK "UQ"
        uuid vendor_id FK
        uuid created_by_id FK
        varchar status
        numeric amount_due
        timestamp created_at
    }

    invoice_items {
        uuid invoice_item_id PK
        uuid invoice_id FK
        varchar item_name
        numeric quantity
        numeric unit_price
        numeric total_price
    }

    notifications {
        uuid notification_id PK
        uuid user_id FK
        varchar title
        text message
        boolean is_read
        timestamp created_at
    }

    activity_logs {
        uuid log_id PK
        uuid user_id FK
        varchar action
        varchar entity_name
        uuid entity_id
        timestamp created_at
    }
```

## Relationship Definitions

1. **`users` ↔ `vendors` (One-to-One)**: Each Vendor profile has exactly one associated User credential record (`vendors.user_id` has a unique constraint).
2. **`rfqs` ↔ `rfq_items` (One-to-Many)**: A single Request for Quotation contains multiple distinct line items.
3. **`rfqs` ↔ `vendors` (Many-to-Many via `rfq_vendors`)**: An RFQ is sent to multiple vendors, and a vendor can be assigned to multiple RFQs.
4. **`rfqs` ↔ `quotations` (One-to-Many)**: An RFQ can gather multiple quotation bids, but each bid belongs to exactly one RFQ.
5. **`vendors` ↔ `quotations` (One-to-Many)**: A vendor can submit multiple bids, but a specific bid is unique to one vendor.
6. **`quotations` ↔ `quotation_items` (One-to-Many)**: Each quotation line belongs to one bid submission.
7. **`quotations` ↔ `approvals` (One-to-One)**: Each bid receives a single evaluation record by a Manager.
8. **`quotations` ↔ `purchase_orders` (One-to-One)**: An approved quotation converts to exactly one Purchase Order.
9. **`purchase_orders` ↔ `purchase_order_items` (One-to-Many)**: A PO contains copy snapshots of the awarded bid items.
10. **`purchase_orders` ↔ `invoices` (One-to-One)**: A PO matches to exactly one Invoice request.
11. **`invoices` ↔ `invoice_items` (One-to-Many)**: An invoice contains copy snapshots of the billed elements.
