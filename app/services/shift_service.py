from datetime import datetime

from app.repositories import ShiftRecordRepository, IssueRecordRepository
from app.utils.helpers import generate_shift_no


class ShiftService:

    @classmethod
    def get_active_shift(cls, operator_id):
        return ShiftRecordRepository.get_active_shift(operator_id)

    @classmethod
    def start_shift(cls, operator_id):
        active_shift = ShiftRecordRepository.get_active_shift(operator_id)
        if active_shift:
            return {
                'success': False,
                'message': '已有活跃班次',
                'data': None
            }

        shift_no = generate_shift_no()
        ShiftRecordRepository.create(shift_no, operator_id, datetime.now())

        new_shift = ShiftRecordRepository.get_active_shift(operator_id)
        return {
            'success': True,
            'message': '班次已开始',
            'data': new_shift
        }

    @classmethod
    def close_shift(cls, operator_id):
        shift = ShiftRecordRepository.get_active_shift(operator_id)
        if not shift:
            return {
                'success': False,
                'message': '没有活跃的班次',
                'data': None
            }

        unsettled_count = IssueRecordRepository.get_unsettled_count(operator_id, shift['start_time'])
        if unsettled_count > 0:
            return {
                'success': False,
                'message': f'还有 {unsettled_count} 条未结算记录，无法交接',
                'data': None
            }

        ShiftRecordRepository.close_shift(shift['id'], datetime.now())

        shift_no = generate_shift_no()
        ShiftRecordRepository.create(shift_no, operator_id, datetime.now())

        new_shift = ShiftRecordRepository.get_active_shift(operator_id)
        return {
            'success': True,
            'message': '交接完成，新班次已开始',
            'data': new_shift
        }

    @classmethod
    def update_shift_stats(cls, shift_id, **kwargs):
        if not kwargs:
            return {
                'success': False,
                'message': '没有提供更新参数',
                'data': None
            }

        ShiftRecordRepository.update(shift_id, **kwargs)

        updated_shift = ShiftRecordRepository.get_by_id(shift_id)
        return {
            'success': True,
            'message': '班次统计已更新',
            'data': updated_shift
        }

    @classmethod
    def get_shift_records(cls, operator_id, start_time):
        return IssueRecordRepository.get_by_operator_and_time(operator_id, start_time)

    @classmethod
    def calculate_shift_summary(cls, records, shift):
        unsettled = [r for r in records if r['fee_status'] != 'settled']
        reissues = [r for r in records if r.get('has_reissue')]

        total_income = sum(
            float(r['base_fee'] or 0) + float(r['extra_fee'] or 0) +
            float(r['loss_fee'] or 0) + float(r['reissue_fee'] or 0)
            for r in records if r['fee_status'] == 'settled'
        )

        summary = {
            'issue_count': len(records),
            'reissue_count': len(reissues),
            'unsettled_count': len(unsettled),
            'total_income': total_income,
            'member_consume_count': int(shift.get('member_consume_count', 0) or 0),
            'member_top_up_total': float(shift.get('member_top_up_total', 0) or 0),
            'member_package_verify_count': int(shift.get('member_package_verify_count', 0) or 0),
            'member_balance_deduction': float(shift.get('member_balance_deduction', 0) or 0),
            'member_package_deduction': float(shift.get('member_package_deduction', 0) or 0),
            'member_issue_count': int(shift.get('member_issue_count', 0) or 0),
            'member_package_purchase_count': int(shift.get('member_package_purchase_count', 0) or 0),
            'member_gift_balance_used': float(shift.get('member_gift_balance_used', 0) or 0),
            'member_new_count': int(shift.get('member_new_count', 0) or 0),
            'cross_store_income': float(shift.get('cross_store_income', 0) or 0),
            'cross_store_deduction': float(shift.get('cross_store_deduction', 0) or 0),
            'cross_store_issue_count': int(shift.get('cross_store_issue_count', 0) or 0),
            'pending_clearing_amount': float(shift.get('pending_clearing_amount', 0) or 0),
            'hq_subsidy_amount': float(shift.get('hq_subsidy_amount', 0) or 0),
        }

        return summary
