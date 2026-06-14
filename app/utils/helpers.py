from datetime import datetime

from app.database import query_one


def generate_serial_no():
    try:
        now = datetime.now()
        prefix = now.strftime('%Y%m%d%H%M%S')
        count = query_one("SELECT COUNT(*) as cnt FROM issue_records WHERE serial_no LIKE %s", (prefix + '%',))
        seq = count['cnt'] + 1 if count and count['cnt'] is not None else 1
        return f"{prefix}{seq:03d}"
    except Exception:
        now = datetime.now()
        prefix = now.strftime('%Y%m%d%H%M%S')
        return f"{prefix}001"


def generate_shift_no():
    try:
        now = datetime.now()
        prefix = now.strftime('S%Y%m%d')
        count = query_one("SELECT COUNT(*) as cnt FROM shift_records WHERE shift_no LIKE %s", (prefix + '%',))
        seq = count['cnt'] + 1 if count and count['cnt'] is not None else 1
        return f"{prefix}{seq:03d}"
    except Exception:
        now = datetime.now()
        prefix = now.strftime('S%Y%m%d')
        return f"{prefix}001"


def generate_member_no():
    try:
        now = datetime.now()
        prefix = 'M' + now.strftime('%Y%m%d')
        count = query_one("SELECT COUNT(*) as cnt FROM members WHERE member_no LIKE %s", (prefix + '%',))
        seq = count['cnt'] + 1 if count and count['cnt'] is not None else 1
        return f"{prefix}{seq:04d}"
    except Exception:
        now = datetime.now()
        prefix = 'M' + now.strftime('%Y%m%d')
        return f"{prefix}0001"


def safe_count(sql, *params):
    try:
        result = query_one(sql, params)
        if result and result.get('cnt') is not None:
            return int(result['cnt'])
        if result and len(result) > 0:
            return int(list(result.values())[0])
        return 0
    except Exception:
        return 0


def safe_sum(sql, *params):
    try:
        result = query_one(sql, params)
        if result and result.get('total') is not None:
            return float(result['total'])
        if result and len(result) > 0:
            val = list(result.values())[0]
            return float(val) if val is not None else 0.0
        return 0.0
    except Exception:
        return 0.0


def parse_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_float(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_bool(value, default=False):
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            val = value.strip().lower()
            if val in ('true', '1', 'yes', 'on', 'y', 't'):
                return True
            if val in ('false', '0', 'no', 'off', 'n', 'f'):
                return False
        return default
    except Exception:
        return default
