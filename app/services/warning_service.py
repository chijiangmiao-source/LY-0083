from datetime import datetime, timedelta
from app.database import query, query_one, execute
from app.repositories import (
    WarningRepository,
    WristbandRepository,
    UserRepository,
)


WARNING_TYPES = [
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
    {'type': 'cross_store_discount_anomaly', 'name': '跨店优惠异常', 'default_level': 'high',
     'description': '会员短期内频繁跨店消费或跨店抵扣金额异常偏高'},
]


def create_warning(warning_type, title, content, **kwargs):
    warning_level = kwargs.get('warning_level', 'normal')
    wristband_id = kwargs.get('wristband_id')
    issue_record_id = kwargs.get('issue_record_id')
    bath_area_id = kwargs.get('bath_area_id')
    phone = kwargs.get('phone')
    related_data = kwargs.get('related_data')

    WarningRepository.create(
        warning_type=warning_type,
        title=title,
        content=content,
        warning_level=warning_level,
        wristband_id=wristband_id,
        issue_record_id=issue_record_id,
        bath_area_id=bath_area_id,
        phone=phone,
        related_data=related_data,
    )


def check_long_unreturned():
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
    band = WristbandRepository.get_by_id(wristband_id)
    if band and band['current_status'] == 'frozen':
        user = UserRepository.get_by_id_with_store(operator_id)
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


def check_abnormal_discount():
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


def check_balance_anomaly():
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


def check_cross_store_discount_anomaly():
    days_threshold = 7
    since = datetime.now() - timedelta(days=days_threshold)

    records = query('''
        SELECT csr.member_id, m.name as member_name, m.phone, m.level_id,
               ml.name as level_name, COUNT(*) as cross_count,
               SUM(csr.deduction_amount) as total_deduction
        FROM cross_store_records csr
        LEFT JOIN members m ON csr.member_id = m.id
        LEFT JOIN member_levels ml ON m.level_id = ml.id
        WHERE csr.created_at >= %s
        GROUP BY csr.member_id, m.name, m.phone, m.level_id, ml.name
        HAVING COUNT(*) >= 5 OR SUM(csr.deduction_amount) >= 3000
    ''', (since,))

    for r in records:
        r = dict(r)
        existing = query_one('''
            SELECT id FROM warnings
            WHERE warning_type = 'cross_store_discount_anomaly' AND phone = %s AND is_resolved = FALSE
              AND created_at >= %s
        ''', (r['phone'], since))
        if not existing:
            create_warning(
                warning_type='cross_store_discount_anomaly',
                warning_level='high',
                title=f'会员[{r["member_name"]}]跨店优惠异常',
                content=f'会员 {r["member_name"]}({r["phone"]}) 等级:{r["level_name"]}, '
                        f'在{days_threshold}天内跨店消费{r["cross_count"]}次, '
                        f'跨店抵扣总额: {float(r["total_deduction"]):.2f}元, 请核查是否存在异常',
                phone=r['phone'],
                related_data={
                    'member_id': r['member_id'],
                    'cross_count': int(r['cross_count']),
                    'total_deduction': float(r['total_deduction']),
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
    try:
        check_cross_store_discount_anomaly()
    except Exception:
        pass


def get_unread_warning_stats():
    return WarningRepository.get_unread_stats()


def get_warnings_by_issue_record_ids(record_ids):
    return WarningRepository.get_by_issue_record_ids(record_ids)


def list_warnings(warning_type='', level='', is_read='', is_resolved='', limit=100):
    return WarningRepository.list(
        warning_type=warning_type,
        level=level,
        is_read=is_read,
        is_resolved=is_resolved,
        limit=limit,
    )


def mark_read(warning_id, user_id):
    read_time = datetime.now()
    WarningRepository.mark_read(warning_id, user_id, read_time)


def mark_all_read(user_id):
    read_time = datetime.now()
    WarningRepository.mark_all_read(user_id, read_time)


def resolve_warning(warning_id, user_id, resolve_note=''):
    resolved_time = datetime.now()
    WarningRepository.mark_resolved(warning_id, user_id, resolved_time, resolve_note)


def delete_warning(warning_id):
    WarningRepository.delete(warning_id)


def get_warning_types():
    return WARNING_TYPES
