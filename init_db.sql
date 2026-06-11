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

-- 手牌状态变更记录表
CREATE TABLE IF NOT EXISTS wristband_status_logs (
    id SERIAL PRIMARY KEY,
    wristband_id INTEGER REFERENCES wristbands(id) NOT NULL,
    issue_record_id INTEGER REFERENCES issue_records(id),
    old_status VARCHAR(20),
    new_status VARCHAR(20) NOT NULL,
    change_reason VARCHAR(100) NOT NULL,
    operator_id INTEGER REFERENCES users(id),
    phone VARCHAR(20),
    customer_name VARCHAR(100),
    remark TEXT,
    change_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wsl_wristband_id ON wristband_status_logs(wristband_id);
CREATE INDEX IF NOT EXISTS idx_wsl_change_time ON wristband_status_logs(change_time);
CREATE INDEX IF NOT EXISTS idx_wsl_issue_record_id ON wristband_status_logs(issue_record_id);

-- 异常预警记录表
CREATE TABLE IF NOT EXISTS warnings (
    id SERIAL PRIMARY KEY,
    warning_type VARCHAR(50) NOT NULL,
    warning_level VARCHAR(20) NOT NULL DEFAULT 'normal',
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    wristband_id INTEGER REFERENCES wristbands(id),
    issue_record_id INTEGER REFERENCES issue_records(id),
    bath_area_id INTEGER REFERENCES bath_areas(id),
    phone VARCHAR(20),
    related_data JSONB,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    read_by INTEGER REFERENCES users(id),
    read_time TIMESTAMP,
    resolved_by INTEGER REFERENCES users(id),
    resolved_time TIMESTAMP,
    resolve_note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_warnings_type ON warnings(warning_type);
CREATE INDEX IF NOT EXISTS idx_warnings_level ON warnings(warning_level);
CREATE INDEX IF NOT EXISTS idx_warnings_created ON warnings(created_at);
CREATE INDEX IF NOT EXISTS idx_warnings_read ON warnings(is_read);
CREATE INDEX IF NOT EXISTS idx_warnings_resolved ON warnings(is_resolved);

-- 创建默认浴区
INSERT INTO bath_areas (name, description, base_price, deposit_amount) VALUES
    ('男宾区', '男士洗浴区域', 38.00, 100.00),
    ('女宾区', '女士洗浴区域', 38.00, 100.00),
    ('VIP区', '贵宾洗浴区域', 88.00, 200.00)
ON CONFLICT (name) DO NOTHING;
