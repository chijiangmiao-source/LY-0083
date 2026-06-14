from datetime import datetime, date, timedelta
import json

from app.repositories import (
    WristbandRepository,
    IssueRecordRepository,
    ReissueApplicationRepository,
    MemberRepository,
    MemberTransactionRepository,
    MemberPackageUsageRepository,
    WarningRepository,
    StoreRepository,
    CrossStoreRepository,
    ClearingRecordRepository,
    UserRepository,
    BathAreaRepository,
    ShiftRecordRepository,
)


class WarningService:

    @staticmethod
    def _create_warning(warning_type, title, content, warning_level='normal',
                        wristband_id=None, issue_record_id=None, bath_area_id=None,
                        phone=None, related_data=None):
        WarningRepository.create(
            warning_type=warning_type,
            warning_level=warning_level,
            title=title,
            content=content,
            wristband_id=wristband_id,
            issue_record_id=issue_record_id,
            bath_area_id=bath_area_id,
            phone=phone,
            related_data=related_data,
        )

    @staticmethod
    def check_long_unreturned():
        from app.database import query, query_one
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
            existing = WarningRepository.exists_unresolved(
                warning_type='long_unreturned',
                identifier=r['id'],
                identifier_type='issue_record_id',
            )
            if not existing:
                hours = int((datetime.now() - r['issue_time']).total_seconds() / 3600)
                WarningService._create_warning(
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

    @staticmethod
    def check_frequent_loss():
        from app.database import query
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
            existing = WarningRepository.exists_unresolved(
                warning_type='frequent_loss',
                identifier=r['phone'],
                identifier_type='phone',
                since=since,
            )
            if not existing:
                WarningService._create_warning(
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

    @staticmethod
    def check_continuous_reissue_in_area():
        from app.database import query, query_one
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
            existing = WarningRepository.exists_unresolved(
                warning_type='continuous_reissue',
                identifier=r['bath_area_id'],
                identifier_type='bath_area_id',
                since=since,
            )
            if not existing:
                WarningService._create_warning(
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

    @staticmethod
    def check_abnormal_discount():
        from app.database import query
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
            existing = WarningRepository.exists_unresolved(
                warning_type='abnormal_discount',
                identifier=r['phone'],
                identifier_type='phone',
                since=since,
            )
            if not existing:
                WarningService._create_warning(
                    warning_type='abnormal_discount',
                    warning_level='medium',
                    title=f'会员[{r["member_name"]}]优惠折扣异常',
                    content=f'会员 {r["member_name"]}({r["phone"]}) 等级:{r["level_name"]}, '
                            f'折扣率:{r["discount_rate"]}%, 在{days_threshold}天内享受优惠{r["discount_count"]}次, '
                            f'优惠总额: {float(r["total_discount_amount"]):.2f}元, 请核查是否存在异常',
                    phone=r['phone'],
                    related_data={
                        'member_id': r['member_id'],
                        'discount_count': int(r['discount_count']),
                        'total_discount_amount': float(r['total_discount_amount']),
                        'days': days_threshold,
                        'discount_rate': float(r['discount_rate'])
                    }
                )

    @staticmethod
    def check_balance_anomaly():
        hours_threshold = 24
        topup_threshold = 5000.00
        consume_threshold = 3000.00
        since = datetime.now() - timedelta(hours=hours_threshold)

        topups = MemberTransactionRepository.get_topup_stats(None, since)
        for t in topups:
            t = dict(t)
            member = MemberRepository.get_by_id_with_level(t['member_id'])
            if not member:
                continue
            existing = WarningRepository.exists_unresolved(
                warning_type='balance_anomaly',
                identifier=member['phone'],
                identifier_type='phone',
                since=since,
            )
            if not existing:
                WarningService._create_warning(
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

        consumes = MemberTransactionRepository.get_consume_stats(None, since)
        for c in consumes:
            c = dict(c)
            member = MemberRepository.get_by_id_with_level(c['member_id'])
            if not member:
                continue
            existing = WarningRepository.exists_unresolved(
                warning_type='balance_anomaly',
                identifier=member['phone'],
                identifier_type='phone',
                since=since,
            )
            if not existing:
                WarningService._create_warning(
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

    @staticmethod
    def check_topup_anomaly():
        from app.database import query
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
            existing = WarningRepository.exists_unresolved(
                warning_type='topup_anomaly',
                identifier=r['phone'],
                identifier_type='phone',
                since=since,
            )
            if not existing:
                WarningService._create_warning(
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

    @staticmethod
    def check_cross_store_discount_anomaly():
        days_threshold = 7
        since = datetime.now() - timedelta(days=days_threshold)
        records = CrossStoreRepository.get_cross_store_discount_anomaly(since)
        for r in records:
            r = dict(r)
            existing = WarningRepository.exists_unresolved(
                warning_type='cross_store_discount_anomaly',
                identifier=r['phone'],
                identifier_type='phone',
                since=since,
            )
            if not existing:
                WarningService._create_warning(
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

    @staticmethod
    def run_all_warning_checks():
        try:
            WarningService.check_long_unreturned()
        except Exception:
            pass
        try:
            WarningService.check_frequent_loss()
        except Exception:
            pass
        try:
            WarningService.check_continuous_reissue_in_area()
        except Exception:
            pass
        try:
            WarningService.check_abnormal_discount()
        except Exception:
            pass
        try:
            WarningService.check_balance_anomaly()
        except Exception:
            pass
        try:
            WarningService.check_topup_anomaly()
        except Exception:
            pass
        try:
            WarningService.check_cross_store_discount_anomaly()
        except Exception:
            pass


def _get_current_store_id(user):
    if not user:
        return None
    u = UserRepository.get_by_id(user['id'])
    return u['store_id'] if u and u.get('store_id') else None


class ReportService:

    @staticmethod
    def get_dashboard_stats(user=None):
        WarningService.run_all_warning_checks()

        stats = {
            'available_bands': WristbandRepository.count_by_status('available'),
            'issued_bands': WristbandRepository.count_by_status('issued'),
            'frozen_bands': WristbandRepository.count_by_status('frozen'),
            'unsettled': IssueRecordRepository.count_by_status('unsettled'),
            'pending_review': ReissueApplicationRepository.count_pending(),
        }

        member_stats = ReportService.get_member_stats()

        cross_store_stats = {
            'today_local_income': 0.0,
            'today_cross_income': 0.0,
            'today_cross_deduction': 0.0,
            'pending_clearing': 0.0
        }
        try:
            current_store_id = _get_current_store_id(user)
            if current_store_id:
                today_str = date.today().strftime('%Y-%m-%d')
                cross_store_stats = ReportService.get_cross_store_stats(current_store_id, today_str)
        except Exception:
            pass

        warning_stats = WarningRepository.get_unread_stats()
        recent_warnings = ReportService.get_recent_warnings(limit=20)

        return {
            'wristband_stats': stats,
            'member_stats': member_stats,
            'cross_store_stats': cross_store_stats,
            'warning_stats': warning_stats,
            'recent_warnings': recent_warnings,
        }

    @staticmethod
    def get_member_stats(date_str=None):
        if date_str is None:
            date_str = date.today().strftime('%Y-%m-%d')

        return {
            'total_members': MemberRepository.count_by_status('active'),
            'today_new_members': MemberRepository.count_by_date(date_str),
            'today_consume_count': MemberTransactionRepository.count_by_type_and_date(
                ['consumption', 'package_deduction'], date_str),
            'today_top_up': MemberTransactionRepository.sum_by_type_and_date('topup', date_str),
            'today_package_verify': MemberPackageUsageRepository.count_by_date(date_str),
            'today_balance_deduction': MemberTransactionRepository.sum_by_type_and_date(
                'consumption', date_str),
            'today_package_deduction': MemberTransactionRepository.sum_by_type_and_date(
                'package_deduction', date_str),
            'today_gift_bonus': MemberTransactionRepository.sum_by_type_and_date(
                'gift_bonus', date_str),
            'today_member_issue_count': IssueRecordRepository.count_by_date_and_member(date_str),
        }

    @staticmethod
    def get_cross_store_stats(store_id, date_str=None):
        if date_str is None:
            date_str = date.today().strftime('%Y-%m-%d')

        stats = StoreRepository.get_stats(store_id, date_str)
        return {
            'today_local_income': stats['today_local_income'],
            'today_cross_income': stats['today_cross_store_income'],
            'today_cross_deduction': stats['today_cross_store_deduction'],
            'pending_clearing': stats['pending_clearing'],
            'hq_subsidy_total': stats['hq_subsidy_total'],
            'total_members_home': stats['total_members_home'],
            'today_cross_store_visits': stats['today_cross_store_visits'],
        }

    @staticmethod
    def get_recent_warnings(limit=20):
        try:
            return WarningRepository.get_recent(limit=limit)
        except Exception:
            return []

    @staticmethod
    def get_shift_summary(operator_id, shift_id):
        shift = ShiftRecordRepository.get_by_id(shift_id)
        if not shift:
            return None

        shift = dict(shift)
        start_time = shift['start_time']

        issue_records = IssueRecordRepository.get_by_operator_and_time(operator_id, start_time)
        unsettled_count = IssueRecordRepository.get_unsettled_count(operator_id, start_time)

        total_income = 0.0
        total_base_fee = 0.0
        total_extra_fee = 0.0
        total_loss_fee = 0.0
        total_reissue_fee = 0.0
        total_deposit = 0.0
        member_count = 0
        cross_store_count = 0

        for record in issue_records:
            total_base_fee += float(record.get('base_fee', 0) or 0)
            total_extra_fee += float(record.get('extra_fee', 0) or 0)
            total_loss_fee += float(record.get('loss_fee', 0) or 0)
            total_reissue_fee += float(record.get('reissue_fee', 0) or 0)
            total_deposit += float(record.get('actual_deposit', 0) or 0)
            if record.get('member_id'):
                member_count += 1
            if record.get('is_cross_store'):
                cross_store_count += 1

        total_income = total_base_fee + total_extra_fee + total_loss_fee + total_reissue_fee

        return {
            'shift': shift,
            'issue_records': issue_records,
            'summary': {
                'total_issues': len(issue_records),
                'unsettled_count': unsettled_count,
                'member_count': member_count,
                'cross_store_count': cross_store_count,
                'total_income': total_income,
                'total_base_fee': total_base_fee,
                'total_extra_fee': total_extra_fee,
                'total_loss_fee': total_loss_fee,
                'total_reissue_fee': total_reissue_fee,
                'total_deposit': total_deposit,
                'member_balance_deduction': float(shift.get('member_balance_deduction', 0) or 0),
                'member_package_deduction': float(shift.get('member_package_deduction', 0) or 0),
                'member_top_up_total': float(shift.get('member_top_up_total', 0) or 0),
                'member_gift_balance_used': float(shift.get('member_gift_balance_used', 0) or 0),
                'cross_store_deduction': float(shift.get('cross_store_deduction', 0) or 0),
                'pending_clearing_amount': float(shift.get('pending_clearing_amount', 0) or 0),
                'issue_count': int(shift.get('issue_count', 0) or 0),
                'member_issue_count': int(shift.get('member_issue_count', 0) or 0),
                'reissue_count': int(shift.get('reissue_count', 0) or 0),
                'member_consume_count': int(shift.get('member_consume_count', 0) or 0),
                'member_package_verify_count': int(shift.get('member_package_verify_count', 0) or 0),
                'member_new_count': int(shift.get('member_new_count', 0) or 0),
                'member_package_purchase_count': int(shift.get('member_package_purchase_count', 0) or 0),
                'cross_store_issue_count': int(shift.get('cross_store_issue_count', 0) or 0),
            }
        }

    @staticmethod
    def get_hq_report(start_date='', end_date=''):
        stores = StoreRepository.list_active()
        result = []

        for s in stores:
            s = dict(s)

            outgoing = CrossStoreRepository.get_outgoing_stats(
                s['id'], start_date=start_date, end_date=end_date)
            incoming = CrossStoreRepository.get_incoming_stats(
                s['id'], start_date=start_date, end_date=end_date)

            pending_clearing = ClearingRecordRepository.sum_by_store_and_status(
                s['id'], status='pending')
            settled_clearing = ClearingRecordRepository.sum_by_store_and_status(
                s['id'], status='settled')
            hq_subsidy = ClearingRecordRepository.sum_by_store_and_status(
                s['id'], status='settled', amount_type='hq_subsidy')

            s['outgoing'] = outgoing
            s['incoming'] = incoming
            s['pending_clearing'] = pending_clearing
            s['settled_clearing'] = settled_clearing
            s['hq_subsidy'] = hq_subsidy
            result.append(s)

        return result

    @staticmethod
    def get_hq_store_summary():
        WarningService.run_all_warning_checks()

        today = date.today()
        today_str = today.strftime('%Y-%m-%d')

        stores = StoreRepository.list_active()
        result = []
        for s in stores:
            s = dict(s)
            stats = StoreRepository.get_stats(s['id'], today_str)
            s['today_local_income'] = stats['today_local_income']
            s['today_cross_income'] = stats['today_cross_store_income']
            s['today_cross_deduction'] = stats['today_cross_store_deduction']
            s['pending_clearing'] = stats['pending_clearing']
            s['today_total'] = s['today_local_income'] + s['today_cross_income']
            s['total_members_home'] = stats['total_members_home']
            s['today_cross_store_visits'] = stats['today_cross_store_visits']
            s['hq_subsidy_total'] = stats['hq_subsidy_total']
            result.append(s)

        return result
