from datetime import datetime, date
from app.database import query, query_one, execute
from app.repositories import (
    CrossStoreRepository,
    ClearingRecordRepository,
    ClearingRuleRepository,
    StoreRepository,
    MemberPackagePurchaseRepository,
    ShiftRecordRepository,
)


def is_cross_store_member(member, current_store_id):
    if not member or not current_store_id:
        return False
    home_store_id = member.get('home_store_id')
    return home_store_id is not None and home_store_id != current_store_id


def validate_cross_store_rights(member, operation_type, current_store_id):
    if not is_cross_store_member(member, current_store_id):
        return True, None
    if operation_type in ('issue', 'return', 'reissue'):
        return True, None
    if operation_type == 'use_package':
        packages = MemberPackagePurchaseRepository.get_available_packages(member['id'])
        for pkg in packages:
            if pkg.get('cross_store_enabled'):
                return True, None
        return False, '该会员的套餐不支持跨店使用'
    if operation_type == 'use_balance':
        if member.get('balance_cross_store_enabled'):
            return True, None
        return False, '该会员的储值余额不支持跨店使用'
    return True, None


def get_clearing_rule(home_store_id, consume_store_id, member_level_id=None):
    return ClearingRuleRepository.get_clearing_rule(
        home_store_id=home_store_id,
        consume_store_id=consume_store_id,
        member_level_id=member_level_id,
    )


def create_cross_store_record(member_id, issue_record_id, home_store_id, consume_store_id,
                               operation_type, original_amount, deduction_amount,
                               operator_id, **kwargs):
    clearing_rule_id = kwargs.get('clearing_rule_id')
    remark = kwargs.get('remark', '')

    record_id = CrossStoreRepository.create(
        member_id=member_id,
        issue_record_id=issue_record_id,
        home_store_id=home_store_id,
        consume_store_id=consume_store_id,
        operation_type=operation_type,
        original_amount=original_amount,
        deduction_amount=deduction_amount,
        clearing_rule_id=clearing_rule_id,
        operator_id=operator_id,
        remark=remark,
    )

    rule = None
    if clearing_rule_id:
        rule = ClearingRuleRepository.get_by_id(clearing_rule_id)
    if not rule:
        rule = {'source_ratio': 50.00, 'target_ratio': 50.00, 'hq_subsidy_ratio': 0.00}

    if deduction_amount > 0:
        source_amount = round(deduction_amount * float(rule['source_ratio']) / 100.0, 2)
        target_amount = round(deduction_amount * float(rule['target_ratio']) / 100.0, 2)
        hq_amount = round(deduction_amount * float(rule.get('hq_subsidy_ratio', 0) or 0) / 100.0, 2)

        ClearingRecordRepository.create(
            cross_store_record_id=record_id,
            store_id=home_store_id,
            amount_type='source_income',
            amount=source_amount,
            status='pending',
        )

        ClearingRecordRepository.create(
            cross_store_record_id=record_id,
            store_id=consume_store_id,
            amount_type='target_income',
            amount=target_amount,
            status='pending',
        )

        if hq_amount > 0:
            hq_store = StoreRepository.get_headquarters()
            if hq_store:
                ClearingRecordRepository.create(
                    cross_store_record_id=record_id,
                    store_id=hq_store['id'],
                    amount_type='hq_subsidy',
                    amount=hq_amount,
                    status='pending',
                )

    shift = ShiftRecordRepository.get_active_shift(operator_id)
    if shift:
        ShiftRecordRepository.add_cross_store_deduction(
            shift_id=shift['id'],
            deduction_amount=deduction_amount,
            amount=deduction_amount,
        )

    return record_id


def process_cross_store_clearing(cross_store_record_id, operator_id):
    record = CrossStoreRepository.get_by_id(cross_store_record_id)
    if not record:
        return False
    if record['clearing_status'] != 'pending':
        return False

    settled_at = datetime.now()
    ClearingRecordRepository.mark_settled_by_cross_store(cross_store_record_id, settled_at)

    CrossStoreRepository.update(
        cross_store_record_id,
        clearing_status='settled',
        settled_at=settled_at,
    )

    return True


def batch_clearing(record_ids, operator_id):
    success_count = 0
    for rid in record_ids:
        if process_cross_store_clearing(rid, operator_id):
            success_count += 1
    return success_count


def list_cross_store_records(status='', store_id='', start_date='', end_date='', limit=100):
    return CrossStoreRepository.list(
        status=status,
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


def list_clearing_records(store_id='', status=''):
    return ClearingRecordRepository.list(
        store_id=store_id,
        status=status,
    )
