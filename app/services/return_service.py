from datetime import datetime

from app.repositories import (
    IssueRecordRepository,
    WristbandRepository,
    ShiftRecordRepository,
    MemberRepository,
    MemberPackagePurchaseRepository,
)
from app.services.wristband_service import WristbandService
from app.services.transaction_service import (
    use_package_for_consumption,
    deduct_member_balance,
)
from app.services.member_service import get_current_store_id
from app.services.warning_service import check_frozen_misuse
from app.services.cross_store_service import (
    is_cross_store_member,
    validate_cross_store_rights,
    get_clearing_rule,
    create_cross_store_record,
)


class ReturnService:

    @staticmethod
    def return_band(record_id, operator_id, **kwargs):
        record = IssueRecordRepository.get_by_id(record_id)
        if not record:
            raise ValueError('记录不存在')
        if record['return_time']:
            raise ValueError('该记录已退牌')

        band = WristbandRepository.get_by_id(record['wristband_id'])
        if band and band['current_status'] == 'frozen':
            check_frozen_misuse(record['wristband_id'], '退牌结算', operator_id)
            raise ValueError('该手牌已冻结，无法退回流转')

        return_time = datetime.now()
        if return_time < record['issue_time']:
            raise ValueError('退牌时间不能早于发牌时间')

        extra_fee = float(kwargs.get('extra_fee', 0) or 0)
        loss_fee = float(kwargs.get('loss_fee', 0) or 0)
        reissue_fee = float(kwargs.get('reissue_fee', 0) or 0)
        deposit_status = kwargs.get('deposit_status', 'returned')
        use_package_id = kwargs.get('use_package_id')
        use_balance = kwargs.get('use_balance', False)

        total_fee = (record['base_fee'] or 0) + extra_fee + loss_fee + reissue_fee

        package_deduction = 0.0
        balance_deduction = 0.0
        cross_store_deduction = 0.0

        if record.get('member_id'):
            member = MemberRepository.get_by_id(record['member_id'])
            if member:
                user = {'id': operator_id}
                current_store_id = get_current_store_id(user)
                is_cross = is_cross_store_member(member, current_store_id)

                if use_package_id:
                    if is_cross:
                        valid, err_msg = validate_cross_store_rights(member, 'use_package', current_store_id)
                        if not valid:
                            raise ValueError(f'跨店权益校验失败: {err_msg}')
                    pkg_purchase = MemberPackagePurchaseRepository.get_by_id(use_package_id)
                    if pkg_purchase:
                        deduction_amount = min(total_fee, float(record['base_fee'] or 0))
                        if use_package_for_consumption(use_package_id, record['member_id'], record_id, deduction_amount, operator_id):
                            package_deduction = deduction_amount
                            total_fee = max(0, total_fee - package_deduction)

                if use_balance and total_fee > 0:
                    if is_cross:
                        valid, err_msg = validate_cross_store_rights(member, 'use_balance', current_store_id)
                        if not valid:
                            raise ValueError(f'跨店权益校验失败: {err_msg}')
                    balance_available = float(member['balance'])
                    balance_deduction = min(total_fee, balance_available)
                    if balance_deduction > 0:
                        if deduct_member_balance(record['member_id'], balance_deduction, record_id, operator_id, f'退牌结算余额抵扣 {balance_deduction}元'):
                            total_fee = max(0, total_fee - balance_deduction)

                if is_cross and (package_deduction > 0 or balance_deduction > 0):
                    home_store_id = member.get('home_store_id')
                    if home_store_id and current_store_id:
                        total_deduction = package_deduction + balance_deduction
                        rule = get_clearing_rule(home_store_id, current_store_id, member.get('level_id'))
                        cross_store_ded = total_deduction
                        create_cross_store_record(
                            member_id=member['id'],
                            issue_record_id=record_id,
                            home_store_id=home_store_id,
                            consume_store_id=current_store_id,
                            operation_type='return_settle',
                            original_amount=total_fee + total_deduction,
                            deduction_amount=total_deduction,
                            operator_id=operator_id,
                            clearing_rule_id=rule['id'] if rule else None,
                            remark=f'跨店退牌结算 套餐抵扣{package_deduction:.2f}元 余额抵扣{balance_deduction:.2f}元',
                        )
                        cross_store_deduction = cross_store_ded

                shift = ShiftRecordRepository.get_active_shift(operator_id)
                if shift:
                    updates = []
                    params = []
                    if package_deduction > 0:
                        updates.append('member_package_deduction = member_package_deduction + %s')
                        params.append(package_deduction)
                        updates.append('member_package_verify_count = member_package_verify_count + 1')
                    if balance_deduction > 0:
                        updates.append('member_balance_deduction = member_balance_deduction + %s')
                        params.append(balance_deduction)
                    updates.append('member_consume_count = member_consume_count + 1')
                    if updates:
                        params.append(shift['id'])
                        from app.database import execute
                        execute('UPDATE shift_records SET ' + ', '.join(updates) + ' WHERE id = %s', params)

        old_band_status = band['current_status'] if band else None

        IssueRecordRepository.update_return(
            record_id=record_id,
            return_time=return_time,
            extra_fee=extra_fee,
            loss_fee=loss_fee,
            reissue_fee=reissue_fee,
            package_deduction=package_deduction,
            balance_deduction=balance_deduction,
            cross_store_deduction=cross_store_deduction,
        )

        if band and band['current_status'] != 'frozen':
            WristbandRepository.update_status(
                band['id'],
                'available',
                deposit_status=deposit_status,
            )
            WristbandService.log_status_change(
                wristband_id=band['id'],
                old_status=old_band_status,
                new_status='available',
                change_reason='退牌结算',
                issue_record_id=record_id,
                operator_id=operator_id,
                phone=record['phone'],
                customer_name=record['customer_name'],
                remark=f'总费用: {total_fee}元, 套餐抵扣: {package_deduction}元, 余额抵扣: {balance_deduction}元, 押金状态: {deposit_status}',
                change_time=return_time,
            )

        shift = ShiftRecordRepository.get_active_shift(operator_id)
        if shift:
            ShiftRecordRepository.add_total_income(shift['id'], total_fee)

        return {
            'total_fee': total_fee,
            'package_deduction': package_deduction,
            'balance_deduction': balance_deduction,
            'cash_to_pay': total_fee,
        }
