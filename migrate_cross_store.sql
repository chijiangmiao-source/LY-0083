CREATE TABLE IF NOT EXISTS stores (
    id SERIAL PRIMARY KEY,
    store_code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    address TEXT DEFAULT '',
    contact_phone VARCHAR(20) DEFAULT '',
    manager_name VARCHAR(100) DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_headquarters BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO stores (store_code, name, is_headquarters) VALUES
('HQ', '总部（默认门店）', TRUE)
ON CONFLICT (store_code) DO NOTHING;

ALTER TABLE bath_areas ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id);
ALTER TABLE wristbands ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id);
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id);
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES stores(id);
ALTER TABLE member_packages ADD COLUMN IF NOT EXISTS cross_store_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE members ADD COLUMN IF NOT EXISTS home_store_id INTEGER REFERENCES stores(id);
ALTER TABLE members ADD COLUMN IF NOT EXISTS balance_cross_store_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS is_cross_store BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS member_home_store_id INTEGER REFERENCES stores(id);
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS cross_store_deduction NUMERIC(12,2) NOT NULL DEFAULT 0.00;

ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS cross_store_income NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS cross_store_deduction NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS cross_store_issue_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS pending_clearing_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS hq_subsidy_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00;

CREATE TABLE IF NOT EXISTS store_clearing_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    rule_type VARCHAR(30) NOT NULL,
    source_store_id INTEGER REFERENCES stores(id),
    target_store_id INTEGER REFERENCES stores(id),
    source_ratio NUMERIC(5,2) NOT NULL DEFAULT 50.00,
    target_ratio NUMERIC(5,2) NOT NULL DEFAULT 50.00,
    hq_subsidy_ratio NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    hq_subsidy_max NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    applicable_level_ids INTEGER[] DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    description TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cross_store_records (
    id SERIAL PRIMARY KEY,
    member_id INTEGER NOT NULL REFERENCES members(id),
    issue_record_id INTEGER REFERENCES issue_records(id),
    home_store_id INTEGER NOT NULL REFERENCES stores(id),
    consume_store_id INTEGER NOT NULL REFERENCES stores(id),
    operation_type VARCHAR(30) NOT NULL,
    original_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    deduction_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    clearing_rule_id INTEGER REFERENCES store_clearing_rules(id),
    clearing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    settled_at TIMESTAMP,
    operator_id INTEGER REFERENCES users(id),
    remark TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clearing_records (
    id SERIAL PRIMARY KEY,
    cross_store_record_id INTEGER NOT NULL REFERENCES cross_store_records(id),
    store_id INTEGER NOT NULL REFERENCES stores(id),
    amount_type VARCHAR(30) NOT NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    settled_at TIMESTAMP,
    remark TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_csr_member_id ON cross_store_records(member_id);
CREATE INDEX IF NOT EXISTS idx_csr_home_store_id ON cross_store_records(home_store_id);
CREATE INDEX IF NOT EXISTS idx_csr_consume_store_id ON cross_store_records(consume_store_id);
CREATE INDEX IF NOT EXISTS idx_csr_clearing_status ON cross_store_records(clearing_status);
CREATE INDEX IF NOT EXISTS idx_csr_created_at ON cross_store_records(created_at);
CREATE INDEX IF NOT EXISTS idx_clr_store_id ON clearing_records(store_id);
CREATE INDEX IF NOT EXISTS idx_clr_status ON clearing_records(status);
CREATE INDEX IF NOT EXISTS idx_clr_cross_store_record_id ON clearing_records(cross_store_record_id);
CREATE INDEX IF NOT EXISTS idx_stores_active ON stores(is_active);

UPDATE bath_areas SET store_id = (SELECT id FROM stores WHERE is_headquarters = TRUE LIMIT 1) WHERE store_id IS NULL;
UPDATE wristbands SET store_id = (SELECT id FROM stores WHERE is_headquarters = TRUE LIMIT 1) WHERE store_id IS NULL;
UPDATE users SET store_id = (SELECT id FROM stores WHERE is_headquarters = TRUE LIMIT 1) WHERE store_id IS NULL;
UPDATE issue_records SET store_id = (SELECT id FROM stores WHERE is_headquarters = TRUE LIMIT 1) WHERE store_id IS NULL;
UPDATE shift_records SET store_id = (SELECT id FROM stores WHERE is_headquarters = TRUE LIMIT 1) WHERE store_id IS NULL;
UPDATE members SET home_store_id = (SELECT id FROM stores WHERE is_headquarters = TRUE LIMIT 1) WHERE home_store_id IS NULL;
