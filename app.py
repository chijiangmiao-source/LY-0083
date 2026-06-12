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


def get_bonus_for_topup(level_id, amount):
    rules = query('''
        SELECT * FROM member_topup_bonus_rules
        WHERE is_active = TRUE AND min_amount <= %s
        ORDER BY priority DESC, min_amount DESC
    ''', (amount,))
    best_rule = None
    for r in rules:
        r = dict(r)
        applicable_ids = r.get('applicable_level_ids') or []
        if not applicable_ids or level_id in applicable_ids:
            best_rule = r
            break
    if not best_rule:
        return 0.0, None
    bonus = float(best_rule['bonus_amount'] or 0)
    if best_rule['bonus_percent'] and float(best_rule['bonus_percent']) > 0:
        bonus += round(amount * float(best_rule['bonus_percent']) / 100.0, 2)
    return bonus, best_rule


def try_auto_upgrade_member(member_id, operator_id):
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        return False
    current_level = query_one("SELECT * FROM member_levels WHERE id = %s", (member['level_id'],))
    if not current_level:
        return False
    levels = query("SELECT * FROM member_levels WHERE is_active = TRUE AND id != %s ORDER BY min_top_up DESC", (member['level_id'],))
    new_level_id = None
    for lv in levels:
        lv = dict(lv)
        if float(member['total_top_up']) >= float(lv['min_top_up']) and float(lv['min_top_up']) > float(current_level['min_top_up']):
            new_level_id = lv['id']
            break
    if not new_level_id:
        return False
    execute('''
        INSERT INTO member_level_upgrade_logs (member_id, old_level_id, new_level_id, trigger_type, operator_id, remark)
        VALUES (%s, %s, %s, 'auto_topup', %s, %s)
    ''', (member_id, member['level_id'], new_level_id, operator_id,
          f'累计充值{float(member["total_top_up"]):.2f}元达到升级门槛，自动升级'))
    execute("UPDATE members SET level_id = %s, auto_upgraded_at = %s WHERE id = %s",
            (new_level_id, datetime.now(), member_id))
    new_level = query_one("SELECT * FROM member_levels WHERE id = %s", (new_level_id,))
    create_warning(
        warning_type='member_upgrade',
        warning_level='normal',
        title=f'会员[{member["name"]}]自动升级为{new_level["name"] if new_level else "新等级"}',
        content=f'会员 {member["name"]}({member["phone"]}) 累计充值 {float(member["total_top_up"]):.2f}元, '
                f'已自动从 {current_level["name"]} 升级为 {new_level["name"] if new_level else "新等级"}',
        phone=member['phone'],
        related_data={
            'member_id': member_id,
            'old_level_id': member['level_id'],
            'new_level_id': new_level_id,
            'total_top_up': float(member['total_top_up'])
        }
    )
    return True


def check_balance_anomaly():
    from datetime import timedelta
    hours_threshold = 24
    topup_threshold = 5000.00
    consume_threshold = 3000.00
    since = datetime.now() - timedelta(hours=hours_threshold)
    topups = query('''
        SELECT member_id, SUM(amount) as total_topup, COUNT(*) as topup_count
        FROM member_transactions
        WHERE transaction_type = 'topup' AND created_at >= %s
        GROUP BY member_id
        HAVING SUM(amount) >= %s OR COUNT(*) >= 5
    ''', (since, topup_threshold))
    for t in topups:
        t = dict(t)
        member = query_one("SELECT name, phone FROM members WHERE id = %s", (t['member_id'],))
        if not member:
            continue
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'balance_anomaly' AND phone = %s AND is_resolved = FALSE
              AND created_at >= %s
        ''', (member['phone'], since))
        if not existing:
            create_warning(
                warning_type='balance_anomaly',
                warning_level='medium',
                title=f'会员[{member["name"]}]储值异常',
                content=f'会员 {member["name"]}({member["phone"]}) 在{hours_threshold}小时内'
                        f'充值{t["topup_count"]}次共{float(t["total_topup"]):.2f}元, 请核查',
                phone=member['phone'],
                related_data={
                    'member_id': t['member_id'],
                    'total_topup': float(t['total_topup']),
                    'topup_count': t['topup_count'],
                    'hours': hours_threshold
                }
            )
    consumes = query('''
        SELECT member_id, SUM(amount) as total_consume, COUNT(*) as consume_count
        FROM member_transactions
        WHERE transaction_type IN ('consumption', 'package_deduction') AND created_at >= %s
        GROUP BY member_id
        HAVING SUM(amount) >= %s OR COUNT(*) >= 10
    ''', (since, consume_threshold))
    for c in consumes:
        c = dict(c)
        member = query_one("SELECT name, phone FROM members WHERE id = %s", (c['member_id'],))
        if not member:
            continue
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'balance_anomaly' AND phone = %s AND is_resolved = FALSE
              AND created_at >= %s AND related_data::text LIKE %s
        ''', (member['phone'], since, f'%consume%'))
        if not existing:
            create_warning(
                warning_type='balance_anomaly',
                warning_level='medium',
                title=f'会员[{member["name"]}]消费异常',
                content=f'会员 {member["name"]}({member["phone"]}) 在{hours_threshold}小时内'
                        f'消费{c["consume_count"]}次共{float(c["total_consume"]):.2f}元, 请核查',
                phone=member['phone'],
                related_data={
                    'member_id': c['member_id'],
                    'total_consume': float(c['total_consume']),
                    'consume_count': c['consume_count'],
                    'hours': hours_threshold,
                    'type': 'consume'
                }
            )


def check_topup_anomaly():
    from datetime import timedelta
    days_threshold = 7
    since = datetime.now() - timedelta(days=days_threshold)
    records = query('''
        SELECT mt.member_id, m.name as member_name, m.phone, m.level_id, ml.name as level_name,
               COUNT(*) as topup_count, SUM(mt.amount) as total_topup
        FROM member_transactions mt
        LEFT JOIN members m ON mt.member_id = m.id
        LEFT JOIN member_levels ml ON m.level_id = ml.id
        WHERE mt.transaction_type = 'topup' AND mt.created_at >= %s
          AND m.status = 'active'
        GROUP BY mt.member_id, m.name, m.phone, m.level_id, ml.name
        HAVING COUNT(*) >= 10 OR SUM(mt.amount) >= 20000
    ''', (since,))
    for r in records:
        r = dict(r)
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'topup_anomaly' AND phone = %s AND is_resolved = FALSE
              AND created_at >= %s
        ''', (r['phone'], since))
        if not existing:
            create_warning(
                warning_type='topup_anomaly',
                warning_level='high',
                title=f'会员[{r["member_name"]}]充值频次异常',
                content=f'会员 {r["member_name"]}({r["phone"]}) 等级:{r["level_name"]}, '
                        f'在{days_threshold}天内充值{r["topup_count"]}次共{float(r["total_topup"]):.2f}元, 请核查',
                phone=r['phone'],
                related_data={
                    'member_id': r['member_id'],
                    'topup_count': r['topup_count'],
                    'total_topup': float(r['total_topup']),
                    'days': days_threshold
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
    try:
        check_abnormal_discount()
    except Exception:
        pass
    try:
        check_balance_anomaly()
    except Exception:
        pass
    try:
        check_topup_anomaly()
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
    def safe_sum(sql, *params):
        try:
            r = query_one(sql, params)
            return float(r['total']) if r and r['total'] else 0.0
        except Exception:
            return 0.0
    stats = {
        'available_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'available'"),
        'issued_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'issued'"),
        'frozen_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'frozen'"),
        'unsettled': safe_count("SELECT COUNT(*) as cnt FROM issue_records WHERE fee_status = 'unsettled' AND return_time IS NULL"),
        'pending_review': safe_count("SELECT COUNT(*) as cnt FROM reissue_applications WHERE review_status = 'pending'"),
    }
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')
    member_stats = {
        'total_members': safe_count("SELECT COUNT(*) as cnt FROM members WHERE status = 'active'"),
        'today_new_members': safe_count(
            "SELECT COUNT(*) as cnt FROM members WHERE DATE(registered_at) = %s", today_str),
        'today_consume_count': safe_count(
            "SELECT COUNT(*) as cnt FROM member_transactions WHERE transaction_type IN ('consumption','package_deduction') AND DATE(created_at) = %s", today_str),
        'today_top_up': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'topup' AND DATE(created_at) = %s", today_str),
        'today_package_verify': safe_count(
            "SELECT COUNT(*) as cnt FROM member_package_usages WHERE DATE(used_at) = %s", today_str),
        'today_balance_deduction': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'consumption' AND DATE(created_at) = %s", today_str),
        'today_package_deduction': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'package_deduction' AND DATE(created_at) = %s", today_str),
        'today_gift_bonus': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'gift_bonus' AND DATE(created_at) = %s", today_str),
        'today_member_issue_count': safe_count(
            "SELECT COUNT(*) as cnt FROM issue_records WHERE member_id IS NOT NULL AND DATE(issue_time) = %s", today_str),
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
        member_stats=member_stats,
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

    member_id = None
    member_discount_rate = 100.00
    member_deposit_rate = 100.00
    actual_deposit = area['deposit_amount'] if area else 0
    base_fee = area['base_price'] if area else 0

    member = get_member_by_phone(phone)
    if member:
        member_id = member['id']
        member_discount_rate = float(member['discount_rate'])
        member_deposit_rate = float(member['deposit_discount_rate'])
        actual_deposit = round(float(area['deposit_amount']) * member_deposit_rate / 100.0, 2) if area else 0
        base_fee = round(float(area['base_price']) * member_discount_rate / 100.0, 2) if area else 0

    execute('''
        INSERT INTO issue_records 
        (serial_no, customer_name, phone, wristband_id, bath_area_id, issue_time, 
         base_fee, deposit_amount, operator_id, fee_status, lost_status,
         member_id, actual_deposit, member_discount_rate, member_deposit_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'unsettled', 'normal',
                %s, %s, %s, %s)
    ''', (
        serial_no, data.get('customer_name', ''), phone, wristband_id,
        band['bath_area_id'], issue_time,
        base_fee, area['deposit_amount'] if area else 0,
        user['id'],
        member_id, actual_deposit, member_discount_rate, member_deposit_rate
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
        change_time=issue_time,
        remark=f'会员: {"是" if member_id else "否"}, 实收押金: {actual_deposit}元, 折扣率: {member_discount_rate}%'
    )

    shift = get_active_shift(user['id'])
    if shift:
        execute("UPDATE shift_records SET issue_count = issue_count + 1 WHERE id = %s", (shift['id'],))
        if member_id:
            execute("UPDATE shift_records SET member_issue_count = member_issue_count + 1 WHERE id = %s", (shift['id'],))

    record = query_one("SELECT * FROM issue_records WHERE serial_no = %s", (serial_no,))
    result = dict(record) if record else {}
    if member:
        result['member_info'] = {
            'member_no': member['member_no'],
            'level_name': member['level_name'],
            'balance': float(member['balance']),
            'discount_rate': member_discount_rate,
            'deposit_rate': member_deposit_rate,
            'actual_deposit': actual_deposit,
            'discounted_base_fee': base_fee
        }
    return json_response(result, True, '发牌成功')


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

    package_deduction = 0.0
    balance_deduction = 0.0
    use_package_id = data.get('use_package_id')
    use_balance = data.get('use_balance', False)

    if record.get('member_id'):
        member = query_one("SELECT * FROM members WHERE id = %s", (record['member_id'],))
        if member:
            if use_package_id:
                pkg_purchase = query_one("SELECT * FROM member_package_purchases WHERE id = %s", (use_package_id,))
                if pkg_purchase:
                    deduction_amount = min(total_fee, float(record['base_fee'] or 0))
                    if use_package_for_consumption(use_package_id, record['member_id'], record_id, deduction_amount, user['id']):
                        package_deduction = deduction_amount
                        total_fee = max(0, total_fee - package_deduction)

            if use_balance and total_fee > 0:
                balance_available = float(member['balance'])
                balance_deduction = min(total_fee, balance_available)
                if balance_deduction > 0:
                    if deduct_member_balance(record['member_id'], balance_deduction, record_id, user['id'], f'退牌结算余额抵扣 {balance_deduction}元'):
                        total_fee = max(0, total_fee - balance_deduction)

            shift = get_active_shift(user['id'])
            if shift:
                updates = []
                params = []
                if package_deduction > 0:
                    updates.append("member_package_deduction = member_package_deduction + %s")
                    params.append(package_deduction)
                    updates.append("member_package_verify_count = member_package_verify_count + 1")
                if balance_deduction > 0:
                    updates.append("member_balance_deduction = member_balance_deduction + %s")
                    params.append(balance_deduction)
                updates.append("member_consume_count = member_consume_count + 1")
                if updates:
                    params.append(shift['id'])
                    execute("UPDATE shift_records SET " + ", ".join(updates) + " WHERE id = %s", params)

    old_band_status = band['current_status'] if band else None

    execute('''
        UPDATE issue_records SET return_time=%s, extra_fee=%s, loss_fee=%s, reissue_fee=%s, fee_status='settled',
               package_deduction=%s, balance_deduction=%s
        WHERE id=%s
    ''', (return_time, extra_fee, loss_fee, reissue_fee, package_deduction, balance_deduction, record_id))

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
            remark=f'总费用: {total_fee}元, 套餐抵扣: {package_deduction}元, 余额抵扣: {balance_deduction}元, 押金状态: {deposit_status}',
            change_time=return_time
        )

    shift = get_active_shift(user['id'])
    if shift:
        execute(
            "UPDATE shift_records SET total_income = total_income + %s WHERE id = %s",
            (total_fee, shift['id'])
        )

    return json_response({
        'total_fee': total_fee,
        'package_deduction': package_deduction,
        'balance_deduction': balance_deduction,
        'cash_to_pay': total_fee
    }, True, '退牌结算成功')


@app.route('/report-loss')
@require_login
def report_loss_page():
    user = get_session_user()
    return template('templates/report_loss.html', user=user)


@app.route('/api/loss/search', method='GET')
@require_login
def api_loss_search():
    keyword = request.query.get('keyword', '').strip()
    sql = '''SELECT ir.*, w.wristband_no, ba.name as bath_area_name,
                    m.name as member_name, m.member_no, m.balance as member_balance,
                    ml.name as level_name, ml.discount_rate, ml.loss_fee_discount_rate, ml.reissue_fee_discount_rate
             FROM issue_records ir 
             LEFT JOIN wristbands w ON ir.wristband_id = w.id
             LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
             LEFT JOIN members m ON ir.member_id = m.id
             LEFT JOIN member_levels ml ON m.level_id = ml.id
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
               ir.member_id, ir.actual_deposit, ir.member_discount_rate, ir.member_deposit_rate,
               w.wristband_no as old_wristband_no, ba.name as bath_area_name,
               m.name as member_name, m.member_no, m.balance as member_balance,
               ml.name as level_name, ml.discount_rate as level_discount_rate,
               ml.loss_fee_discount_rate, ml.reissue_fee_discount_rate, m.level_id as member_level_id
        FROM reissue_applications ra
        LEFT JOIN issue_records ir ON ra.issue_record_id = ir.id
        LEFT JOIN wristbands w ON ir.wristband_id = w.id
        LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
        LEFT JOIN members m ON ir.member_id = m.id
        LEFT JOIN member_levels ml ON m.level_id = ml.id
        ORDER BY ra.report_time DESC
    ''')
    result = []
    for r in records:
        r = dict(r)
        if r.get('member_level_id'):
            loss_promos = get_active_promotions(r['member_level_id'], 'loss_fee')
            reissue_promos = get_active_promotions(r['member_level_id'], 'reissue_fee')
            r['loss_promotions'] = loss_promos
            r['reissue_promotions'] = reissue_promos
            if loss_promos:
                best_loss = min(float(p['discount_rate']) for p in loss_promos)
                r['effective_loss_fee_discount_rate'] = min(float(r.get('loss_fee_discount_rate', 100) or 100), best_loss)
            else:
                r['effective_loss_fee_discount_rate'] = float(r.get('loss_fee_discount_rate', 100) or 100)
            if reissue_promos:
                best_reissue = min(float(p['discount_rate']) for p in reissue_promos)
                r['effective_reissue_fee_discount_rate'] = min(float(r.get('reissue_fee_discount_rate', 100) or 100), best_reissue)
            else:
                r['effective_reissue_fee_discount_rate'] = float(r.get('reissue_fee_discount_rate', 100) or 100)
        result.append(r)
    return json_response(result)


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

    if record and record.get('member_id'):
        member = query_one("SELECT * FROM members WHERE id = %s", (record['member_id'],))
        if member:
            level = query_one("SELECT * FROM member_levels WHERE id = %s", (member['level_id'],))
            if level:
                loss_rate = float(level['loss_fee_discount_rate'])
                reissue_rate = float(level['reissue_fee_discount_rate'])
                loss_promos = get_active_promotions(member['level_id'], 'loss_fee')
                reissue_promos = get_active_promotions(member['level_id'], 'reissue_fee')
                if loss_promos:
                    best_loss = min(float(p['discount_rate']) for p in loss_promos)
                    loss_rate = min(loss_rate, best_loss)
                if reissue_promos:
                    best_reissue = min(float(p['discount_rate']) for p in reissue_promos)
                    reissue_rate = min(reissue_rate, best_reissue)
                if not data.get('skip_auto_discount'):
                    loss_fee = round(float(data.get('loss_fee_original', loss_fee) or loss_fee) * loss_rate / 100.0, 2)
                    reissue_fee = round(float(data.get('reissue_fee_original', reissue_fee) or reissue_fee) * reissue_rate / 100.0, 2)

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
               CASE WHEN ra.id IS NOT NULL THEN TRUE ELSE FALSE END as has_reissue,
               m.name as member_name, m.member_no, ml.name as level_name
        FROM issue_records ir
        LEFT JOIN wristbands w ON ir.wristband_id = w.id
        LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
        LEFT JOIN reissue_applications ra ON ra.issue_record_id = ir.id
        LEFT JOIN members m ON ir.member_id = m.id
        LEFT JOIN member_levels ml ON m.level_id = ml.id
        WHERE ir.operator_id = %s AND ir.issue_time >= %s
        ORDER BY ir.issue_time DESC
    ''', (user['id'], shift['start_time']))

    unsettled = [r for r in records if r['fee_status'] != 'settled']
    reissues = [r for r in records if r.get('has_reissue')]
    member_records = [r for r in records if r.get('member_id')]

    summary_data = {
        'issue_count': len(records),
        'reissue_count': len(reissues),
        'unsettled_count': len(unsettled),
        'total_income': sum(float(r['base_fee'] or 0) + float(r['extra_fee'] or 0) + float(r['loss_fee'] or 0) + float(r['reissue_fee'] or 0) for r in records if r['fee_status'] == 'settled'),
        'member_consume_count': int(shift.get('member_consume_count', 0) or 0),
        'member_top_up_total': float(shift.get('member_top_up_total', 0) or 0),
        'member_package_verify_count': int(shift.get('member_package_verify_count', 0) or 0),
        'member_balance_deduction': float(shift.get('member_balance_deduction', 0) or 0),
        'member_package_deduction': float(shift.get('member_package_deduction', 0) or 0),
        'member_issue_count': int(shift.get('member_issue_count', 0) or 0),
        'member_package_purchase_count': int(shift.get('member_package_purchase_count', 0) or 0),
        'member_gift_balance_used': float(shift.get('member_gift_balance_used', 0) or 0),
        'member_new_count': int(shift.get('member_new_count', 0) or 0),
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


def generate_member_no():
    now = datetime.now()
    prefix = 'M' + now.strftime('%Y%m%d')
    count = query_one("SELECT COUNT(*) as cnt FROM members WHERE member_no LIKE %s", (prefix + '%',))
    return f"{prefix}{(count['cnt'] + 1):04d}"


def get_member_by_phone(phone):
    if not phone:
        return None
    member = query_one('''
        SELECT m.*, ml.name as level_name, ml.discount_rate, ml.deposit_discount_rate,
               ml.loss_fee_discount_rate, ml.reissue_fee_discount_rate,
               COALESCE(m.gift_balance, 0) as gift_balance
        FROM members m
        LEFT JOIN member_levels ml ON m.level_id = ml.id
        WHERE m.phone = %s AND m.status = 'active'
    ''', (phone,))
    return dict(member) if member else None


def get_active_promotions(level_id, promotion_type=None):
    now = datetime.now()
    sql = '''
        SELECT * FROM member_promotions
        WHERE is_active = TRUE AND start_time <= %s AND end_time >= %s
    '''
    params = [now, now]
    if promotion_type:
        sql += " AND promotion_type = %s"
        params.append(promotion_type)
    rows = query(sql, params)
    result = []
    for p in rows:
        p = dict(p)
        applicable_ids = p.get('applicable_level_ids') or []
        if not applicable_ids or level_id in applicable_ids:
            result.append(p)
    return result


def get_member_available_packages(member_id, bath_area_id=None):
    now = datetime.now()
    sql = '''
        SELECT mpp.*, mp.name as package_name, mp.package_type, mp.original_value
        FROM member_package_purchases mpp
        LEFT JOIN member_packages mp ON mpp.package_id = mp.id
        WHERE mpp.member_id = %s AND mpp.status = 'active'
          AND (mpp.expire_at IS NULL OR mpp.expire_at > %s)
          AND (mpp.remaining_count IS NULL OR mpp.remaining_count > 0)
        ORDER BY mpp.activated_at DESC
    '''
    purchases = query(sql, (member_id, now))
    result = []
    for p in purchases:
        if bath_area_id and p.get('applicable_bath_area_ids'):
            if bath_area_id not in (p['applicable_bath_area_ids'] or []):
                continue
        result.append(dict(p))
    return result


def use_package_for_consumption(purchase_id, member_id, issue_record_id, deduction_amount, operator_id):
    purchase = query_one("SELECT * FROM member_package_purchases WHERE id = %s", (purchase_id,))
    if not purchase:
        return False
    if purchase['remaining_count'] is not None and purchase['remaining_count'] <= 0:
        return False

    execute('''
        INSERT INTO member_package_usages (purchase_id, member_id, issue_record_id, deduction_amount)
        VALUES (%s, %s, %s, %s)
    ''', (purchase_id, member_id, issue_record_id, deduction_amount))

    if purchase['remaining_count'] is not None:
        execute(
            "UPDATE member_package_purchases SET remaining_count = remaining_count - 1 WHERE id = %s",
            (purchase_id,)
        )
        updated = query_one("SELECT remaining_count FROM member_package_purchases WHERE id = %s", (purchase_id,))
        if updated and updated['remaining_count'] <= 0:
            execute("UPDATE member_package_purchases SET status = 'used_up' WHERE id = %s", (purchase_id,))

    execute(
        "UPDATE members SET total_package_deduction = total_package_deduction + %s, last_active_at = %s WHERE id = %s",
        (deduction_amount, datetime.now(), member_id)
    )

    execute('''
        INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, issue_record_id, operator_id, remark)
        VALUES (%s, 'package_deduction', %s, %s, %s, %s, %s)
    ''', (member_id, deduction_amount, query_one("SELECT balance FROM members WHERE id = %s", (member_id,))['balance'],
          issue_record_id, operator_id, f'套餐核销扣减 {deduction_amount}元'))

    return True


def deduct_member_balance(member_id, amount, issue_record_id, operator_id, remark=''):
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        return False
    regular_balance = float(member['balance'])
    gift_balance = float(member.get('gift_balance', 0) or 0)
    total_available = regular_balance + gift_balance
    if total_available < float(amount):
        return False

    deduct_amount = float(amount)
    gift_used = 0.0
    regular_used = 0.0

    if gift_balance > 0:
        gift_used = min(deduct_amount, gift_balance)
        deduct_amount -= gift_used
    if deduct_amount > 0:
        regular_used = deduct_amount

    new_regular = regular_balance - regular_used
    new_gift = gift_balance - gift_used
    execute(
        "UPDATE members SET balance = %s, gift_balance = %s, total_consumption = total_consumption + %s, last_active_at = %s WHERE id = %s",
        (new_regular, new_gift, amount, datetime.now(), member_id)
    )

    execute('''
        INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, issue_record_id, operator_id, remark)
        VALUES (%s, 'consumption', %s, %s, %s, %s, %s)
    ''', (member_id, amount, new_regular, issue_record_id, operator_id,
          remark or f'消费扣减 {amount}元' + (f' (含赠送余额{gift_used}元)' if gift_used > 0 else '')))

    shift = get_active_shift(operator_id)
    if shift and gift_used > 0:
        execute("UPDATE shift_records SET member_gift_balance_used = member_gift_balance_used + %s WHERE id = %s",
                (gift_used, shift['id']))

    return True


def check_abnormal_discount():
    from datetime import timedelta
    days_threshold = 7
    discount_threshold = 50.00
    since = datetime.now() - timedelta(days=days_threshold)

    records = query('''
        SELECT ir.member_id, m.name as member_name, m.phone, m.level_id, ml.name as level_name,
               ml.discount_rate, COUNT(*) as discount_count,
               SUM(ir.base_fee * (1 - ir.member_discount_rate / 100.0)) as total_discount_amount
        FROM issue_records ir
        LEFT JOIN members m ON ir.member_id = m.id
        LEFT JOIN member_levels ml ON m.level_id = ml.id
        WHERE ir.member_id IS NOT NULL AND ir.member_discount_rate < %s
          AND ir.issue_time >= %s
        GROUP BY ir.member_id, m.name, m.phone, m.level_id, ml.name, ml.discount_rate
        HAVING SUM(ir.base_fee * (1 - ir.member_discount_rate / 100.0)) > 500
           OR COUNT(*) >= 10
    ''', (discount_threshold, since))

    for r in records:
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'abnormal_discount' AND phone = %s AND is_resolved = FALSE
              AND created_at >= %s
        ''', (r['phone'], since))
        if not existing:
            create_warning(
                warning_type='abnormal_discount',
                warning_level='medium',
                title=f'会员[{r["member_name"]}]优惠折扣异常',
                content=f'会员 {r["member_name"]}({r["phone"]}) 等级:{r["level_name"]}, '
                        f'在{days_threshold}天内享受折扣消费{r["discount_count"]}次, '
                        f'累计优惠金额: {float(r["total_discount_amount"]):.2f}元, '
                        f'折扣率: {r["discount_rate"]}%, 请核查是否存在异常',
                phone=r['phone'],
                related_data={
                    'member_id': r['member_id'],
                    'discount_count': r['discount_count'],
                    'total_discount_amount': float(r['total_discount_amount']),
                    'discount_rate': float(r['discount_rate']),
                    'days': days_threshold
                }
            )


@app.route('/members')
@require_login
def members_page():
    user = get_session_user()
    levels = query('SELECT * FROM member_levels WHERE is_active = TRUE ORDER BY id')
    packages = query('SELECT * FROM member_packages WHERE is_active = TRUE ORDER BY id')
    areas = query('SELECT * FROM bath_areas WHERE is_active = TRUE ORDER BY id')
    bonus_rules = query('SELECT * FROM member_topup_bonus_rules ORDER BY priority DESC, min_amount ASC')
    return template('templates/members.html', user=user,
                    levels_json=to_template_json(levels),
                    packages_json=to_template_json(packages),
                    areas_json=to_template_json(areas),
                    bonus_rules_json=to_template_json(bonus_rules))


@app.route('/api/members', method='GET')
@require_login
def api_members_list():
    keyword = request.query.get('keyword', '').strip()
    level_id = request.query.get('level_id', '')
    status = request.query.get('status', '')
    sql = '''
        SELECT m.*, ml.name as level_name, ml.discount_rate
        FROM members m
        LEFT JOIN member_levels ml ON m.level_id = ml.id
        WHERE 1=1
    '''
    params = []
    if keyword:
        sql += " AND (m.name LIKE %s OR m.phone LIKE %s OR m.member_no LIKE %s)"
        like = f'%{keyword}%'
        params.extend([like, like, like])
    if level_id:
        sql += " AND m.level_id = %s"
        params.append(int(level_id))
    if status:
        sql += " AND m.status = %s"
        params.append(status)
    sql += ' ORDER BY m.id DESC'
    rows = query(sql, params)
    return json_response([dict(r) for r in rows])


@app.route('/api/members', method='POST')
@require_login
def api_create_member():
    data = request.json
    user = get_session_user()
    phone = data.get('phone', '').strip()
    if not phone:
        return json_response(None, False, '手机号不能为空')

    existing = query_one("SELECT id FROM members WHERE phone = %s", (phone,))
    if existing:
        return json_response(None, False, '该手机号已注册会员')

    member_no = generate_member_no()
    level_id = data.get('level_id', 1)

    execute('''
        INSERT INTO members (member_no, name, phone, gender, id_card, level_id, remark)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (member_no, data.get('name', ''), phone, data.get('gender', ''),
          data.get('id_card', ''), level_id, data.get('remark', '')))

    member = query_one("SELECT * FROM members WHERE member_no = %s", (member_no,))

    execute('''
        INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, operator_id, remark)
        VALUES (%s, 'register', 0, 0, %s, %s)
    ''', (member['id'], user['id'], f'会员注册 {member_no}'))

    shift = get_active_shift(user['id'])
    if shift:
        execute("UPDATE shift_records SET member_new_count = member_new_count + 1 WHERE id = %s", (shift['id'],))

    return json_response(dict(member), True, '会员注册成功')


@app.route('/api/members/<member_id:int>', method='PUT')
@require_login
def api_update_member(member_id):
    data = request.json
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        return json_response(None, False, '会员不存在')

    new_phone = data.get('phone', '').strip()
    if new_phone and new_phone != member['phone']:
        existing = query_one("SELECT id FROM members WHERE phone = %s AND id != %s", (new_phone, member_id))
        if existing:
            return json_response(None, False, '该手机号已被其他会员使用')

    execute('''
        UPDATE members SET name=%s, phone=%s, gender=%s, id_card=%s, level_id=%s, remark=%s
        WHERE id=%s
    ''', (data.get('name', ''), new_phone or member['phone'],
          data.get('gender', ''), data.get('id_card', ''),
          data.get('level_id', member['level_id']),
          data.get('remark', ''), member_id))

    if data.get('status') and data.get('status') != member['status']:
        execute("UPDATE members SET status = %s WHERE id = %s", (data['status'], member_id))

    return json_response(None, True, '会员信息更新成功')


@app.route('/api/members/<member_id:int>/topup', method='POST')
@require_login
def api_member_topup(member_id):
    data = request.json
    user = get_session_user()
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        return json_response(None, False, '会员不存在')

    amount = float(data.get('amount', 0))
    if amount <= 0:
        return json_response(None, False, '充值金额必须大于0')

    bonus_amount, bonus_rule = get_bonus_for_topup(member['level_id'], amount)
    gift_amount = float(data.get('gift_amount', 0) or 0)
    total_bonus = bonus_amount + gift_amount

    new_balance = float(member['balance']) + amount
    new_gift = float(member.get('gift_balance', 0) or 0) + total_bonus
    execute(
        "UPDATE members SET balance = %s, gift_balance = %s, total_top_up = total_top_up + %s, total_gift = total_gift + %s, last_active_at = %s WHERE id = %s",
        (new_balance, new_gift, amount, total_bonus, datetime.now(), member_id)
    )

    execute('''
        INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, operator_id, remark)
        VALUES (%s, 'topup', %s, %s, %s, %s)
    ''', (member_id, amount, new_balance, user['id'],
          data.get('remark', '') or f'储值充值 {amount}元'))

    if total_bonus > 0:
        bonus_remark = f'充值赠送 {total_bonus}元'
        if bonus_rule:
            bonus_remark += f' (规则:{bonus_rule["name"]})'
        if gift_amount > 0:
            bonus_remark += f' 含手动赠送{gift_amount}元'
        execute('''
            INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, operator_id, remark)
            VALUES (%s, 'gift_bonus', %s, %s, %s, %s)
        ''', (member_id, total_bonus, new_balance, user['id'], bonus_remark))

    upgraded = try_auto_upgrade_member(member_id, user['id'])

    shift = get_active_shift(user['id'])
    if shift:
        execute(
            "UPDATE shift_records SET member_top_up_total = member_top_up_total + %s WHERE id = %s",
            (amount, shift['id'])
        )

    result = {'new_balance': new_balance, 'new_gift_balance': new_gift, 'bonus': total_bonus}
    if upgraded:
        result['upgraded'] = True
        new_member = query_one("SELECT m.*, ml.name as level_name FROM members m LEFT JOIN member_levels ml ON m.level_id = ml.id WHERE m.id = %s", (member_id,))
        result['new_level_name'] = new_member['level_name'] if new_member else None

    msg = f'充值成功，余额: {new_balance:.2f}元'
    if total_bonus > 0:
        msg += f'，赠送: {total_bonus:.2f}元'
    if upgraded:
        msg += f'，已自动升级等级'

    return json_response(result, True, msg)


@app.route('/api/members/<member_id:int>/transactions', method='GET')
@require_login
def api_member_transactions(member_id):
    limit = request.query.get('limit', '50')
    rows = query('''
        SELECT mt.*, u.full_name as operator_name
        FROM member_transactions mt
        LEFT JOIN users u ON mt.operator_id = u.id
        WHERE mt.member_id = %s
        ORDER BY mt.created_at DESC LIMIT %s
    ''', (member_id, int(limit)))
    return json_response([dict(r) for r in rows])


@app.route('/api/members/<member_id:int>/packages', method='GET')
@require_login
def api_member_packages(member_id):
    rows = query('''
        SELECT mpp.*, mp.name as package_name, mp.package_type, mp.original_value
        FROM member_package_purchases mpp
        LEFT JOIN member_packages mp ON mpp.package_id = mp.id
        WHERE mpp.member_id = %s
        ORDER BY mpp.created_at DESC
    ''', (member_id,))
    return json_response([dict(r) for r in rows])


@app.route('/api/members/<member_id:int>/purchase-package', method='POST')
@require_login
def api_member_purchase_package(member_id):
    data = request.json
    user = get_session_user()
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        return json_response(None, False, '会员不存在')

    package_id = data.get('package_id')
    pkg = query_one("SELECT * FROM member_packages WHERE id = %s AND is_active = TRUE", (package_id,))
    if not pkg:
        return json_response(None, False, '套餐不存在或已下架')

    pay_method = data.get('pay_method', 'cash')
    purchase_price = float(pkg['price'])

    if pay_method == 'balance':
        if float(member['balance']) < purchase_price:
            return json_response(None, False, '会员余额不足')
        new_balance = float(member['balance']) - purchase_price
        execute(
            "UPDATE members SET balance = %s, total_consumption = total_consumption + %s, last_active_at = %s WHERE id = %s",
            (new_balance, purchase_price, datetime.now(), member_id)
        )
        execute('''
            INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, operator_id, remark)
            VALUES (%s, 'package_purchase', %s, %s, %s, %s)
        ''', (member_id, purchase_price, new_balance, user['id'],
              f'余额购买套餐[{pkg["name"]}] {purchase_price}元'))
    else:
        new_balance = float(member['balance'])
        execute('''
            INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, operator_id, remark)
            VALUES (%s, 'package_purchase_cash', %s, %s, %s, %s)
        ''', (member_id, purchase_price, new_balance, user['id'],
              f'现金购买套餐[{pkg["name"]}] {purchase_price}元'))

    from datetime import timedelta
    expire_at = None
    if pkg['valid_days']:
        expire_at = datetime.now() + timedelta(days=pkg['valid_days'])

    remaining_count = pkg['total_count'] if pkg['package_type'] in ('count', 'combo') else None

    execute_and_return_id('''
        INSERT INTO member_package_purchases (member_id, package_id, purchase_price, remaining_count, total_count, expire_at)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    ''', (member_id, package_id, purchase_price, remaining_count, pkg['total_count'], expire_at))

    purchase_id_res = query_one('''
        SELECT id FROM member_package_purchases
        WHERE member_id = %s AND package_id = %s
        ORDER BY created_at DESC LIMIT 1
    ''', (member_id, package_id))

    execute('''
        INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after, package_purchase_id, operator_id, remark)
        VALUES (%s, 'package_activate', 0, %s, %s, %s, %s)
    ''', (member_id, new_balance, purchase_id_res['id'] if purchase_id_res else None,
          user['id'], f'激活套餐[{pkg["name"]}]'))

    shift = get_active_shift(user['id'])
    if shift:
        execute("UPDATE shift_records SET member_package_purchase_count = member_package_purchase_count + 1 WHERE id = %s",
                (shift['id'],))

    return json_response(None, True, f'套餐[{pkg["name"]}]购买成功')


@app.route('/api/members/lookup', method='GET')
@require_login
def api_member_lookup():
    phone = request.query.get('phone', '').strip()
    member = get_member_by_phone(phone)
    if not member:
        return json_response(None, True, '非会员')
    bath_area_id = request.query.get('bath_area_id', '')
    area_id = int(bath_area_id) if bath_area_id else None
    packages = get_member_available_packages(member['id'], area_id)
    member['available_packages'] = packages
    promotions = get_active_promotions(member.get('level_id', 1))
    member['active_promotions'] = promotions
    member['total_available'] = float(member.get('balance', 0) or 0) + float(member.get('gift_balance', 0) or 0)
    bonus_preview = get_bonus_for_topup(member.get('level_id', 1), 0)[0]
    member['bonus_available'] = bonus_preview > 0
    next_level = query_one('''
        SELECT * FROM member_levels WHERE is_active = TRUE AND min_top_up > %s
        ORDER BY min_top_up ASC LIMIT 1
    ''', (float(member.get('total_top_up', 0) or 0),))
    if next_level:
        member['next_level'] = {
            'name': next_level['name'],
            'min_top_up': float(next_level['min_top_up']),
            'gap': round(float(next_level['min_top_up']) - float(member.get('total_top_up', 0) or 0), 2)
        }
    else:
        member['next_level'] = None
    return json_response(member)


@app.route('/api/member-levels', method='GET')
@require_login
def api_member_levels():
    rows = query('SELECT * FROM member_levels WHERE is_active = TRUE ORDER BY id')
    return json_response([dict(r) for r in rows])


@app.route('/api/member-levels', method='POST')
@require_login
def api_create_member_level():
    data = request.json
    try:
        execute('''
            INSERT INTO member_levels (name, discount_rate, deposit_discount_rate, loss_fee_discount_rate, reissue_fee_discount_rate, min_top_up, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (data['name'], float(data['discount_rate']), float(data['deposit_discount_rate']),
              float(data['loss_fee_discount_rate']), float(data['reissue_fee_discount_rate']),
              float(data.get('min_top_up', 0)), data.get('description', '')))
        return json_response(None, True, '等级创建成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/member-levels/<level_id:int>', method='PUT')
@require_login
def api_update_member_level(level_id):
    data = request.json
    try:
        execute('''
            UPDATE member_levels SET name=%s, discount_rate=%s, deposit_discount_rate=%s,
                   loss_fee_discount_rate=%s, reissue_fee_discount_rate=%s, min_top_up=%s, description=%s
            WHERE id=%s
        ''', (data['name'], float(data['discount_rate']), float(data['deposit_discount_rate']),
              float(data['loss_fee_discount_rate']), float(data['reissue_fee_discount_rate']),
              float(data.get('min_top_up', 0)), data.get('description', ''), level_id))
        return json_response(None, True, '等级更新成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/member-packages', method='GET')
@require_login
def api_member_packages_list():
    rows = query('SELECT * FROM member_packages ORDER BY id DESC')
    return json_response([dict(r) for r in rows])


@app.route('/api/member-packages', method='POST')
@require_login
def api_create_member_package():
    data = request.json
    try:
        area_ids = data.get('applicable_bath_area_ids', [])
        if isinstance(area_ids, str):
            area_ids = [int(x) for x in area_ids.split(',') if x.strip()]
        execute('''
            INSERT INTO member_packages (name, package_type, total_count, valid_days, price, original_value, applicable_bath_area_ids, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (data['name'], data['package_type'],
              data.get('total_count'), data.get('valid_days'),
              float(data['price']), float(data['original_value']),
              area_ids, data.get('description', '')))
        return json_response(None, True, '套餐创建成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/member-packages/<pkg_id:int>', method='PUT')
@require_login
def api_update_member_package(pkg_id):
    data = request.json
    try:
        area_ids = data.get('applicable_bath_area_ids', [])
        if isinstance(area_ids, str):
            area_ids = [int(x) for x in area_ids.split(',') if x.strip()]
        execute('''
            UPDATE member_packages SET name=%s, package_type=%s, total_count=%s, valid_days=%s,
                   price=%s, original_value=%s, applicable_bath_area_ids=%s, description=%s, is_active=%s
            WHERE id=%s
        ''', (data['name'], data['package_type'],
              data.get('total_count'), data.get('valid_days'),
              float(data['price']), float(data['original_value']),
              area_ids, data.get('description', ''),
              data.get('is_active', True), pkg_id))
        return json_response(None, True, '套餐更新成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/member-stats', method='GET')
@require_login
def api_member_stats():
    def safe_count(sql, *params):
        try:
            r = query_one(sql, params)
            return int(r['cnt']) if r else 0
        except Exception:
            return 0

    def safe_sum(sql, *params):
        try:
            r = query_one(sql, params)
            return float(r['total']) if r and r['total'] else 0.0
        except Exception:
            return 0.0

    today = date.today()
    today_str = today.strftime('%Y-%m-%d')
    stats = {
        'total_members': safe_count("SELECT COUNT(*) as cnt FROM members WHERE status = 'active'"),
        'today_new_members': safe_count(
            "SELECT COUNT(*) as cnt FROM members WHERE DATE(registered_at) = %s", today_str),
        'today_consume_count': safe_count(
            "SELECT COUNT(*) as cnt FROM member_transactions WHERE transaction_type IN ('consumption','package_deduction') AND DATE(created_at) = %s", today_str),
        'today_top_up': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'topup' AND DATE(created_at) = %s", today_str),
        'today_package_verify': safe_count(
            "SELECT COUNT(*) as cnt FROM member_package_usages WHERE DATE(used_at) = %s", today_str),
        'today_balance_deduction': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'consumption' AND DATE(created_at) = %s", today_str),
        'today_package_deduction': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'package_deduction' AND DATE(created_at) = %s", today_str),
        'today_gift_bonus': safe_sum(
            "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'gift_bonus' AND DATE(created_at) = %s", today_str),
        'today_member_issue_count': safe_count(
            "SELECT COUNT(*) as cnt FROM issue_records WHERE member_id IS NOT NULL AND DATE(issue_time) = %s", today_str),
    }
    return json_response(stats)


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
        {'type': 'abnormal_discount', 'name': '异常优惠', 'default_level': 'medium',
         'description': '会员折扣优惠金额异常偏高'},
        {'type': 'balance_anomaly', 'name': '储值异常', 'default_level': 'medium',
         'description': '会员短时间内大额充值或消费异常'},
        {'type': 'topup_anomaly', 'name': '充值频次异常', 'default_level': 'high',
         'description': '会员短期内频繁大额充值'},
        {'type': 'member_upgrade', 'name': '会员升级', 'default_level': 'normal',
         'description': '会员自动升级等级通知'},
    ]
    return json_response(types)


@app.route('/api/promotions', method='GET')
@require_login
def api_promotions_list():
    rows = query('SELECT * FROM member_promotions ORDER BY id DESC')
    return json_response([dict(r) for r in rows])


@app.route('/api/promotions/active', method='GET')
@require_login
def api_promotions_active():
    level_id = request.query.get('level_id', '')
    promotion_type = request.query.get('type', '')
    now = datetime.now()
    sql = '''
        SELECT * FROM member_promotions
        WHERE is_active = TRUE AND start_time <= %s AND end_time >= %s
    '''
    params = [now, now]
    if promotion_type:
        sql += " AND promotion_type = %s"
        params.append(promotion_type)
    rows = query(sql, params)
    result = []
    for p in rows:
        p = dict(p)
        if level_id:
            applicable_ids = p.get('applicable_level_ids') or []
            if applicable_ids and int(level_id) not in applicable_ids:
                continue
        result.append(p)
    return json_response(result)


@app.route('/api/promotions', method='POST')
@require_login
def api_create_promotion():
    data = request.json
    try:
        level_ids = data.get('applicable_level_ids', [])
        if isinstance(level_ids, str):
            level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
        execute('''
            INSERT INTO member_promotions (name, promotion_type, discount_rate, applicable_level_ids, start_time, end_time, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (data['name'], data['promotion_type'],
              float(data.get('discount_rate', 100)),
              level_ids,
              data.get('start_time'), data.get('end_time'),
              data.get('description', '')))
        return json_response(None, True, '活动创建成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/promotions/<promo_id:int>', method='PUT')
@require_login
def api_update_promotion(promo_id):
    data = request.json
    try:
        level_ids = data.get('applicable_level_ids', [])
        if isinstance(level_ids, str):
            level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
        execute('''
            UPDATE member_promotions SET name=%s, promotion_type=%s, discount_rate=%s,
                   applicable_level_ids=%s, start_time=%s, end_time=%s, description=%s, is_active=%s
            WHERE id=%s
        ''', (data['name'], data['promotion_type'],
              float(data.get('discount_rate', 100)),
              level_ids,
              data.get('start_time'), data.get('end_time'),
              data.get('description', ''),
              data.get('is_active', True), promo_id))
        return json_response(None, True, '活动更新成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/promotions/<promo_id:int>', method='DELETE')
@require_login
def api_delete_promotion(promo_id):
    execute("DELETE FROM member_promotions WHERE id = %s", (promo_id,))
    return json_response(None, True, '活动删除成功')


@app.route('/api/topup-bonus-rules', method='GET')
@require_login
def api_topup_bonus_rules_list():
    rows = query('SELECT * FROM member_topup_bonus_rules ORDER BY priority DESC, min_amount ASC')
    return json_response([dict(r) for r in rows])


@app.route('/api/topup-bonus-rules', method='POST')
@require_login
def api_create_topup_bonus_rule():
    data = request.json
    try:
        level_ids = data.get('applicable_level_ids', [])
        if isinstance(level_ids, str):
            level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
        execute('''
            INSERT INTO member_topup_bonus_rules (name, min_amount, bonus_amount, bonus_percent, applicable_level_ids, priority, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (data['name'], float(data['min_amount']),
              float(data.get('bonus_amount', 0)), float(data.get('bonus_percent', 0)),
              level_ids, int(data.get('priority', 0)), data.get('description', '')))
        return json_response(None, True, '充值赠送规则创建成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/topup-bonus-rules/<rule_id:int>', method='PUT')
@require_login
def api_update_topup_bonus_rule(rule_id):
    data = request.json
    try:
        level_ids = data.get('applicable_level_ids', [])
        if isinstance(level_ids, str):
            level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
        execute('''
            UPDATE member_topup_bonus_rules SET name=%s, min_amount=%s, bonus_amount=%s, bonus_percent=%s,
                   applicable_level_ids=%s, priority=%s, description=%s, is_active=%s
            WHERE id=%s
        ''', (data['name'], float(data['min_amount']),
              float(data.get('bonus_amount', 0)), float(data.get('bonus_percent', 0)),
              level_ids, int(data.get('priority', 0)), data.get('description', ''),
              data.get('is_active', True), rule_id))
        return json_response(None, True, '充值赠送规则更新成功')
    except Exception as e:
        return json_response(None, False, str(e))


@app.route('/api/topup-bonus-rules/<rule_id:int>', method='DELETE')
@require_login
def api_delete_topup_bonus_rule(rule_id):
    execute("DELETE FROM member_topup_bonus_rules WHERE id = %s", (rule_id,))
    return json_response(None, True, '充值赠送规则删除成功')


@app.route('/api/topup-bonus-preview', method='GET')
@require_login
def api_topup_bonus_preview():
    level_id = request.query.get('level_id', '')
    amount = request.query.get('amount', '0')
    if not level_id or not amount:
        return json_response({'bonus': 0, 'rule': None})
    bonus, rule = get_bonus_for_topup(int(level_id), float(amount))
    return json_response({'bonus': bonus, 'rule': dict(rule) if rule else None})


@app.route('/api/members/<member_id:int>/upgrade-logs', method='GET')
@require_login
def api_member_upgrade_logs(member_id):
    rows = query('''
        SELECT mul.*, ml1.name as old_level_name, ml2.name as new_level_name, u.full_name as operator_name
        FROM member_level_upgrade_logs mul
        LEFT JOIN member_levels ml1 ON mul.old_level_id = ml1.id
        LEFT JOIN member_levels ml2 ON mul.new_level_id = ml2.id
        LEFT JOIN users u ON mul.operator_id = u.id
        WHERE mul.member_id = %s
        ORDER BY mul.created_at DESC
    ''', (member_id,))
    return json_response([dict(r) for r in rows])


@app.route('/api/members/<member_id:int>/manual-upgrade', method='POST')
@require_login
def api_member_manual_upgrade(member_id):
    data = request.json
    user = get_session_user()
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        return json_response(None, False, '会员不存在')
    new_level_id = data.get('new_level_id')
    if not new_level_id:
        return json_response(None, False, '请选择新等级')
    new_level = query_one("SELECT * FROM member_levels WHERE id = %s AND is_active = TRUE", (new_level_id,))
    if not new_level:
        return json_response(None, False, '目标等级不存在或已停用')
    if member['level_id'] == new_level_id:
        return json_response(None, False, '该会员已是该等级')
    execute('''
        INSERT INTO member_level_upgrade_logs (member_id, old_level_id, new_level_id, trigger_type, operator_id, remark)
        VALUES (%s, %s, %s, 'manual', %s, %s)
    ''', (member_id, member['level_id'], new_level_id, user['id'],
          data.get('remark', '') or f'手动调整为{new_level["name"]}'))
    execute("UPDATE members SET level_id = %s WHERE id = %s", (new_level_id, member_id))
    return json_response(None, True, f'会员等级已调整为{new_level["name"]}')


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=8080, debug=True, reloader=True)
