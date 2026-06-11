-- 创建数据库
-- CREATE DATABASE bathhouse;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'staff',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 浴区表
CREATE TABLE IF NOT EXISTS bath_areas (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    base_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    deposit_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 手牌表
CREATE TABLE IF NOT EXISTS wristbands (
    id SERIAL PRIMARY KEY,
    wristband_no VARCHAR(20) UNIQUE NOT NULL,
    bath_area_id INTEGER REFERENCES bath_areas(id),
    deposit_status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
    current_status VARCHAR(20) NOT NULL DEFAULT 'available',
    last_issued_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 发放记录表
CREATE TABLE IF NOT EXISTS issue_records (
    id SERIAL PRIMARY KEY,
    serial_no VARCHAR(50) UNIQUE NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    wristband_id INTEGER REFERENCES wristbands(id),
    bath_area_id INTEGER REFERENCES bath_areas(id),
    issue_time TIMESTAMP NOT NULL,
    return_time TIMESTAMP,
    base_fee DECIMAL(10, 2) DEFAULT 0.00,
    extra_fee DECIMAL(10, 2) DEFAULT 0.00,
    deposit_amount DECIMAL(10, 2) DEFAULT 0.00,
    fee_status VARCHAR(20) NOT NULL DEFAULT 'unsettled',
    lost_status VARCHAR(20) NOT NULL DEFAULT 'normal',
    loss_fee DECIMAL(10, 2) DEFAULT 0.00,
    reissue_fee DECIMAL(10, 2) DEFAULT 0.00,
    operator_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 遗失补办申请表
CREATE TABLE IF NOT EXISTS reissue_applications (
    id SERIAL PRIMARY KEY,
    issue_record_id INTEGER REFERENCES issue_records(id),
    report_time TIMESTAMP NOT NULL,
    reported_by VARCHAR(100),
    loss_description TEXT,
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    review_time TIMESTAMP,
    reviewer_id INTEGER REFERENCES users(id),
    review_comment TEXT,
    is_responsible BOOLEAN DEFAULT TRUE,
    new_wristband_id INTEGER REFERENCES wristbands(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 班次交接表
CREATE TABLE IF NOT EXISTS shift_records (
    id SERIAL PRIMARY KEY,
    shift_no VARCHAR(50) UNIQUE NOT NULL,
    operator_id INTEGER REFERENCES users(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    issue_count INTEGER DEFAULT 0,
    reissue_count INTEGER DEFAULT 0,
    unsettled_count INTEGER DEFAULT 0,
    total_income DECIMAL(10, 2) DEFAULT 0.00,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建默认管理员账户 (密码: admin123)
INSERT INTO users (username, password_hash, full_name, role) VALUES
    ('admin', 'pbkdf2:sha256:260000$admin$f5d57f628ef48f4484f033ddcbf0dfe753a49284b58623e7ba1db67e0b80f824', '系统管理员', 'admin')
ON CONFLICT (username) DO NOTHING;

-- 创建默认浴区
INSERT INTO bath_areas (name, description, base_price, deposit_amount) VALUES
    ('男宾区', '男士洗浴区域', 38.00, 100.00),
    ('女宾区', '女士洗浴区域', 38.00, 100.00),
    ('VIP区', '贵宾洗浴区域', 88.00, 200.00)
ON CONFLICT (name) DO NOTHING;
