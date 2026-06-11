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
    stats = {
        'available_bands': query_one("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'available'")['cnt'],
        'issued_bands': query_one("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'issued'")['cnt'],
        'frozen_bands': query_one("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'frozen'")['cnt'],
        'unsettled': query_one("SELECT COUNT(*) as cnt FROM issue_records WHERE fee_status = 'unsettled' AND return_time IS NULL")['cnt'],
        'pending_review': query_one("SELECT COUNT(*) as cnt FROM reissue_applications WHERE review_status = 'pending'")['cnt'],
    }
    return template('templates/index.html', user=user, stats=stats)


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
    exists = query_one("SELECT id FROM wristbands WHERE wristband_no = %s", (data['wristband_no'],))
    if exists:
        return json_response(None, False, '手牌编号已存在')
    try:
        execute(
            "INSERT INTO wristbands (wristband_no, bath_area_id, current_status) VALUES (%s, %s, 'available')",
            (data['wristband_no'], data.get('bath_area_id'))
        )
        return json_response(None, True, '创建成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/wristbands/<band_id:int>', method='PUT')
@require_login
def api_update_wristband(band_id):
    data = request.json
    try:
        execute(
            "UPDATE wristbands SET bath_area_id=%s WHERE id=%s",
            (data.get('bath_area_id'), band_id)
        )
        return json_response(None, True, '更新成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/wristbands/<band_id:int>', method='DELETE')
@require_login
def api_delete_wristband(band_id):
    band = query_one("SELECT * FROM wristbands WHERE id = %s", (band_id,))
    if band and band['current_status'] == 'issued':
        return json_response(None, False, '手牌已发放，无法删除')
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
    records = query('''
        SELECT ir.*, ra.review_status 
        FROM issue_records ir 
        LEFT JOIN reissue_applications ra ON ra.issue_record_id = ir.id 
        WHERE ir.phone = %s AND (
            (ir.lost_status = 'lost' AND (ra.review_status IS NULL OR ra.review_status != 'approved'))
            OR (ir.lost_status = 'lost' AND ir.fee_status != 'settled')
        )
    ''', (phone,))
    has_unsettled = any(r for r in records if r['fee_status'] != 'settled' and r['lost_status'] == 'lost')
    return json_response({'can_issue': not has_unsettled, 'records': [dict(r) for r in records]})


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

    check = query('''
        SELECT ir.* FROM issue_records ir 
        LEFT JOIN reissue_applications ra ON ra.issue_record_id = ir.id 
        WHERE ir.phone = %s AND ir.lost_status = 'lost' AND ir.fee_status != 'settled'
    ''', (phone,))
    if check:
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
        return json_response(None, False, '该手牌已冻结，无法退回流转')

    return_time = datetime.now()
    if return_time < record['issue_time']:
        return json_response(None, False, '退牌时间不能早于发牌时间')

    extra_fee = float(data.get('extra_fee', 0) or 0)
    loss_fee = float(data.get('loss_fee', 0) or 0)
    reissue_fee = float(data.get('reissue_fee', 0) or 0)
    deposit_status = data.get('deposit_status', 'returned')

    total_fee = (record['base_fee'] or 0) + extra_fee + loss_fee + reissue_fee

    execute('''
        UPDATE issue_records SET return_time=%s, extra_fee=%s, loss_fee=%s, reissue_fee=%s, fee_status='settled'
        WHERE id=%s
    ''', (return_time, extra_fee, loss_fee, reissue_fee, record_id))

    if band and band['current_status'] != 'frozen':
        execute(
            "UPDATE wristbands SET current_status = 'available', deposit_status = %s WHERE id = %s",
            (deposit_status, band['id'])
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

    execute(
        "UPDATE issue_records SET lost_status = 'lost' WHERE id = %s",
        (record_id,)
    )

    if record['wristband_id']:
        execute(
            "UPDATE wristbands SET current_status = 'frozen' WHERE id = %s",
            (record['wristband_id'],)
        )

    execute('''
        INSERT INTO reissue_applications 
        (issue_record_id, report_time, reported_by, loss_description)
        VALUES (%s, %s, %s, %s)
    ''', (record_id, datetime.now(), user['full_name'], data.get('loss_description', '')))

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

    if decision == 'reject':
        execute('''
            UPDATE reissue_applications SET review_status='rejected', review_time=%s, reviewer_id=%s, review_comment=%s
            WHERE id=%s
        ''', (datetime.now(), user['id'], data.get('review_comment', ''), app_id))
        return json_response(None, True, '审核驳回成功')

    record = query_one("SELECT * FROM issue_records WHERE id = %s", (app['issue_record_id'],))

    execute('''
        UPDATE reissue_applications 
        SET review_status='approved', review_time=%s, reviewer_id=%s, review_comment=%s,
            is_responsible=%s, new_wristband_id=%s
        WHERE id=%s
    ''', (datetime.now(), user['id'], data.get('review_comment', ''), is_responsible, new_wristband_id, app_id))

    execute('''
        UPDATE issue_records SET loss_fee=%s, reissue_fee=%s WHERE id=%s
    ''', (loss_fee, reissue_fee, app['issue_record_id']))

    if new_wristband_id:
        new_band = query_one("SELECT * FROM wristbands WHERE id = %s", (new_wristband_id,))
        if new_band and new_band['current_status'] == 'available':
            execute(
                "UPDATE wristbands SET current_status = 'issued', last_issued_at = %s WHERE id = %s",
                (datetime.now(), new_wristband_id)
            )
            execute(
                "UPDATE issue_records SET wristband_id = %s WHERE id = %s",
                (new_wristband_id, app['issue_record_id'])
            )

    shift = get_active_shift(user['id'])
    if shift:
        execute("UPDATE shift_records SET reissue_count = reissue_count + 1 WHERE id = %s", (shift['id'],))

    return json_response(None, True, '审核通过成功')


@app.route('/shift-summary')
@require_login
def shift_summary_page():
    user = get_session_user()
    shift = get_active_shift(user['id'])
    if not shift:
        return template('templates/shift_summary.html', user=user, shift_json='null', records_json='[]', summary_json='null')

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

    return template('templates/shift_summary.html', user=user, shift_json=to_template_json(shift), records_json=to_template_json(records), summary_json=to_template_json(summary_data))


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


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=8080, debug=True, reloader=True)
