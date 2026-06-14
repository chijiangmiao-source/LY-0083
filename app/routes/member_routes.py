from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response, to_template_json
from app.services import (
    create_member,
    update_member,
    member_topup,
    get_member_available_packages,
    get_active_promotions,
    get_bonus_for_topup,
    lookup_member_detail,
    purchase_package,
    list_members,
    get_member_transactions,
    get_member_packages,
    get_member_upgrade_logs,
    get_current_store_id,
    manual_upgrade_member,
    is_cross_store_member,
    get_member_stats,
)
from app.repositories import (
    MemberLevelRepository,
    MemberPackageRepository,
    BathAreaRepository,
    MemberPromotionRepository,
    TopupBonusRepository,
    StoreRepository,
    MemberRepository,
    MemberTransactionRepository,
    MemberPackageUsageRepository,
    IssueRecordRepository,
)


def register_member_routes(app):

    @app.route('/members')
    @require_login
    def members_page():
        user = get_session_user()
        levels = MemberLevelRepository.list_active()
        packages = MemberPackageRepository.list_active()
        areas = BathAreaRepository.list_active()
        bonus_rules = TopupBonusRepository.list_all()
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
        rows = list_members(keyword=keyword, level_id=level_id, status=status)
        return json_response(rows)

    @app.route('/api/members', method='POST')
    @require_login
    def api_create_member():
        data = request.json
        user = get_session_user()
        try:
            member = create_member(data, user['id'])
            return json_response(member, True, '会员注册成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/members/<member_id:int>', method='PUT')
    @require_login
    def api_update_member(member_id):
        data = request.json
        try:
            update_member(member_id, data)
            return json_response(None, True, '会员信息更新成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/members/<member_id:int>/topup', method='POST')
    @require_login
    def api_member_topup(member_id):
        data = request.json
        user = get_session_user()
        try:
            result = member_topup(
                member_id,
                float(data.get('amount', 0)),
                user['id'],
                float(data.get('gift_amount', 0) or 0)
            )
            msg = f'充值成功，余额: {result["new_balance"]:.2f}元'
            if result.get('bonus', 0) > 0:
                msg += f'，赠送: {result["bonus"]:.2f}元'
            if result.get('upgraded'):
                msg += f'，已自动升级等级'
            return json_response(result, True, msg)
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/members/<member_id:int>/transactions', method='GET')
    @require_login
    def api_member_transactions(member_id):
        limit = request.query.get('limit', '50')
        rows = get_member_transactions(member_id, limit=int(limit))
        return json_response(rows)

    @app.route('/api/members/<member_id:int>/packages', method='GET')
    @require_login
    def api_member_packages(member_id):
        rows = get_member_packages(member_id)
        return json_response(rows)

    @app.route('/api/members/<member_id:int>/purchase-package', method='POST')
    @require_login
    def api_member_purchase_package(member_id):
        data = request.json
        user = get_session_user()
        try:
            pkg = MemberPackageRepository.get_active_by_id(data.get('package_id'))
            if not pkg:
                return json_response(None, False, '套餐不存在或已下架')
            purchase_package(member_id, data.get('package_id'), data.get('pay_method', 'cash'), user['id'])
            return json_response(None, True, f'套餐[{pkg["name"]}]购买成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/members/lookup', method='GET')
    @require_login
    def api_member_lookup():
        phone = request.query.get('phone', '').strip()
        bath_area_id = request.query.get('bath_area_id', '')
        current_store_id = get_current_store_id(get_session_user())
        try:
            member = lookup_member_detail(phone, bath_area_id=bath_area_id, current_store_id=current_store_id)
            return json_response(member)
        except ValueError as e:
            if '会员不存在' in str(e):
                return json_response(None, True, '非会员')
            return json_response(None, False, str(e))

    @app.route('/api/members/<member_id:int>/upgrade-logs', method='GET')
    @require_login
    def api_member_upgrade_logs(member_id):
        rows = get_member_upgrade_logs(member_id)
        return json_response(rows)

    @app.route('/api/members/<member_id:int>/manual-upgrade', method='POST')
    @require_login
    def api_member_manual_upgrade(member_id):
        data = request.json
        user = get_session_user()
        try:
            manual_upgrade_member(member_id, data.get('new_level_id'), user['id'], data.get('remark', ''))
            new_level = MemberLevelRepository.get_by_id(data.get('new_level_id'))
            return json_response(None, True, f'会员等级已调整为{new_level["name"]}')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/member-levels', method='GET')
    @require_login
    def api_member_levels():
        rows = MemberLevelRepository.list_active()
        return json_response(rows)

    @app.route('/api/member-levels', method='POST')
    @require_login
    def api_create_member_level():
        data = request.json
        try:
            MemberLevelRepository.create(
                name=data['name'],
                discount_rate=float(data['discount_rate']),
                deposit_discount_rate=float(data['deposit_discount_rate']),
                loss_fee_discount_rate=float(data['loss_fee_discount_rate']),
                reissue_fee_discount_rate=float(data['reissue_fee_discount_rate']),
                min_top_up=float(data.get('min_top_up', 0)),
                description=data.get('description', '')
            )
            return json_response(None, True, '等级创建成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/member-levels/<level_id:int>', method='PUT')
    @require_login
    def api_update_member_level(level_id):
        data = request.json
        try:
            MemberLevelRepository.update(
                level_id,
                name=data['name'],
                discount_rate=float(data['discount_rate']),
                deposit_discount_rate=float(data['deposit_discount_rate']),
                loss_fee_discount_rate=float(data['loss_fee_discount_rate']),
                reissue_fee_discount_rate=float(data['reissue_fee_discount_rate']),
                min_top_up=float(data.get('min_top_up', 0)),
                description=data.get('description', '')
            )
            return json_response(None, True, '等级更新成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/member-packages', method='GET')
    @require_login
    def api_member_packages_list():
        rows = MemberPackageRepository.list_all()
        return json_response(rows)

    @app.route('/api/member-packages', method='POST')
    @require_login
    def api_create_member_package():
        data = request.json
        try:
            area_ids = data.get('applicable_bath_area_ids', [])
            if isinstance(area_ids, str):
                area_ids = [int(x) for x in area_ids.split(',') if x.strip()]
            MemberPackageRepository.create(
                name=data['name'],
                package_type=data['package_type'],
                total_count=data.get('total_count'),
                valid_days=data.get('valid_days'),
                price=float(data['price']),
                original_value=float(data['original_value']),
                applicable_bath_area_ids=area_ids,
                cross_store_enabled=data.get('cross_store_enabled', False),
                description=data.get('description', '')
            )
            return json_response(None, True, '套餐创建成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/member-packages/<pkg_id:int>', method='PUT')
    @require_login
    def api_update_member_package(pkg_id):
        data = request.json
        try:
            area_ids = data.get('applicable_bath_area_ids', [])
            if isinstance(area_ids, str):
                area_ids = [int(x) for x in area_ids.split(',') if x.strip()]
            MemberPackageRepository.update(
                pkg_id,
                name=data['name'],
                package_type=data['package_type'],
                total_count=data.get('total_count'),
                valid_days=data.get('valid_days'),
                price=float(data['price']),
                original_value=float(data['original_value']),
                applicable_bath_area_ids=area_ids,
                cross_store_enabled=data.get('cross_store_enabled', False),
                description=data.get('description', ''),
                is_active=data.get('is_active', True)
            )
            return json_response(None, True, '套餐更新成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/member-stats', method='GET')
    @require_login
    def api_member_stats():
        date_str = request.query.get('date', '')
        try:
            stats = get_member_stats(date_str=date_str if date_str else None)
            return json_response(stats)
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/promotions', method='GET')
    @require_login
    def api_promotions_list():
        rows = MemberPromotionRepository.list_all()
        return json_response(rows)

    @app.route('/api/promotions/active', method='GET')
    @require_login
    def api_promotions_active():
        level_id = request.query.get('level_id', '')
        promotion_type = request.query.get('type', '')
        rows = MemberPromotionRepository.get_active(
            level_id=int(level_id) if level_id else None,
            promotion_type=promotion_type if promotion_type else None
        )
        return json_response(rows)

    @app.route('/api/promotions', method='POST')
    @require_login
    def api_create_promotion():
        data = request.json
        try:
            level_ids = data.get('applicable_level_ids', [])
            if isinstance(level_ids, str):
                level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
            MemberPromotionRepository.create(
                name=data['name'],
                promotion_type=data['promotion_type'],
                discount_rate=float(data.get('discount_rate', 100)),
                applicable_level_ids=level_ids,
                start_time=data.get('start_time'),
                end_time=data.get('end_time'),
                description=data.get('description', '')
            )
            return json_response(None, True, '活动创建成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/promotions/<promo_id:int>', method='PUT')
    @require_login
    def api_update_promotion(promo_id):
        data = request.json
        try:
            level_ids = data.get('applicable_level_ids', [])
            if isinstance(level_ids, str):
                level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
            MemberPromotionRepository.update(
                promo_id,
                name=data['name'],
                promotion_type=data['promotion_type'],
                discount_rate=float(data.get('discount_rate', 100)),
                applicable_level_ids=level_ids,
                start_time=data.get('start_time'),
                end_time=data.get('end_time'),
                description=data.get('description', ''),
                is_active=data.get('is_active', True)
            )
            return json_response(None, True, '活动更新成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/promotions/<promo_id:int>', method='DELETE')
    @require_login
    def api_delete_promotion(promo_id):
        MemberPromotionRepository.delete(promo_id)
        return json_response(None, True, '活动删除成功')

    @app.route('/api/topup-bonus-rules', method='GET')
    @require_login
    def api_topup_bonus_rules_list():
        rows = TopupBonusRepository.list_all()
        return json_response(rows)

    @app.route('/api/topup-bonus-rules', method='POST')
    @require_login
    def api_create_topup_bonus_rule():
        data = request.json
        try:
            level_ids = data.get('applicable_level_ids', [])
            if isinstance(level_ids, str):
                level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
            TopupBonusRepository.create(
                name=data['name'],
                min_amount=float(data['min_amount']),
                bonus_amount=float(data.get('bonus_amount', 0)),
                bonus_percent=float(data.get('bonus_percent', 0)),
                applicable_level_ids=level_ids,
                priority=int(data.get('priority', 0)),
                description=data.get('description', '')
            )
            return json_response(None, True, '充值赠送规则创建成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/topup-bonus-rules/<rule_id:int>', method='PUT')
    @require_login
    def api_update_topup_bonus_rule(rule_id):
        data = request.json
        try:
            level_ids = data.get('applicable_level_ids', [])
            if isinstance(level_ids, str):
                level_ids = [int(x) for x in level_ids.split(',') if x.strip()]
            TopupBonusRepository.update(
                rule_id,
                name=data['name'],
                min_amount=float(data['min_amount']),
                bonus_amount=float(data.get('bonus_amount', 0)),
                bonus_percent=float(data.get('bonus_percent', 0)),
                applicable_level_ids=level_ids,
                priority=int(data.get('priority', 0)),
                description=data.get('description', ''),
                is_active=data.get('is_active', True)
            )
            return json_response(None, True, '充值赠送规则更新成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/topup-bonus-rules/<rule_id:int>', method='DELETE')
    @require_login
    def api_delete_topup_bonus_rule(rule_id):
        TopupBonusRepository.delete(rule_id)
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
