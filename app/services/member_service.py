from datetime import datetime, timedelta, date

from app.repositories import (
    MemberRepository,
    MemberLevelRepository,
    MemberPackageRepository,
    MemberPackagePurchaseRepository,
    MemberPackageUsageRepository,
    MemberTransactionRepository,
    MemberPromotionRepository,
    TopupBonusRepository,
    MemberUpgradeLogRepository,
    WarningRepository,
    StoreRepository,
    ShiftRecordRepository,
    UserRepository,
    IssueRecordRepository,
)


def get_member_stats(date_str=None):
    if not date_str:
        date_str = date.today().strftime('%Y-%m-%d')

    try:
        total_members = MemberRepository.count_by_status('active')
        today_new_members = MemberRepository.count_by_date(date_str)
        today_consume_count = MemberTransactionRepository.count_by_type_and_date(
            ['consumption', 'package_deduction'], date_str)
        today_top_up = MemberTransactionRepository.sum_by_type_and_date('topup', date_str)
        today_package_verify = MemberPackageUsageRepository.count_by_date(date_str)
        today_balance_deduction = MemberTransactionRepository.sum_by_type_and_date('consumption', date_str)
        today_package_deduction = MemberTransactionRepository.sum_by_type_and_date('package_deduction', date_str)
        today_gift_bonus = MemberTransactionRepository.sum_by_type_and_date('gift_bonus', date_str)
        today_member_issue_count = IssueRecordRepository.count_by_date_and_member(date_str)

        return {
            'total_members': total_members,
            'today_new_members': today_new_members,
            'today_consume_count': today_consume_count,
            'today_top_up': today_top_up,
            'today_package_verify': today_package_verify,
            'today_balance_deduction': today_balance_deduction,
            'today_package_deduction': today_package_deduction,
            'today_gift_bonus': today_gift_bonus,
            'today_member_issue_count': today_member_issue_count,
            'date': date_str,
        }
    except Exception as e:
        raise ValueError(f'获取会员统计数据失败: {str(e)}')


def generate_member_no():
    now = datetime.now()
    prefix = 'M' + now.strftime('%Y%m%d')
    from app.database import query_one
    count = query_one("SELECT COUNT(*) as cnt FROM members WHERE member_no LIKE %s", (prefix + '%',))
    return f"{prefix}{(count['cnt'] + 1):04d}"


def get_current_store_id(user):
    if not user:
        return None
    u = UserRepository.get_by_id(user['id'])
    return u['store_id'] if u and u.get('store_id') else None


def is_cross_store_member(member, current_store_id):
    if not member or not current_store_id:
        return False
    home_store_id = member.get('home_store_id')
    return home_store_id is not None and home_store_id != current_store_id


def get_member_by_phone(phone):
    return MemberRepository.get_by_phone(phone)


def create_member(data, operator_id):
    phone = data.get('phone', '').strip()
    if not phone:
        raise ValueError('手机号不能为空')

    from app.database import query_one
    existing = query_one("SELECT id FROM members WHERE phone = %s", (phone,))
    if existing:
        raise ValueError('该手机号已注册会员')

    member_no = generate_member_no()
    level_id = data.get('level_id', 1)
    home_store_id = data.get('home_store_id')
    balance_cross_store = data.get('balance_cross_store_enabled', False)

    MemberRepository.create(
        member_no=member_no,
        name=data.get('name', ''),
        phone=phone,
        gender=data.get('gender', ''),
        id_card=data.get('id_card', ''),
        level_id=level_id,
        remark=data.get('remark', ''),
        home_store_id=home_store_id,
        balance_cross_store_enabled=balance_cross_store,
    )

    from app.database import query_one
    member = query_one("SELECT * FROM members WHERE member_no = %s", (member_no,))

    MemberTransactionRepository.create(
        member_id=member['id'],
        transaction_type='register',
        amount=0,
        balance_after=0,
        operator_id=operator_id,
        remark=f'会员注册 {member_no}',
    )

    shift = ShiftRecordRepository.get_active_shift(operator_id)
    if shift:
        ShiftRecordRepository.increment_member_new_count(shift['id'])

    return dict(member)


def update_member(member_id, data):
    from app.database import query_one
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        raise ValueError('会员不存在')

    new_phone = data.get('phone', '').strip()
    if new_phone and new_phone != member['phone']:
        existing = query_one("SELECT id FROM members WHERE phone = %s AND id != %s", (new_phone, member_id))
        if existing:
            raise ValueError('该手机号已被其他会员使用')

    update_data = {
        'name': data.get('name', ''),
        'phone': new_phone or member['phone'],
        'gender': data.get('gender', ''),
        'id_card': data.get('id_card', ''),
        'level_id': data.get('level_id', member['level_id']),
        'remark': data.get('remark', ''),
        'home_store_id': data.get('home_store_id', member.get('home_store_id')),
        'balance_cross_store_enabled': data.get('balance_cross_store_enabled', member.get('balance_cross_store_enabled', False)),
    }

    MemberRepository.update(member_id, **update_data)

    if data.get('status') and data.get('status') != member['status']:
        MemberRepository.update(member_id, status=data['status'])

    return True


def get_bonus_for_topup(level_id, amount):
    return TopupBonusRepository.get_bonus_for_topup(level_id, amount)


def try_auto_upgrade_member(member_id, operator_id):
    from app.database import query_one
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        return False

    current_level = MemberLevelRepository.get_by_id(member['level_id'])
    if not current_level:
        return False

    levels = MemberLevelRepository.get_for_upgrade(member['level_id'], member['total_top_up'])
    new_level_id = None
    for lv in levels:
        if float(member['total_top_up']) >= float(lv['min_top_up']) and float(lv['min_top_up']) > float(current_level['min_top_up']):
            new_level_id = lv['id']
            break

    if not new_level_id:
        return False

    MemberUpgradeLogRepository.create(
        member_id=member_id,
        old_level_id=member['level_id'],
        new_level_id=new_level_id,
        trigger_type='auto_topup',
        operator_id=operator_id,
        remark=f'累计充值{float(member["total_top_up"]):.2f}元达到升级门槛，自动升级',
    )

    from app.database import execute
    execute("UPDATE members SET level_id = %s, auto_upgraded_at = %s WHERE id = %s",
            (new_level_id, datetime.now(), member_id))

    new_level = MemberLevelRepository.get_by_id(new_level_id)
    WarningRepository.create(
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
            'total_top_up': float(member['total_top_up']),
        },
    )

    return True


def manual_upgrade_member(member_id, new_level_id, operator_id, remark=''):
    from app.database import query_one, execute
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        raise ValueError('会员不存在')

    old_level = MemberLevelRepository.get_by_id(member['level_id'])
    new_level = MemberLevelRepository.get_by_id(new_level_id)
    if not new_level:
        raise ValueError('目标等级不存在')

    MemberUpgradeLogRepository.create(
        member_id=member_id,
        old_level_id=member['level_id'],
        new_level_id=new_level_id,
        trigger_type='manual',
        operator_id=operator_id,
        remark=remark or f'手动调整等级从 {old_level["name"] if old_level else "原等级"} 到 {new_level["name"]}',
    )

    execute("UPDATE members SET level_id = %s WHERE id = %s", (new_level_id, member_id))

    WarningRepository.create(
        warning_type='member_upgrade',
        warning_level='normal',
        title=f'会员[{member["name"]}]等级手动调整',
        content=f'会员 {member["name"]}({member["phone"]}) 等级从 {old_level["name"] if old_level else "原等级"} '
                f'手动调整为 {new_level["name"]}, 操作员备注: {remark}',
        phone=member['phone'],
        related_data={
            'member_id': member_id,
            'old_level_id': member['level_id'],
            'new_level_id': new_level_id,
            'operator_id': operator_id,
            'remark': remark,
        },
    )

    return True


def member_topup(member_id, amount, operator_id, gift_amount=0):
    from app.database import query_one
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        raise ValueError('会员不存在')

    amount = float(amount)
    if amount <= 0:
        raise ValueError('充值金额必须大于0')

    bonus_amount, bonus_rule = get_bonus_for_topup(member['level_id'], amount)
    gift_amount = float(gift_amount or 0)
    total_bonus = bonus_amount + gift_amount

    new_balance = float(member['balance']) + amount
    new_gift = float(member.get('gift_balance', 0) or 0) + total_bonus

    MemberRepository.update_balance(
        member_id=member_id,
        balance=new_balance,
        gift_balance=new_gift,
        total_top_up=amount,
        total_gift=total_bonus,
    )

    MemberTransactionRepository.create(
        member_id=member_id,
        transaction_type='topup',
        amount=amount,
        balance_after=new_balance,
        operator_id=operator_id,
        remark=f'储值充值 {amount}元',
    )

    if total_bonus > 0:
        bonus_remark = f'充值赠送 {total_bonus}元'
        if bonus_rule:
            bonus_remark += f' (规则:{bonus_rule["name"]})'
        if gift_amount > 0:
            bonus_remark += f' 含手动赠送{gift_amount}元'
        MemberTransactionRepository.create(
            member_id=member_id,
            transaction_type='gift_bonus',
            amount=total_bonus,
            balance_after=new_balance,
            operator_id=operator_id,
            remark=bonus_remark,
        )

    upgraded = try_auto_upgrade_member(member_id, operator_id)

    shift = ShiftRecordRepository.get_active_shift(operator_id)
    if shift:
        ShiftRecordRepository.add_member_top_up_total(shift['id'], amount)

    result = {
        'new_balance': new_balance,
        'new_gift_balance': new_gift,
        'bonus': total_bonus,
    }
    if upgraded:
        result['upgraded'] = True
        member_with_level = MemberRepository.get_by_id_with_level(member_id)
        result['new_level_name'] = member_with_level.get('level_name') if member_with_level else None

    return result


def get_member_available_packages(member_id, bath_area_id=None):
    return MemberPackagePurchaseRepository.get_available_packages(member_id, bath_area_id)


def get_active_promotions(level_id, promotion_type=None):
    if not level_id:
        raise ValueError('会员等级ID不能为空')
    try:
        return MemberPromotionRepository.get_active(
            level_id=int(level_id),
            promotion_type=promotion_type
        )
    except Exception as e:
        raise ValueError(f'获取促销活动失败: {str(e)}')


def lookup_member_detail(phone, bath_area_id=None, current_store_id=None):
    if not phone:
        raise ValueError('手机号不能为空')

    try:
        member = get_member_by_phone(phone)
        if not member:
            raise ValueError('会员不存在')

        member = dict(member)

        area_id = int(bath_area_id) if bath_area_id else None
        packages = get_member_available_packages(member['id'], area_id)
        member['available_packages'] = packages

        promotions = get_active_promotions(member.get('level_id', 1))
        member['active_promotions'] = promotions

        total_available = float(member.get('balance', 0) or 0) + float(member.get('gift_balance', 0) or 0)
        member['total_available'] = total_available
        member['total_balance'] = float(member.get('balance', 0) or 0)
        member['gift_balance'] = float(member.get('gift_balance', 0) or 0)

        bonus_rules = TopupBonusRepository.list_all()
        level_id = member.get('level_id', 1)
        applicable_bonus_rules = []
        for rule in bonus_rules:
            applicable_ids = rule.get('applicable_level_ids') or []
            if not applicable_ids or level_id in applicable_ids:
                applicable_bonus_rules.append({
                    'id': rule['id'],
                    'name': rule['name'],
                    'min_amount': float(rule['min_amount']),
                    'bonus_amount': float(rule.get('bonus_amount', 0) or 0),
                    'bonus_percent': float(rule.get('bonus_percent', 0) or 0),
                    'description': rule.get('description', ''),
                })
        member['bonus_preview'] = applicable_bonus_rules
        member['has_bonus'] = len(applicable_bonus_rules) > 0

        home_store = None
        if member.get('home_store_id'):
            home_store = StoreRepository.get_by_id(member['home_store_id'])
            if home_store:
                member['home_store'] = {
                    'id': home_store['id'],
                    'name': home_store.get('name'),
                    'store_code': home_store.get('store_code'),
                }
            else:
                member['home_store'] = None
        else:
            member['home_store'] = None

        member['is_cross_store'] = is_cross_store_member(member, current_store_id)
        member['balance_cross_store_enabled'] = member.get('balance_cross_store_enabled', False)

        next_level = MemberRepository.get_next_level(member.get('total_top_up', 0))
        if next_level:
            total_top_up = float(member.get('total_top_up', 0) or 0)
            member['next_level'] = {
                'id': next_level['id'],
                'name': next_level['name'],
                'min_top_up': float(next_level['min_top_up']),
                'current_total': total_top_up,
                'gap': round(float(next_level['min_top_up']) - total_top_up, 2),
                'progress_percent': round((total_top_up / float(next_level['min_top_up'])) * 100, 2) if float(next_level['min_top_up']) > 0 else 0,
            }
        else:
            member['next_level'] = None

        member['level'] = {
            'id': member.get('level_id'),
            'name': member.get('level_name'),
            'discount_rate': float(member.get('discount_rate', 100) or 100),
        }

        return member
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f'查询会员详情失败: {str(e)}')


def purchase_package(member_id, package_id, pay_method, operator_id):
    from app.database import query_one
    member = query_one("SELECT * FROM members WHERE id = %s", (member_id,))
    if not member:
        raise ValueError('会员不存在')

    pkg = MemberPackageRepository.get_active_by_id(package_id)
    if not pkg:
        raise ValueError('套餐不存在或已下架')

    purchase_price = float(pkg['price'])

    if pay_method == 'balance':
        if float(member['balance']) < purchase_price:
            raise ValueError('会员余额不足')
        new_balance = float(member['balance']) - purchase_price
        MemberRepository.update(member_id, balance=new_balance)
        from app.database import execute
        execute(
            "UPDATE members SET total_consumption = total_consumption + %s, last_active_at = %s WHERE id = %s",
            (purchase_price, datetime.now(), member_id)
        )
        MemberTransactionRepository.create(
            member_id=member_id,
            transaction_type='package_purchase',
            amount=purchase_price,
            balance_after=new_balance,
            operator_id=operator_id,
            remark=f'余额购买套餐[{pkg["name"]}] {purchase_price}元',
        )
    else:
        new_balance = float(member['balance'])
        MemberTransactionRepository.create(
            member_id=member_id,
            transaction_type='package_purchase_cash',
            amount=purchase_price,
            balance_after=new_balance,
            operator_id=operator_id,
            remark=f'现金购买套餐[{pkg["name"]}] {purchase_price}元',
        )

    expire_at = None
    if pkg['valid_days']:
        expire_at = datetime.now() + timedelta(days=pkg['valid_days'])

    remaining_count = pkg['total_count'] if pkg['package_type'] in ('count', 'combo') else None

    from db import execute_and_return_id
    purchase_id = execute_and_return_id('''
        INSERT INTO member_package_purchases (member_id, package_id, purchase_price, remaining_count, total_count, expire_at)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    ''', (member_id, package_id, purchase_price, remaining_count, pkg['total_count'], expire_at))

    purchase_id_res = MemberPackagePurchaseRepository.get_latest_by_member_and_package(member_id, package_id)

    MemberTransactionRepository.create(
        member_id=member_id,
        transaction_type='package_activate',
        amount=0,
        balance_after=new_balance,
        operator_id=operator_id,
        remark=f'激活套餐[{pkg["name"]}]',
        package_purchase_id=purchase_id_res['id'] if purchase_id_res else None,
    )

    shift = ShiftRecordRepository.get_active_shift(operator_id)
    if shift:
        ShiftRecordRepository.increment_member_package_purchase_count(shift['id'])

    return True


def list_members(keyword='', level_id='', status=''):
    return MemberRepository.list(keyword=keyword, level_id=level_id, status=status)


def get_member_transactions(member_id, limit=50):
    return MemberTransactionRepository.get_by_member(member_id, limit=limit)


def get_member_packages(member_id):
    return MemberPackagePurchaseRepository.get_by_member(member_id)


def get_member_upgrade_logs(member_id):
    return MemberUpgradeLogRepository.get_by_member(member_id)
