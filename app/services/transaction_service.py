from datetime import datetime

from app.repositories import (
    MemberRepository,
    MemberPackagePurchaseRepository,
    MemberPackageUsageRepository,
    MemberTransactionRepository,
    ShiftRecordRepository,
)


def create_member_transaction(member_id, transaction_type, amount, balance_after, operator_id, remark='', **kwargs):
    return MemberTransactionRepository.create(
        member_id=member_id,
        transaction_type=transaction_type,
        amount=amount,
        balance_after=balance_after,
        operator_id=operator_id,
        remark=remark,
        issue_record_id=kwargs.get('issue_record_id'),
        package_purchase_id=kwargs.get('package_purchase_id'),
    )


def use_package_for_consumption(purchase_id, member_id, issue_record_id, deduction_amount, operator_id):
    purchase = MemberPackagePurchaseRepository.get_by_id(purchase_id)
    if not purchase:
        return False
    if purchase['remaining_count'] is not None and purchase['remaining_count'] <= 0:
        return False

    MemberPackageUsageRepository.create(
        purchase_id=purchase_id,
        member_id=member_id,
        issue_record_id=issue_record_id,
        deduction_amount=deduction_amount,
    )

    if purchase['remaining_count'] is not None:
        MemberPackagePurchaseRepository.decrement_remaining(purchase_id)
        from app.database import query_one
        updated = query_one("SELECT remaining_count FROM member_package_purchases WHERE id = %s", (purchase_id,))
        if updated and updated['remaining_count'] <= 0:
            MemberPackagePurchaseRepository.mark_used_up(purchase_id)

    from app.database import execute
    execute(
        "UPDATE members SET total_package_deduction = total_package_deduction + %s, last_active_at = %s WHERE id = %s",
        (deduction_amount, datetime.now(), member_id)
    )

    from app.database import query_one
    member_balance = query_one("SELECT balance FROM members WHERE id = %s", (member_id,))
    balance_after = float(member_balance['balance']) if member_balance else 0.0

    create_member_transaction(
        member_id=member_id,
        transaction_type='package_deduction',
        amount=deduction_amount,
        balance_after=balance_after,
        operator_id=operator_id,
        remark=f'套餐核销扣减 {deduction_amount}元',
        issue_record_id=issue_record_id,
    )

    return True


def deduct_member_balance(member_id, amount, issue_record_id, operator_id, remark=''):
    from app.database import query_one
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

    from app.database import execute
    execute(
        "UPDATE members SET balance = %s, gift_balance = %s, total_consumption = total_consumption + %s, last_active_at = %s WHERE id = %s",
        (new_regular, new_gift, amount, datetime.now(), member_id)
    )

    remark_text = remark or f'消费扣减 {amount}元'
    if gift_used > 0:
        remark_text += f' (含赠送余额{gift_used}元)'

    create_member_transaction(
        member_id=member_id,
        transaction_type='consumption',
        amount=amount,
        balance_after=new_regular,
        operator_id=operator_id,
        remark=remark_text,
        issue_record_id=issue_record_id,
    )

    shift = ShiftRecordRepository.get_active_shift(operator_id)
    if shift and gift_used > 0:
        ShiftRecordRepository.add_member_gift_balance_used(shift['id'], gift_used)

    return True
