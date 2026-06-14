from datetime import datetime

from app.repositories import (
    IssueRecordRepository,
    WristbandRepository,
    BathAreaRepository,
    ShiftRecordRepository,
)
from app.services.wristband_service import WristbandService
from app.services.member_service import get_member_by_phone
from app.services.member_service import get_current_store_id
from app.services.cross_store_service import (
    is_cross_store_member,
    validate_cross_store_rights,
    get_clearing_rule,
    create_cross_store_record,
)
from app.utils.helpers import generate_serial_no


class IssueService:

    @staticmethod
    def search_issue_records(keyword):
        return IssueRecordRepository.search_unreturned(keyword)

    @staticmethod
    def issue_band(wristband_id, customer_name, phone, operator_id, use_package_id=None, use_balance=False):
        phone = phone.strip() if phone else ''
        customer_name = customer_name.strip() if customer_name else ''

        band = WristbandRepository.get_by_id(wristband_id)
        if not band:
            raise ValueError('手牌不存在')
        if band['current_status'] != 'available':
            raise ValueError('该手牌当前不可用')

        has_issue, _ = WristbandService.phone_has_unsettled_loss(phone)
        if has_issue:
            raise ValueError('该手机号存在未结清遗失记录，无法领牌')

        area = BathAreaRepository.get_by_id(band['bath_area_id'])
        serial_no = generate_serial_no()
        issue_time = datetime.now()

        member_id = None
        member_discount_rate = 100.00
        member_deposit_rate = 100.00
        actual_deposit = area['deposit_amount'] if area else 0
        base_fee = area['base_price'] if area else 0

        user = {'id': operator_id}
        member = get_member_by_phone(phone)
        current_store_id = get_current_store_id(user)
        is_cross = False
        member_home_store_id = None

        if member:
            member_id = member['id']
            member_discount_rate = float(member['discount_rate'])
            member_deposit_rate = float(member['deposit_discount_rate'])
            actual_deposit = round(float(area['deposit_amount']) * member_deposit_rate / 100.0, 2) if area else 0
            base_fee = round(float(area['base_price']) * member_discount_rate / 100.0, 2) if area else 0
            member_home_store_id = member.get('home_store_id')
            if is_cross_store_member(member, current_store_id):
                is_cross = True
                valid, err_msg = validate_cross_store_rights(member, 'issue', current_store_id)
                if not valid:
                    raise ValueError(f'跨店权益校验失败: {err_msg}')

        IssueRecordRepository.create(
            serial_no=serial_no,
            customer_name=customer_name,
            phone=phone,
            wristband_id=wristband_id,
            bath_area_id=band['bath_area_id'],
            issue_time=issue_time,
            base_fee=base_fee,
            deposit_amount=area['deposit_amount'] if area else 0,
            operator_id=operator_id,
            fee_status='unsettled',
            lost_status='normal',
            member_id=member_id,
            actual_deposit=actual_deposit,
            member_discount_rate=member_discount_rate,
            member_deposit_rate=member_deposit_rate,
            store_id=current_store_id,
            is_cross_store=is_cross,
            member_home_store_id=member_home_store_id,
        )

        WristbandRepository.update_status_and_issued_time(
            wristband_id,
            'issued',
            issue_time,
        )

        new_record = IssueRecordRepository.get_by_serial_no(serial_no)
        new_record_id = new_record['id'] if new_record else None

        WristbandService.log_status_change(
            wristband_id=wristband_id,
            old_status=band['current_status'],
            new_status='issued',
            change_reason='入场发牌',
            issue_record_id=new_record_id,
            operator_id=operator_id,
            phone=phone,
            customer_name=customer_name,
            change_time=issue_time,
            remark=f'会员: {"是" if member_id else "否"}, 实收押金: {actual_deposit}元, 折扣率: {member_discount_rate}%',
        )

        if is_cross and member_id and member_home_store_id and current_store_id:
            original_amount = float(area['base_price'] if area else 0)
            discount_savings = original_amount - base_fee
            rule = get_clearing_rule(member_home_store_id, current_store_id, member.get('level_id'))
            create_cross_store_record(
                member_id=member_id,
                issue_record_id=new_record_id,
                home_store_id=member_home_store_id,
                consume_store_id=current_store_id,
                operation_type='issue',
                original_amount=original_amount,
                deduction_amount=discount_savings,
                operator_id=operator_id,
                clearing_rule_id=rule['id'] if rule else None,
                remark=f'跨店发牌 折扣优惠{discount_savings:.2f}元',
            )

        shift = ShiftRecordRepository.get_active_shift(operator_id)
        if shift:
            ShiftRecordRepository.increment_issue_count(shift['id'])
            if member_id:
                ShiftRecordRepository.increment_member_issue_count(shift['id'])

        record = IssueRecordRepository.get_by_serial_no(serial_no)
        result = dict(record) if record else {}
        if member:
            result['member_info'] = {
                'member_no': member['member_no'],
                'level_name': member['level_name'],
                'balance': float(member['balance']),
                'discount_rate': member_discount_rate,
                'deposit_rate': member_deposit_rate,
                'actual_deposit': actual_deposit,
                'discounted_base_fee': base_fee,
            }
        return result
