import os
import json
from datetime import datetime, date
from functools import wraps
from hashlib import pbkdf2_hmac
from binascii import hexlify

from bottle import Bottle, request, response, redirect, static_file, template, abort

from db import query, query_one, execute, execute_and_return_id

app = Bottle()
SECRET_KEY = 'bathhouse-secret-key-2024'


def hash_password(password, salt='admin'):
    dk = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260000)
    return f'pbkdf2:sha256:260000${salt}${hexlify(dk).decode()}'


def verify_password(password, password_hash):
    parts = password_hash.split('$')
    if len(parts) != 3:
        return False
    _, salt, stored_hash = parts
    dk = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260000)
    return hexlify(dk).decode() == stored_hash


def get_session_user():
    session = request.get_cookie('session', secret=SECRET_KEY)
    if not session:
        return None
    try:
        data = json.loads(session)
        user = query_one('SELECT id, username, full_name, role FROM users WHERE id = %s', (data['user_id'],))
        return dict(user) if user else None
    except Exception:
        return None


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_session_user()
        if not user:
            redirect('/login')
        return f(*args, **kwargs)
    return wrapper


def get_active_shift(operator_id):
    return query_one(
        "SELECT * FROM shift_records WHERE operator_id = %s AND status = 'active' ORDER BY start_time DESC LIMIT 1",
        (operator_id,)
    )


def generate_serial_no():
    now = datetime.now()
    prefix = now.strftime('%Y%m%d%H%M%S')
    count = query_one("SELECT COUNT(*) as cnt FROM issue_records WHERE serial_no LIKE %s", (prefix + '%',))
    return f"{prefix}{count['cnt'] + 1:03d}"


def generate_shift_no():
    now = datetime.now()
    prefix = now.strftime('S%Y%m%d')
    count = query_one("SELECT COUNT(*) as cnt FROM shift_records WHERE shift_no LIKE %s", (prefix + '%',))
    return f"{prefix}{count['cnt'] + 1:03d}"


def phone_has_unsettled_loss(phone):
    if not phone:
        return False, []
    records = query('''
        SELECT ir.*, ra.review_status, ra.id as reissue_id
        FROM issue_records ir 
        LEFT JOIN reissue_applications ra ON ra.issue_record_id = ir.id 
        WHERE ir.phone = %s AND ir.lost_status = 'lost' AND ir.fee_status != 'settled'
        ORDER BY ir.issue_time DESC
    ''', (phone,))
    has_issue = len(records) > 0
    return has_issue, [dict(r) for r in records]


def log_status_change(wristband_id, new_status, change_reason, old_status=None,
                      issue_record_id=None, operator_id=None, phone=None,
                      customer_name=None, remark=None, change_time=None):
    if change_time is None:
        change_time = datetime.now()
    execute('''
        INSERT INTO wristband_status_logs
        (wristband_id, issue_record_id, old_status, new_status, change_reason,
         operator_id, phone, customer_name, remark, change_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (wristband_id, issue_record_id, old_status, new_status, change_reason,
          operator_id, phone, customer_name, remark, change_time))


def create_warning(warning_type, title, content, warning_level='normal',
                   wristband_id=None, issue_record_id=None, bath_area_id=None,
                   phone=None, related_data=None):
    import json as _json
    data_json = _json.dumps(related_data, ensure_ascii=False) if related_data else None
    execute('''
        INSERT INTO warnings
        (warning_type, warning_level, title, content, wristband_id,
         issue_record_id, bath_area_id, phone, related_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (warning_type, warning_level, title, content, wristband_id,
          issue_record_id, bath_area_id, phone, data_json))


def check_long_unreturned():
    from datetime import timedelta
    threshold_hours = 12
    threshold = datetime.now() - timedelta(hours=threshold_hours)
    records = query('''
        SELECT ir.*, w.wristband_no, ba.name as bath_area_name, u.full_name as operator_name
        FROM issue_records ir
        LEFT JOIN wristbands w ON ir.wristband_id = w.id
        LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
        LEFT JOIN users u ON ir.operator_id = u.id
        WHERE ir.return_time IS NULL AND ir.issue_time < %s
        ORDER BY ir.issue_time ASC
    ''', (threshold,))
    for r in records:
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'long_unreturned' AND issue_record_id = %s AND is_resolved = FALSE
        ''', (r['id'],))
        if not existing:
            hours = int((datetime.now() - r['issue_time']).total_seconds() / 3600)
            create_warning(
                warning_type='long_unreturned',
                warning_level='high',
                title=f'手牌[{r["wristband_no"]}]长时间未退回',
                content=f'手牌编号: {r["wristband_no"]}, 浴区: {r["bath_area_name"]}, '
                        f'客户: {r["customer_name"]}({r["phone"]}), '
                        f'发牌时间: {r["issue_time"].strftime("%Y-%m-%d %H:%M")}, '
                        f'已使用 {hours} 小时, 发牌操作员: {r["operator_name"]}',
                wristband_id=r['wristband_id'],
                issue_record_id=r['id'],
                bath_area_id=r['bath_area_id'],
                phone=r['phone'],
                related_data={'hours': hours, 'wristband_no': r['wristband_no']}
            )


def check_frequent_loss():
    from datetime import timedelta
    days_threshold = 30
    count_threshold = 2
    since = datetime.now() - timedelta(days=days_threshold)
    result = query('''
        SELECT phone, COUNT(*) as loss_count,
               ARRAY_AGG(ir.id) as record_ids,
               ARRAY_AGG(w.wristband_no) as wristband_nos
        FROM issue_records ir
        LEFT JOIN wristbands w ON ir.wristband_id = w.id
        WHERE ir.lost_status = 'lost' AND ir.created_at >= %s AND ir.phone != ''
        GROUP BY phone
        HAVING COUNT(*) >= %s
    ''', (since, count_threshold))
    for r in result:
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'frequent_loss' AND phone = %s AND is_resolved = FALSE
              AND created_at >= %s
        ''', (r['phone'], since))
        if not existing:
            create_warning(
                warning_type='frequent_loss',
                warning_level='high',
                title=f'手机号[{r["phone"]}]短期内频繁遗失',
                content=f'手机号 {r["phone"]} 在 {days_threshold} 天内申报遗失 {r["loss_count"]} 次, '
                        f'涉及手牌: {", ".join(filter(None, r["wristband_nos"]))}',
                phone=r['phone'],
                related_data={
                    'loss_count': r['loss_count'],
                    'days': days_threshold,
                    'wristband_nos': r['wristband_nos']
                }
            )


def check_continuous_reissue_in_area():
    from datetime import timedelta
    hours_threshold = 24
    count_threshold = 3
    since = datetime.now() - timedelta(hours=hours_threshold)
    result = query('''
        SELECT ir.bath_area_id, ba.name as bath_area_name,
               COUNT(DISTINCT ra.id) as reissue_count,
               ARRAY_AGG(DISTINCT w.wristband_no) as wristband_nos
        FROM reissue_applications ra
        LEFT JOIN issue_records ir ON ra.issue_record_id = ir.id
        LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
        LEFT JOIN wristbands w ON ra.new_wristband_id = w.id
        WHERE ra.review_status = 'approved' AND ra.review_time >= %s
        GROUP BY ir.bath_area_id, ba.name
        HAVING COUNT(DISTINCT ra.id) >= %s
    ''', (since, count_threshold))
    for r in result:
        if not r['bath_area_id']:
            continue
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'continuous_reissue' AND bath_area_id = %s AND is_resolved = FALSE
              AND created_at >= %s
        ''', (r['bath_area_id'], since))
        if not existing:
            create_warning(
                warning_type='continuous_reissue',
                warning_level='medium',
                title=f'浴区[{r["bath_area_name"]}]连续出现补办',
                content=f'浴区 {r["bath_area_name"]} 在 {hours_threshold} 小时内补办 {r["reissue_count"]} 次, '
                        f'新手牌: {", ".join(filter(None, r["wristband_nos"]))}',
                bath_area_id=r['bath_area_id'],
                related_data={
                    'reissue_count': r['reissue_count'],
                    'hours': hours_threshold,
                    'bath_area_name': r['bath_area_name']
                }
            )


def check_frozen_misuse(wristband_id, action, operator_id):
    band = query_one("SELECT * FROM wristbands WHERE id = %s", (wristband_id,))
    if band and band['current_status'] == 'frozen':
        user = query_one("SELECT full_name FROM users WHERE id = %s", (operator_id,))
        create_warning(
            warning_type='frozen_misuse',
            warning_level='high',
            title=f'冻结手牌[{band["wristband_no"]}]被误操作',
            content=f'冻结手牌 {band["wristband_no"]} 被操作员 {user["full_name"] if user else "未知"} '
                    f'尝试执行操作: {action}, 请及时核查',
            wristband_id=wristband_id,
            related_data={
                'action': action,
                'operator_id': operator_id,
                'operator_name': user['full_name'] if user else None
            }
        )


def run_all_warning_checks():
    try:
        check_long_unreturned()
    except Exception:
        pass
    try:
        check_frequent_loss()
    except Exception:
        pass
    try:
        check_continuous_reissue_in_area()
    except Exception:
        pass


def get_unread_warning_stats():
    stats = {
        'total_unread': 0,
        'high_count': 0,
        'medium_count': 0,
        'normal_count': 0,
        'unresolved_count': 0
    }
    try:
        total = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE")
        stats['total_unread'] = int(total['cnt']) if total else 0
        high = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE AND warning_level = 'high'")
        stats['high_count'] = int(high['cnt']) if high else 0
        medium = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE AND warning_level = 'medium'")
        stats['medium_count'] = int(medium['cnt']) if medium else 0
        normal = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE AND warning_level = 'normal'")
        stats['normal_count'] = int(normal['cnt']) if normal else 0
        unresolved = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_resolved = FALSE")
        stats['unresolved_count'] = int(unresolved['cnt']) if unresolved else 0
    except Exception:
        pass
    return stats


def dict_to_json(data):
    if data is None:
        return None
    if isinstance(data, list):
        return [dict(row) for row in data]
    return dict(data)


def json_response(data, success=True, message=''):
    response.content_type = 'application/json'
    return json.dumps({
        'success': success,
        'message': message,
        'data': dict_to_json(data) if data else None
    }, default=str, ensure_ascii=False)


def to_template_json(data):
    if data is None:
        return 'null'
    return json.dumps(dict_to_json(data) if not isinstance(data, (dict, list)) else data, default=str, ensure_ascii=False)


@app.route('/static/<filepath:path>')
def server_static(filepath):
    return static_file(filepath, root='./static')


@app.route('/login', method='GET')
def login_page():
    return template('templates/login.html', error='')


@app.route('/login', method='POST')
def login_post():
    data = request.json if request.json else request.forms
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user = query_one('SELECT * FROM users WHERE username = %s', (username,))
    if not user or not verify_password(password, user['password_hash']):
        if request.json:
            return json_response(None, False, '用户名或密码错误')
        return template('templates/login.html', error='用户名或密码错误')

    session_data = json.dumps({'user_id': user['id']})
    response.set_cookie('session', session_data, secret=SECRET_KEY, path='/', max_age=86400)

    operator_id = user['id']
    active_shift = get_active_shift(operator_id)
    if not active_shift:
        shift_no = generate_shift_no()
        execute(
            "INSERT INTO shift_records (shift_no, operator_id, start_time) VALUES (%s, %s, %s)",
            (shift_no, operator_id, datetime.now())
        )

    if request.json:
        return json_response({'redirect': '/'})
    redirect('/')


@app.route('/logout')
def logout():
    user = get_session_user()
    if user:
        active_shift = get_active_shift(user['id'])
        if active_shift:
            execute(
                "UPDATE shift_records SET status = 'closed', end_time = %s WHERE id = %s",
                (datetime.now(), active_shift['id'])
            )
    response.delete_cookie('session', path='/')
    redirect('/login')


@app.route('/')
@require_login
def index():
    user = get_session_user()
    run_all_warning_checks()
    def safe_count(sql, *params):
        try:
            r = query_one(sql, params)
            return int(r['cnt']) if r else 0
        except Exception:
            return 0
    stats = {
        'available_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'available'"),
        'issued_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'issued'"),
        'frozen_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'frozen'"),
        'unsettled': safe_count("SELECT COUNT(*) as cnt FROM issue_records WHERE fee_status = 'unsettled' AND return_time IS NULL"),
        'pending_review': safe_count("SELECT COUNT(*) as cnt FROM reissue_applications WHERE review_status = 'pending'"),
    }
    warning_stats = get_unread_warning_stats()
    recent_warnings = []
    try:
        rows = query('''
            SELECT w.*, u1.full_name as read_by_name, u2.full_name as resolved_by_name,
                   wr.wristband_no, ba.name as bath_area_name
            FROM warnings w
            LEFT JOIN users u1 ON w.read_by = u1.id
            LEFT JOIN users u2 ON w.resolved_by = u2.id
            LEFT JOIN wristbands wr ON w.wristband_id = wr.id
            LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id
            ORDER BY w.created_at DESC LIMIT 20
        ''')
        recent_warnings = [dict(r) for r in rows]
    except Exception:
        pass
    return template(
        'templates/index.html',
        user=user,
        stats=stats,
        warning_stats_json=to_template_json(warning_stats),
        recent_warnings_json=to_template_json(recent_warnings)
    )


@app.route('/bath-areas')
@require_login
def bath_areas_page():
    user = get_session_user()
    return template('templates/bath_areas.html', user=user)


@app.route('/api/bath-areas', method='GET')
@require_login
def api_bath_areas():
    areas = query('SELECT * FROM bath_areas ORDER BY id')
    return json_response(areas)


@app.route('/api/bath-areas', method='POST')
@require_login
def api_create_bath_area():
    data = request.json
    try:
        execute(
            "INSERT INTO bath_areas (name, description, base_price, deposit_amount) VALUES (%s, %s, %s, %s)",
            (data['name'], data.get('description', ''), float(data['base_price']), float(data['deposit_amount']))
        )
        return json_response(None, True, '创建成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/bath-areas/<area_id:int>', method='PUT')
@require_login
def api_update_bath_area(area_id):
    data = request.json
    try:
        execute(
            "UPDATE bath_areas SET name=%s, description=%s, base_price=%s, deposit_amount=%s, is_active=%s WHERE id=%s",
            (data['name'], data.get('description', ''), float(data['base_price']), float(data['deposit_amount']), data.get('is_active', True), area_id)
        )
        return json_response(None, True, '更新成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/bath-areas/<area_id:int>', method='DELETE')
@require_login
def api_delete_bath_area(area_id):
    has_bands = query_one("SELECT COUNT(*) as cnt FROM wristbands WHERE bath_area_id = %s", (area_id,))
    if has_bands['cnt'] > 0:
        return json_response(None, False, '该浴区下还有手牌，无法删除')
    execute("DELETE FROM bath_areas WHERE id = %s", (area_id,))
    return json_response(None, True, '删除成功')


@app.route('/wristbands')
@require_login
def wristbands_page():
    user = get_session_user()
    areas = query('SELECT * FROM bath_areas WHERE is_active = TRUE ORDER BY id')
    return template('templates/wristbands.html', user=user, areas_json=to_template_json(areas))


@app.route('/api/wristbands', method='GET')
@require_login
def api_wristbands():
    status = request.query.get('status', '')
    area_id = request.query.get('area_id', '')
    sql = '''SELECT w.*, ba.name as bath_area_name FROM wristbands w 
             LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id WHERE 1=1'''
    params = []
    if status:
        sql += " AND w.current_status = %s"
        params.append(status)
    if area_id:
        sql += " AND w.bath_area_id = %s"
        params.append(int(area_id))
    sql += ' ORDER BY w.id DESC'
    bands = query(sql, params)
    return json_response(bands)


@app.route('/api/wristbands', method='POST')
@require_login
def api_create_wristband():
    data = request.json
    user = get_session_user()
    exists = query_one("SELECT id FROM wristbands WHERE wristband_no = %s", (data['wristband_no'],))
    if exists:
        return json_response(None, False, '手牌编号已存在')
    try:
        execute(
            "INSERT INTO wristbands (wristband_no, bath_area_id, current_status) VALUES (%s, %s, 'available')",
            (data['wristband_no'], data.get('bath_area_id'))
        )
        new_band = query_one("SELECT * FROM wristbands WHERE wristband_no = %s", (data['wristband_no'],))
        if new_band:
            log_status_change(
                wristband_id=new_band['id'],
                old_status=None,
                new_status='available',
                change_reason='手牌创建',
                operator_id=user['id'],
                remark=data.get('bath_area_id') and f'初始浴区ID: {data.get("bath_area_id")}' or '未指定浴区'
            )
        return json_response(None, True, '创建成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/wristbands/<band_id:int>', method='PUT')
@require_login
def api_update_wristband(band_id):
    data = request.json
    user = get_session_user()
    try:
        band = query_one("SELECT * FROM wristbands WHERE id = %s", (band_id,))
        if not band:
            return json_response(None, False, '手牌不存在')
        old_area_id = band['bath_area_id']
        new_area_id = data.get('bath_area_id')
        old_area = query_one("SELECT name FROM bath_areas WHERE id = %s", (old_area_id,)) if old_area_id else None
        new_area = query_one("SELECT name FROM bath_areas WHERE id = %s", (new_area_id,)) if new_area_id else None
        execute(
            "UPDATE wristbands SET bath_area_id=%s WHERE id=%s",
            (new_area_id, band_id)
        )
        area_changed = (old_area_id or None) != (new_area_id or None)
        if area_changed:
            log_status_change(
                wristband_id=band_id,
                old_status=band['current_status'],
                new_status=band['current_status'],
                change_reason='浴区变更',
                operator_id=user['id'],
                remark=f'从 {old_area["name"] if old_area else "无"} 调整为 {new_area["name"] if new_area else "无"}'
            )
        return json_response(None, True, '更新成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/wristbands/<band_id:int>', method='DELETE')
@require_login
def api_delete_wristband(band_id):
    user = get_session_user()
    band = query_one("SELECT * FROM wristbands WHERE id = %s", (band_id,))
    if not band:
        return json_response(None, False, '手牌不存在')
    if band['current_status'] == 'issued':
        return json_response(None, False, '手牌已发放，无法删除')
    log_status_change(
        wristband_id=band_id,
        old_status=band['current_status'],
        new_status=None,
        change_reason='手牌删除',
        operator_id=user['id'],
        remark=f'手牌编号: {band["wristband_no"]}'
    )
    execute("DELETE FROM wristbands WHERE id = %s", (band_id,))
    return json_response(None, True, '删除成功')


@app.route('/issue')
@require_login
def issue_page():
    user = get_session_user()
    areas = query('SELECT * FROM bath_areas WHERE is_active = TRUE ORDER BY id')
    return template('templates/issue.html', user=user, areas_json=to_template_json(areas))


@app.route('/api/issue/available-bands', method='GET')
@require_login
def api_available_bands():
    area_id = request.query.get('area_id', '')
    sql = '''SELECT w.*, ba.name as bath_area_name, ba.base_price, ba.deposit_amount 
             FROM wristbands w LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id 
             WHERE w.current_status = 'available' '''
    params = []
    if area_id:
        sql += " AND w.bath_area_id = %s"
        params.append(int(area_id))
    sql += ' ORDER BY w.wristband_no'
    bands = query(sql, params)
    return json_response(bands)


@app.route('/api/issue/check-phone', method='GET')
@require_login
def api_check_phone():
    phone = request.query.get('phone', '')
    if not phone:
        return json_response({'can_issue': True})
    has_issue, records = phone_has_unsettled_loss(phone)
    return json_response({'can_issue': not has_issue, 'records': records})


@app.route('/api/issue', method='POST')
@require_login
def api_issue_band():
    data = request.json
    user = get_session_user()

    wristband_id = data.get('wristband_id')
    phone = data.get('phone', '').strip()

    band = query_one("SELECT * FROM wristbands WHERE id = %s", (wristband_id,))
    if not band:
        return json_response(None, False, '手牌不存在')
    if band['current_status'] != 'available':
        return json_response(None, False, '该手牌当前不可用')

    has_issue, _ = phone_has_unsettled_loss(phone)
    if has_issue:
        return json_response(None, False, '该手机号存在未结清遗失记录，无法领牌')

    area = query_one("SELECT * FROM bath_areas WHERE id = %s", (band['bath_area_id'],))
    serial_no = generate_serial_no()
    issue_time = datetime.now()

    execute('''
        INSERT INTO issue_records 
        (serial_no, customer_name, phone, wristband_id, bath_area_id, issue_time, 
         base_fee, deposit_amount, operator_id, fee_status, lost_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'unsettled', 'normal')
    ''', (
        serial_no, data.get('customer_name', ''), phone, wristband_id,
        band['bath_area_id'], issue_time,
        area['base_price'] if area else 0, area['deposit_amount'] if area else 0,
        user['id']
    ))

    execute(
        "UPDATE wristbands SET current_status = 'issued', last_issued_at = %s WHERE id = %s",
        (issue_time, wristband_id)
    )

    new_record = query_one("SELECT id FROM issue_records WHERE serial_no = %s", (serial_no,))
    log_status_change(
        wristband_id=wristband_id,
        old_status=band['current_status'],
        new_status='issued',
        change_reason='入场发牌',
        issue_record_id=new_record['id'] if new_record else None,
        operator_id=user['id'],
        phone=phone,
        customer_name=data.get('customer_name', ''),
        change_time=issue_time
    )

    shift = get_active_shift(user['id'])
    if shift:
        execute("UPDATE shift_records SET issue_count = issue_count + 1 WHERE id = %s", (shift['id'],))

    record = query_one("SELECT * FROM issue_records WHERE serial_no = %s", (serial_no,))
    return json_response(record, True, '发牌成功')


@app.route('/return')
@require_login
def return_page():
    user = get_session_user()
    return template('templates/return.html', user=user)


@app.route('/api/return/search', method='GET')
@require_login
def api_return_search():
    keyword = request.query.get('keyword', '').strip()
    sql = '''SELECT ir.*, w.wristband_no, ba.name as bath_area_name, u.full_name as operator_name
             FROM issue_records ir 
             LEFT JOIN wristbands w ON ir.wristband_id = w.id
             LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
             LEFT JOIN users u ON ir.operator_id = u.id
             WHERE ir.return_time IS NULL AND (
                 ir.serial_no LIKE %s OR w.wristband_no LIKE %s OR ir.phone LIKE %s OR ir.customer_name LIKE %s
             ) ORDER BY ir.issue_time DESC'''
    like = f'%{keyword}%'
    records = query(sql, (like, like, like, like))
    return json_response(records)


@app.route('/api/return/<record_id:int>', method='POST')
@require_login
def api_return_band(record_id):
    data = request.json
    user = get_session_user()

    record = query_one("SELECT * FROM issue_records WHERE id = %s", (record_id,))
    if not record:
        return json_response(None, False, '记录不存在')
    if record['return_time']:
        return json_response(None, False, '该记录已退牌')

    band = query_one("SELECT * FROM wristbands WHERE id = %s", (record['wristband_id'],))
    if band and band['current_status'] == 'frozen':
        check_frozen_misuse(record['wristband_id'], '退牌结算', user['id'])
        return json_response(None, False, '该手牌已冻结，无法退回流转')

    return_time = datetime.now()
    if return_time < record['issue_time']:
        return json_response(None, False, '退牌时间不能早于发牌时间')

    extra_fee = float(data.get('extra_fee', 0) or 0)
    loss_fee = float(data.get('loss_fee', 0) or 0)
    reissue_fee = float(data.get('reissue_fee', 0) or 0)
    deposit_status = data.get('deposit_status', 'returned')

    total_fee = (record['base_fee'] or 0) + extra_fee + loss_fee + reissue_fee

    old_band_status = band['current_status'] if band else None

    execute('''
        UPDATE issue_records SET return_time=%s, extra_fee=%s, loss_fee=%s, reissue_fee=%s, fee_status='settled'
        WHERE id=%s
    ''', (return_time, extra_fee, loss_fee, reissue_fee, record_id))

    if band and band['current_status'] != 'frozen':
        execute(
            "UPDATE wristbands SET current_status = 'available', deposit_status = %s WHERE id = %s",
            (deposit_status, band['id'])
        )
        log_status_change(
            wristband_id=band['id'],
            old_status=old_band_status,
            new_status='available',
            change_reason='退牌结算',
            issue_record_id=record_id,
            operator_id=user['id'],
            phone=record['phone'],
            customer_name=record['customer_name'],
            remark=f'总费用: {total_fee}元, 押金状态: {deposit_status}',
            change_time=return_time
        )

    shift = get_active_shift(user['id'])
    if shift:
        execute(
            "UPDATE shift_records SET total_income = total_income + %s WHERE id = %s",
            (total_fee, shift['id'])
        )

    return json_response({'total_fee': total_fee}, True, '退牌结算成功')


@app.route('/report-loss')
@require_login
def report_loss_page():
    user = get_session_user()
    return template('templates/report_loss.html', user=user)


@app.route('/api/loss/search', method='GET')
@require_login
def api_loss_search():
    keyword = request.query.get('keyword', '').strip()
    sql = '''SELECT ir.*, w.wristband_no, ba.name as bath_area_name
             FROM issue_records ir 
             LEFT JOIN wristbands w ON ir.wristband_id = w.id
             LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
             WHERE ir.return_time IS NULL AND ir.lost_status = 'normal' AND (
                 ir.serial_no LIKE %s OR w.wristband_no LIKE %s OR ir.phone LIKE %s OR ir.customer_name LIKE %s
             ) ORDER BY ir.issue_time DESC'''
    like = f'%{keyword}%'
    records = query(sql, (like, like, like, like))
    return json_response(records)


@app.route('/api/loss/report', method='POST')
@require_login
def api_report_loss():
    data = request.json
    user = get_session_user()

    record_id = data.get('issue_record_id')
    record = query_one("SELECT * FROM issue_records WHERE id = %s", (record_id,))
    if not record:
        return json_response(None, False, '记录不存在')
    if record['lost_status'] != 'normal':
        return json_response(None, False, '该记录已申报遗失')

    loss_time = datetime.now()

    execute(
        "UPDATE issue_records SET lost_status = 'lost' WHERE id = %s",
        (record_id,)
    )

    if record['wristband_id']:
        band = query_one("SELECT * FROM wristbands WHERE id = %s", (record['wristband_id'],))
        old_status = band['current_status'] if band else None
        execute(
            "UPDATE wristbands SET current_status = 'frozen' WHERE id = %s",
            (record['wristband_id'],)
        )
        log_status_change(
            wristband_id=record['wristband_id'],
            old_status=old_status,
            new_status='frozen',
            change_reason='遗失申报冻结',
            issue_record_id=record_id,
            operator_id=user['id'],
            phone=record['phone'],
            customer_name=record['customer_name'],
            remark=data.get('loss_description', ''),
            change_time=loss_time
        )

    execute('''
        INSERT INTO reissue_applications 
        (issue_record_id, report_time, reported_by, loss_description)
        VALUES (%s, %s, %s, %s)
    ''', (record_id, loss_time, user['full_name'], data.get('loss_description', '')))

    try:
        check_frequent_loss()
    except Exception:
        pass

    return json_response(None, True, '遗失申报成功，原手牌已冻结')


@app.route('/reissue-review')
@require_login
def reissue_review_page():
    user = get_session_user()
    return template('templates/reissue_review.html', user=user)


@app.route('/api/reissue/pending', method='GET')
@require_login
def api_reissue_pending():
    records = query('''
        SELECT ra.*, ir.serial_no, ir.customer_name, ir.phone, ir.base_fee, ir.deposit_amount,
               w.wristband_no as old_wristband_no, ba.name as bath_area_name
        FROM reissue_applications ra
        LEFT JOIN issue_records ir ON ra.issue_record_id = ir.id
        LEFT JOIN wristbands w ON ir.wristband_id = w.id
        LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
        ORDER BY ra.report_time DESC
    ''')
    return json_response(records)


@app.route('/api/reissue/<app_id:int>/review', method='POST')
@require_login
def api_review_reissue(app_id):
    data = request.json
    user = get_session_user()

    app = query_one("SELECT * FROM reissue_applications WHERE id = %s", (app_id,))
    if not app:
        return json_response(None, False, '申请不存在')
    if app['review_status'] != 'pending':
        return json_response(None, False, '该申请已审核')

    decision = data.get('decision')
    is_responsible = data.get('is_responsible', True)
    loss_fee = float(data.get('loss_fee', 0) or 0)
    reissue_fee = float(data.get('reissue_fee', 0) or 0)
    new_wristband_id = data.get('new_wristband_id')
    review_time = datetime.now()

    if decision == 'reject':
        execute('''
            UPDATE reissue_applications SET review_status='rejected', review_time=%s, reviewer_id=%s, review_comment=%s
            WHERE id=%s
        ''', (review_time, user['id'], data.get('review_comment', ''), app_id))
        record = query_one("SELECT * FROM issue_records WHERE id = %s", (app['issue_record_id'],))
        if record and record['wristband_id']:
            band = query_one("SELECT * FROM wristbands WHERE id = %s", (record['wristband_id'],))
            old_status = band['current_status'] if band else None
            execute(
                "UPDATE wristbands SET current_status = 'issued' WHERE id = %s AND current_status = 'frozen'",
                (record['wristband_id'],)
            )
            if band and band['current_status'] == 'frozen':
                log_status_change(
                    wristband_id=record['wristband_id'],
                    old_status='frozen',
                    new_status='issued',
                    change_reason='补办审核驳回，解除冻结',
                    issue_record_id=record['id'],
                    operator_id=user['id'],
                    phone=record['phone'],
                    customer_name=record['customer_name'],
                    remark=data.get('review_comment', ''),
                    change_time=review_time
                )
        return json_response(None, True, '审核驳回成功')

    record = query_one("SELECT * FROM issue_records WHERE id = %s", (app['issue_record_id'],))
    old_wristband_id = record['wristband_id'] if record else None

    execute('''
        UPDATE reissue_applications 
        SET review_status='approved', review_time=%s, reviewer_id=%s, review_comment=%s,
            is_responsible=%s, new_wristband_id=%s
        WHERE id=%s
    ''', (review_time, user['id'], data.get('review_comment', ''), is_responsible, new_wristband_id, app_id))

    execute('''
        UPDATE issue_records SET loss_fee=%s, reissue_fee=%s WHERE id=%s
    ''', (loss_fee, reissue_fee, app['issue_record_id']))

    if new_wristband_id:
        new_band = query_one("SELECT * FROM wristbands WHERE id = %s", (new_wristband_id,))
        if new_band and new_band['current_status'] == 'available':
            if old_wristband_id and old_wristband_id != new_wristband_id:
                execute(
                    "UPDATE wristbands SET current_status = 'replaced' WHERE id = %s",
                    (old_wristband_id,)
                )
                log_status_change(
                    wristband_id=old_wristband_id,
                    old_status='frozen',
                    new_status='replaced',
                    change_reason='补办替换，旧手牌作废',
                    issue_record_id=app['issue_record_id'],
                    operator_id=user['id'],
                    phone=record['phone'] if record else None,
                    customer_name=record['customer_name'] if record else None,
                    remark=f'补办新手牌ID: {new_wristband_id}, 赔偿费: {loss_fee}元, 补办费: {reissue_fee}元',
                    change_time=review_time
                )
            execute(
                "UPDATE wristbands SET current_status = 'issued', last_issued_at = %s WHERE id = %s",
                (review_time, new_wristband_id)
            )
            log_status_change(
                wristband_id=new_wristband_id,
                old_status='available',
                new_status='issued',
                change_reason='补办发牌',
                issue_record_id=app['issue_record_id'],
                operator_id=user['id'],
                phone=record['phone'] if record else None,
                customer_name=record['customer_name'] if record else None,
                remark=f'补办替换, 赔偿费: {loss_fee}元, 补办费: {reissue_fee}元',
                change_time=review_time
            )
            execute(
                "UPDATE issue_records SET wristband_id = %s WHERE id = %s",
                (new_wristband_id, app['issue_record_id'])
            )

    try:
        check_continuous_reissue_in_area()
    except Exception:
        pass

    shift = get_active_shift(user['id'])
    if shift:
        execute("UPDATE shift_records SET reissue_count = reissue_count + 1 WHERE id = %s", (shift['id'],))

    return json_response(None, True, '审核通过成功')


@app.route('/shift-summary')
@require_login
def shift_summary_page():
    user = get_session_user()
    run_all_warning_checks()
    shift = get_active_shift(user['id'])
    if not shift:
        return template('templates/shift_summary.html', user=user, shift_json='null', records_json='[]', summary_json='null',
                        warning_stats_json=to_template_json({'total_unread':0,'high_count':0,'medium_count':0,'normal_count':0,'unresolved_count':0}),
                        shift_warnings_json='[]')

    records = query('''
        SELECT ir.*, w.wristband_no, ba.name as bath_area_name,
               CASE WHEN ra.id IS NOT NULL THEN TRUE ELSE FALSE END as has_reissue
        FROM issue_records ir
        LEFT JOIN wristbands w ON ir.wristband_id = w.id
        LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
        LEFT JOIN reissue_applications ra ON ra.issue_record_id = ir.id
        WHERE ir.operator_id = %s AND ir.issue_time >= %s
        ORDER BY ir.issue_time DESC
    ''', (user['id'], shift['start_time']))

    unsettled = [r for r in records if r['fee_status'] != 'settled']
    reissues = [r for r in records if r.get('has_reissue')]

    summary_data = {
        'issue_count': len(records),
        'reissue_count': len(reissues),
        'unsettled_count': len(unsettled),
        'total_income': sum(float(r['base_fee'] or 0) + float(r['extra_fee'] or 0) + float(r['loss_fee'] or 0) + float(r['reissue_fee'] or 0) for r in records if r['fee_status'] == 'settled')
    }

    warning_stats = get_unread_warning_stats()
    shift_warnings = []
    try:
        record_ids = [r['id'] for r in records]
        if record_ids:
            placeholders = ','.join(['%s'] * len(record_ids))
            rows = query(f'''
                SELECT w.*, wr.wristband_no, ba.name as bath_area_name
                FROM warnings w
                LEFT JOIN wristbands wr ON w.wristband_id = wr.id
                LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id
                WHERE w.issue_record_id IN ({placeholders})
                  AND w.issue_record_id IS NOT NULL
                ORDER BY w.created_at DESC
            ''', record_ids)
            shift_warnings = [dict(r) for r in rows]
    except Exception:
        pass

    return template('templates/shift_summary.html', user=user, shift_json=to_template_json(shift),
                    records_json=to_template_json(records), summary_json=to_template_json(summary_data),
                    warning_stats_json=to_template_json(warning_stats),
                    shift_warnings_json=to_template_json(shift_warnings))


@app.route('/api/shift/close', method='POST')
@require_login
def api_close_shift():
    user = get_session_user()
    shift = get_active_shift(user['id'])
    if not shift:
        return json_response(None, False, '没有活跃的班次')

    unsettled = query_one('''
        SELECT COUNT(*) as cnt FROM issue_records 
        WHERE operator_id = %s AND issue_time >= %s AND fee_status != 'settled'
    ''', (user['id'], shift['start_time']))

    if unsettled['cnt'] > 0:
        return json_response(None, False, f'还有 {unsettled["cnt"]} 条未结算记录，无法交接')

    execute(
        "UPDATE shift_records SET status = 'closed', end_time = %s WHERE id = %s",
        (datetime.now(), shift['id'])
    )

    shift_no = generate_shift_no()
    execute(
        "INSERT INTO shift_records (shift_no, operator_id, start_time) VALUES (%s, %s, %s)",
        (shift_no, user['id'], datetime.now())
    )

    return json_response(None, True, '交接完成，新班次已开始')


@app.route('/wristband-tracking')
@require_login
def wristband_tracking_page():
    user = get_session_user()
    areas = query('SELECT * FROM bath_areas WHERE is_active = TRUE ORDER BY id')
    return template('templates/wristband_tracking.html', user=user, areas_json=to_template_json(areas))


@app.route('/warnings')
@require_login
def warnings_page():
    user = get_session_user()
    return template('templates/warnings.html', user=user)


@app.route('/api/warnings/stats', method='GET')
@require_login
def api_warnings_stats():
    run_all_warning_checks()
    stats = get_unread_warning_stats()
    return json_response(stats)


@app.route('/api/warnings', method='GET')
@require_login
def api_warnings_list():
    warning_type = request.query.get('type', '')
    level = request.query.get('level', '')
    is_read = request.query.get('is_read', '')
    is_resolved = request.query.get('is_resolved', '')
    limit = request.query.get('limit', '100')

    sql = '''
        SELECT w.*, u1.full_name as read_by_name, u2.full_name as resolved_by_name,
               wr.wristband_no, ba.name as bath_area_name
        FROM warnings w
        LEFT JOIN users u1 ON w.read_by = u1.id
        LEFT JOIN users u2 ON w.resolved_by = u2.id
        LEFT JOIN wristbands wr ON w.wristband_id = wr.id
        LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id
        WHERE 1=1
    '''
    params = []
    if warning_type:
        sql += " AND w.warning_type = %s"
        params.append(warning_type)
    if level:
        sql += " AND w.warning_level = %s"
        params.append(level)
    if is_read:
        sql += " AND w.is_read = %s"
        params.append(is_read == 'true')
    if is_resolved:
        sql += " AND w.is_resolved = %s"
        params.append(is_resolved == 'true')
    sql += " ORDER BY w.created_at DESC LIMIT %s"
    try:
        params.append(int(limit))
    except ValueError:
        params.append(100)
    rows = query(sql, params)
    return json_response([dict(r) for r in rows])


@app.route('/api/warnings/refresh', method='POST')
@require_login
def api_warnings_refresh():
    run_all_warning_checks()
    return json_response({'status': 'ok'}, True, '预警检测完成')


@app.route('/api/warnings/<warning_id:int>/read', method='POST')
@require_login
def api_warning_mark_read(warning_id):
    user = get_session_user()
    execute('''
        UPDATE warnings SET is_read = TRUE, read_by = %s, read_time = %s
        WHERE id = %s AND is_read = FALSE
    ''', (user['id'], datetime.now(), warning_id))
    return json_response(None, True, '已标记为已读')


@app.route('/api/warnings/read-all', method='POST')
@require_login
def api_warning_read_all():
    user = get_session_user()
    execute('''
        UPDATE warnings SET is_read = TRUE, read_by = %s, read_time = %s
        WHERE is_read = FALSE
    ''', (user['id'], datetime.now()))
    return json_response(None, True, '已全部标记为已读')


@app.route('/api/warnings/<warning_id:int>/resolve', method='POST')
@require_login
def api_warning_resolve(warning_id):
    user = get_session_user()
    data = request.json or {}
    execute('''
        UPDATE warnings SET is_resolved = TRUE, resolved_by = %s,
               resolved_time = %s, resolve_note = %s
        WHERE id = %s AND is_resolved = FALSE
    ''', (user['id'], datetime.now(), data.get('resolve_note', ''), warning_id))
    return json_response(None, True, '已标记为已解决')


@app.route('/api/warnings/<warning_id:int>', method='DELETE')
@require_login
def api_warning_delete(warning_id):
    execute("DELETE FROM warnings WHERE id = %s", (warning_id,))
    return json_response(None, True, '删除成功')


@app.route('/api/wristbands/<band_id:int>/status-log', method='GET')
@require_login
def api_wristband_status_log(band_id):
    rows = query('''
        SELECT l.*, u.full_name as operator_name, w.wristband_no
        FROM wristband_status_logs l
        LEFT JOIN users u ON l.operator_id = u.id
        LEFT JOIN wristbands w ON l.wristband_id = w.id
        WHERE l.wristband_id = %s
        ORDER BY l.change_time DESC
    ''', (band_id,))
    band = query_one("SELECT * FROM wristbands WHERE id = %s", (band_id,))
    return json_response({
        'wristband': dict(band) if band else None,
        'logs': [dict(r) for r in rows]
    })


@app.route('/api/issue-records/<record_id:int>/status-log', method='GET')
@require_login
def api_issue_record_status_log(record_id):
    rows = query('''
        SELECT l.*, u.full_name as operator_name, w.wristband_no
        FROM wristband_status_logs l
        LEFT JOIN users u ON l.operator_id = u.id
        LEFT JOIN wristbands w ON l.wristband_id = w.id
        WHERE l.issue_record_id = %s
        ORDER BY l.change_time ASC
    ''', (record_id,))
    return json_response([dict(r) for r in rows])


@app.route('/api/warnings/types', method='GET')
@require_login
def api_warning_types():
    types = [
        {'type': 'long_unreturned', 'name': '长时间未退', 'default_level': 'high',
         'description': '手牌发放超过12小时未退回'},
        {'type': 'frequent_loss', 'name': '频繁遗失', 'default_level': 'high',
         'description': '同一手机号30天内遗失2次以上'},
        {'type': 'continuous_reissue', 'name': '连续补办', 'default_level': 'medium',
         'description': '同一浴区24小时内补办3次以上'},
        {'type': 'frozen_misuse', 'name': '冻结误操作', 'default_level': 'high',
         'description': '被冻结的手牌被尝试进行操作'},
    ]
    return json_response(types)


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=8080, debug=True, reloader=True)
