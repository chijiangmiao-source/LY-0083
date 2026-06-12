CREATE TABLE IF NOT EXISTS member_levels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    discount_rate NUMERIC(5,2) NOT NULL DEFAULT 100.00,
    deposit_discount_rate NUMERIC(5,2) NOT NULL DEFAULT 100.00,
    loss_fee_discount_rate NUMERIC(5,2) NOT NULL DEFAULT 100.00,
    reissue_fee_discount_rate NUMERIC(5,2) NOT NULL DEFAULT 100.00,
    min_top_up NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    description TEXT DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO member_levels (name, discount_rate, deposit_discount_rate, loss_fee_discount_rate, reissue_fee_discount_rate, min_top_up, description) VALUES
('普通会员', 100.00, 100.00, 100.00, 100.00, 0.00, '普通会员，无特殊折扣'),
('银卡会员', 95.00, 80.00, 90.00, 90.00, 500.00, '银卡会员，消费95折，押金8折'),
('金卡会员', 90.00, 60.00, 80.00, 80.00, 2000.00, '金卡会员，消费9折，押金6折'),
('钻石会员', 85.00, 0.00, 50.00, 50.00, 5000.00, '钻石会员，消费85折，押金全免');

CREATE TABLE IF NOT EXISTS members (
    id SERIAL PRIMARY KEY,
    member_no VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL DEFAULT '',
    phone VARCHAR(20) NOT NULL UNIQUE,
    gender VARCHAR(10) DEFAULT '',
    id_card VARCHAR(20) DEFAULT '',
    level_id INTEGER NOT NULL DEFAULT 1 REFERENCES member_levels(id),
    balance NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    total_top_up NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    total_consumption NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    total_package_deduction NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    registered_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMP,
    remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS member_packages (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    package_type VARCHAR(30) NOT NULL,
    total_count INTEGER,
    valid_days INTEGER,
    price NUMERIC(10,2) NOT NULL,
    original_value NUMERIC(10,2) NOT NULL,
    applicable_bath_area_ids INTEGER[] DEFAULT '{}',
    description TEXT DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS member_package_purchases (
    id SERIAL PRIMARY KEY,
    member_id INTEGER NOT NULL REFERENCES members(id),
    package_id INTEGER NOT NULL REFERENCES member_packages(id),
    purchase_price NUMERIC(10,2) NOT NULL,
    remaining_count INTEGER,
    total_count INTEGER,
    activated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expire_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS member_package_usages (
    id SERIAL PRIMARY KEY,
    purchase_id INTEGER NOT NULL REFERENCES member_package_purchases(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    issue_record_id INTEGER REFERENCES issue_records(id),
    deduction_amount NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    used_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS member_transactions (
    id SERIAL PRIMARY KEY,
    member_id INTEGER NOT NULL REFERENCES members(id),
    transaction_type VARCHAR(30) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    balance_after NUMERIC(12,2) NOT NULL,
    issue_record_id INTEGER REFERENCES issue_records(id),
    package_purchase_id INTEGER REFERENCES member_package_purchases(id),
    operator_id INTEGER REFERENCES users(id),
    remark TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS member_id INTEGER REFERENCES members(id);
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS package_deduction NUMERIC(10,2) NOT NULL DEFAULT 0.00;
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS balance_deduction NUMERIC(10,2) NOT NULL DEFAULT 0.00;
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS actual_deposit NUMERIC(10,2) NOT NULL DEFAULT 0.00;
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS member_discount_rate NUMERIC(5,2) NOT NULL DEFAULT 100.00;
ALTER TABLE issue_records ADD COLUMN IF NOT EXISTS member_deposit_rate NUMERIC(5,2) NOT NULL DEFAULT 100.00;

ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_consume_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_top_up_total NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_package_verify_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_balance_deduction NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_package_deduction NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_issue_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_package_purchase_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_gift_balance_used NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE shift_records ADD COLUMN IF NOT EXISTS member_new_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE members ADD COLUMN IF NOT EXISTS gift_balance NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE members ADD COLUMN IF NOT EXISTS total_gift NUMERIC(12,2) NOT NULL DEFAULT 0.00;
ALTER TABLE members ADD COLUMN IF NOT EXISTS auto_upgraded_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS member_topup_bonus_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    min_amount NUMERIC(10,2) NOT NULL,
    bonus_amount NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    bonus_percent NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    applicable_level_ids INTEGER[] DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    description TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS member_level_upgrade_logs (
    id SERIAL PRIMARY KEY,
    member_id INTEGER NOT NULL REFERENCES members(id),
    old_level_id INTEGER REFERENCES member_levels(id),
    new_level_id INTEGER NOT NULL REFERENCES member_levels(id),
    trigger_type VARCHAR(30) NOT NULL DEFAULT 'auto_topup',
    operator_id INTEGER REFERENCES users(id),
    remark TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS member_promotions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    promotion_type VARCHAR(30) NOT NULL,
    discount_rate NUMERIC(5,2) NOT NULL DEFAULT 100.00,
    applicable_level_ids INTEGER[] DEFAULT '{}',
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
