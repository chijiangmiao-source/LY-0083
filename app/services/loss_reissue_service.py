from datetime import datetime, timedelta
from app.database import query, query_one
from app.repositories import (
    IssueRecordRepository,
    ReissueApplicationRepository,
    WristbandRepository,
    StatusLogRepository,
    WarningRepository,
    MemberRepository,
    MemberLevelRepository,
    MemberPromotionRepository,
    UserRepository,
)


class LossReissueService:

    @staticmethod
    def search_loss_records(keyword):
        return IssueRecordRepository.search_active_normal(keyword)

    @staticmethod
    def report_loss(issue_record_id, loss_description, operator_id):
        record = IssueRecordRepository.get_by_id(issue_record_id)
        if not record:
            raise ValueError('记录不存在')
        if record['lost_status'] != 'normal':
            raise ValueError('该记录已申报遗失')

        loss_time = datetime.now()

        IssueRecordRepository.update_lost_status(issue_record_id, 'lost')

        if record['wristband_id']:
            band = WristbandRepository.get_by_id(record['wristband_id'])
            old_status = band['current_status'] if band else None
            WristbandRepository.update_status(record['wristband_id'], 'frozen')
            StatusLogRepository.create(
                wristband_id=record['wristband_id'],
                old_status=old_status,
                new_status='frozen',
                change_reason='遗失申报冻结',
                issue_record_id=issue_record_id,
                operator_id=operator_id,
                phone=record['phone'],
                customer_name=record['customer_name'],
                remark=loss_description,
                change_time=loss_time,
            )

        user = UserRepository.get_by_id_with_store(operator_id)
        ReissueApplicationRepository.create(
            issue_record_id=issue_record_id,
            report_time=loss_time,
            reported_by=user['full_name'] if user else '',
            loss_description=loss_description,
        )

        try:
            LossReissueService._check_frequent_loss()
        except Exception:
            pass

        return True

    @staticmethod
    def get_pending_reissues():
        records = ReissueApplicationRepository.list_pending()
        result = []
        for r in records:
            if r.get('member_level_id'):
                loss_promos = MemberPromotionRepository.get_active_by_level_and_type(
                    r['member_level_id'], 'loss_fee'
                )
                reissue_promos = MemberPromotionRepository.get_active_by_level_and_type(
                    r['member_level_id'], 'reissue_fee'
                )
                r['loss_promotions'] = loss_promos
                r['reissue_promotions'] = reissue_promos
                if loss_promos:
                    best_loss = min(float(p['discount_rate']) for p in loss_promos)
                    r['effective_loss_fee_discount_rate'] = min(
                        float(r.get('loss_fee_discount_rate', 100) or 100), best_loss
                    )
                else:
                    r['effective_loss_fee_discount_rate'] = float(
                        r.get('loss_fee_discount_rate', 100) or 100
                    )
                if reissue_promos:
                    best_reissue = min(float(p['discount_rate']) for p in reissue_promos)
                    r['effective_reissue_fee_discount_rate'] = min(
                        float(r.get('reissue_fee_discount_rate', 100) or 100), best_reissue
                    )
                else:
                    r['effective_reissue_fee_discount_rate'] = float(
                        r.get('reissue_fee_discount_rate', 100) or 100
                    )
            result.append(r)
        return result

    @staticmethod
    def review_reissue(app_id, decision, operator_id, **kwargs):
        app = ReissueApplicationRepository.get_by_id(app_id)
        if not app:
            raise ValueError('申请不存在')
        if app['review_status'] != 'pending':
            raise ValueError('该申请已审核')

        is_responsible = kwargs.get('is_responsible', True)
        loss_fee = float(kwargs.get('loss_fee', 0) or 0)
        reissue_fee = float(kwargs.get('reissue_fee', 0) or 0)
        new_wristband_id = kwargs.get('new_wristband_id')
        review_time = datetime.now()

        if decision == 'reject':
            ReissueApplicationRepository.review(
                app_id=app_id,
                review_status='rejected',
                review_time=review_time,
                reviewer_id=operator_id,
                review_comment=kwargs.get('review_comment', ''),
            )
            record = IssueRecordRepository.get_by_id(app['issue_record_id'])
            if record and record['wristband_id']:
                band = WristbandRepository.get_by_id(record['wristband_id'])
                old_status = band['current_status'] if band else None
                if band and band['current_status'] == 'frozen':
                    WristbandRepository.update_status(record['wristband_id'], 'issued')
                    StatusLogRepository.create(
                        wristband_id=record['wristband_id'],
                        old_status='frozen',
                        new_status='issued',
                        change_reason='补办审核驳回，解除冻结',
                        issue_record_id=record['id'],
                        operator_id=operator_id,
                        phone=record['phone'],
                        customer_name=record['customer_name'],
                        remark=kwargs.get('review_comment', ''),
                        change_time=review_time,
                    )
            return True

        record = IssueRecordRepository.get_by_id(app['issue_record_id'])
        old_wristband_id = record['wristband_id'] if record else None

        if record and record.get('member_id'):
            member = MemberRepository.get_by_id_with_level(record['member_id'])
            if member:
                level = MemberLevelRepository.get_by_id(member['level_id'])
                if level:
                    loss_rate = float(level['loss_fee_discount_rate'])
                    reissue_rate = float(level['reissue_fee_discount_rate'])
                    loss_promos = MemberPromotionRepository.get_active_by_level_and_type(
                        member['level_id'], 'loss_fee'
                    )
                    reissue_promos = MemberPromotionRepository.get_active_by_level_and_type(
                        member['level_id'], 'reissue_fee'
                    )
                    if loss_promos:
                        best_loss = min(float(p['discount_rate']) for p in loss_promos)
                        loss_rate = min(loss_rate, best_loss)
                    if reissue_promos:
                        best_reissue = min(float(p['discount_rate']) for p in reissue_promos)
                        reissue_rate = min(reissue_rate, best_reissue)
                    if not kwargs.get('skip_auto_discount'):
                        loss_fee = round(
                            float(kwargs.get('loss_fee_original', loss_fee) or loss_fee)
                            * loss_rate / 100.0, 2
                        )
                        reissue_fee = round(
                            float(kwargs.get('reissue_fee_original', reissue_fee) or reissue_fee)
                            * reissue_rate / 100.0, 2
                        )

        ReissueApplicationRepository.review(
            app_id=app_id,
            review_status='approved',
            review_time=review_time,
            reviewer_id=operator_id,
            review_comment=kwargs.get('review_comment', ''),
            is_responsible=is_responsible,
            new_wristband_id=new_wristband_id,
        )

        IssueRecordRepository.update_fees(app['issue_record_id'], loss_fee, reissue_fee)

        if new_wristband_id:
            new_band = WristbandRepository.get_by_id(new_wristband_id)
            if new_band and new_band['current_status'] == 'available':
                if old_wristband_id and old_wristband_id != new_wristband_id:
                    WristbandRepository.update_status(old_wristband_id, 'replaced')
                    StatusLogRepository.create(
                        wristband_id=old_wristband_id,
                        old_status='frozen',
                        new_status='replaced',
                        change_reason='补办替换，旧手牌作废',
                        issue_record_id=app['issue_record_id'],
                        operator_id=operator_id,
                        phone=record['phone'] if record else None,
                        customer_name=record['customer_name'] if record else None,
                        remark=f'补办新手牌ID: {new_wristband_id}, 赔偿费: {loss_fee}元, 补办费: {reissue_fee}元',
                        change_time=review_time,
                    )
                WristbandRepository.update_status_and_issued_time(
                    new_wristband_id, 'issued', review_time
                )
                StatusLogRepository.create(
                    wristband_id=new_wristband_id,
                    old_status='available',
                    new_status='issued',
                    change_reason='补办发牌',
                    issue_record_id=app['issue_record_id'],
                    operator_id=operator_id,
                    phone=record['phone'] if record else None,
                    customer_name=record['customer_name'] if record else None,
                    remark=f'补办替换, 赔偿费: {loss_fee}元, 补办费: {reissue_fee}元',
                    change_time=review_time,
                )
                IssueRecordRepository.update_wristband(app['issue_record_id'], new_wristband_id)

        try:
            LossReissueService._check_continuous_reissue_in_area()
        except Exception:
            pass

        return True

    @staticmethod
    def calculate_effective_discount_rates(member_level_id):
        if not member_level_id:
            return {
                'loss_fee_discount_rate': 100.0,
                'reissue_fee_discount_rate': 100.0,
                'loss_promotions': [],
                'reissue_promotions': [],
            }

        level = MemberLevelRepository.get_by_id(member_level_id)
        base_loss_rate = float(level['loss_fee_discount_rate']) if level else 100.0
        base_reissue_rate = float(level['reissue_fee_discount_rate']) if level else 100.0

        loss_promos = MemberPromotionRepository.get_active_by_level_and_type(
            member_level_id, 'loss_fee'
        )
        reissue_promos = MemberPromotionRepository.get_active_by_level_and_type(
            member_level_id, 'reissue_fee'
        )

        effective_loss_rate = base_loss_rate
        if loss_promos:
            best_loss = min(float(p['discount_rate']) for p in loss_promos)
            effective_loss_rate = min(base_loss_rate, best_loss)

        effective_reissue_rate = base_reissue_rate
        if reissue_promos:
            best_reissue = min(float(p['discount_rate']) for p in reissue_promos)
            effective_reissue_rate = min(base_reissue_rate, best_reissue)

        return {
            'loss_fee_discount_rate': base_loss_rate,
            'reissue_fee_discount_rate': base_reissue_rate,
            'effective_loss_fee_discount_rate': effective_loss_rate,
            'effective_reissue_fee_discount_rate': effective_reissue_rate,
            'loss_promotions': loss_promos,
            'reissue_promotions': reissue_promos,
        }

    @staticmethod
    def _check_frequent_loss():
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
                WarningRepository.create(
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
    def _check_continuous_reissue_in_area():
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
                WarningRepository.create(
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
