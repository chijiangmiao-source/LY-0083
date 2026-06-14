from app.database import query, query_one, execute
from .base import BaseRepository


class ShiftRecordRepository(BaseRepository):
    table_name = 'shift_records'

    @classmethod
    def get_active_shift(cls, operator_id):
        sql = '''
            SELECT * FROM shift_records
            WHERE operator_id = %s AND status = 'active'
            ORDER BY start_time DESC LIMIT 1
        '''
        result = query_one(sql, (operator_id,))
        return dict(result) if result else None

    @classmethod
    def get_by_shift_no(cls, shift_no):
        sql = 'SELECT * FROM shift_records WHERE shift_no = %s'
        result = query_one(sql, (shift_no,))
        return dict(result) if result else None

    @classmethod
    def get_by_id(cls, shift_id):
        sql = 'SELECT * FROM shift_records WHERE id = %s'
        result = query_one(sql, (shift_id,))
        return dict(result) if result else None

    @classmethod
    def list_by_operator(cls, operator_id):
        sql = 'SELECT * FROM shift_records WHERE operator_id = %s ORDER BY start_time DESC'
        results = query(sql, (operator_id,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def create(cls, shift_no, operator_id, start_time):
        sql = '''
            INSERT INTO shift_records (shift_no, operator_id, start_time)
            VALUES (%s, %s, %s)
        '''
        return execute(sql, (shift_no, operator_id, start_time))

    @classmethod
    def close_shift(cls, shift_id, end_time):
        sql = '''
            UPDATE shift_records SET status = 'closed', end_time = %s WHERE id = %s
        '''
        return execute(sql, (end_time, shift_id))

    @classmethod
    def increment_issue_count(cls, shift_id):
        sql = "UPDATE shift_records SET issue_count = issue_count + 1 WHERE id = %s"
        return execute(sql, (shift_id,))

    @classmethod
    def increment_member_issue_count(cls, shift_id):
        sql = "UPDATE shift_records SET member_issue_count = member_issue_count + 1 WHERE id = %s"
        return execute(sql, (shift_id,))

    @classmethod
    def increment_reissue_count(cls, shift_id):
        sql = "UPDATE shift_records SET reissue_count = reissue_count + 1 WHERE id = %s"
        return execute(sql, (shift_id,))

    @classmethod
    def increment_member_consume_count(cls, shift_id):
        sql = "UPDATE shift_records SET member_consume_count = member_consume_count + 1 WHERE id = %s"
        return execute(sql, (shift_id,))

    @classmethod
    def increment_member_package_verify_count(cls, shift_id):
        sql = "UPDATE shift_records SET member_package_verify_count = member_package_verify_count + 1 WHERE id = %s"
        return execute(sql, (shift_id,))

    @classmethod
    def increment_member_new_count(cls, shift_id):
        sql = "UPDATE shift_records SET member_new_count = member_new_count + 1 WHERE id = %s"
        return execute(sql, (shift_id,))

    @classmethod
    def increment_member_package_purchase_count(cls, shift_id):
        sql = "UPDATE shift_records SET member_package_purchase_count = member_package_purchase_count + 1 WHERE id = %s"
        return execute(sql, (shift_id,))

    @classmethod
    def add_member_balance_deduction(cls, shift_id, amount):
        sql = "UPDATE shift_records SET member_balance_deduction = member_balance_deduction + %s WHERE id = %s"
        return execute(sql, (amount, shift_id))

    @classmethod
    def add_member_package_deduction(cls, shift_id, amount):
        sql = "UPDATE shift_records SET member_package_deduction = member_package_deduction + %s WHERE id = %s"
        return execute(sql, (amount, shift_id))

    @classmethod
    def add_member_top_up_total(cls, shift_id, amount):
        sql = "UPDATE shift_records SET member_top_up_total = member_top_up_total + %s WHERE id = %s"
        return execute(sql, (amount, shift_id))

    @classmethod
    def add_member_gift_balance_used(cls, shift_id, amount):
        sql = "UPDATE shift_records SET member_gift_balance_used = member_gift_balance_used + %s WHERE id = %s"
        return execute(sql, (amount, shift_id))

    @classmethod
    def add_total_income(cls, shift_id, amount):
        sql = "UPDATE shift_records SET total_income = total_income + %s WHERE id = %s"
        return execute(sql, (amount, shift_id))

    @classmethod
    def add_cross_store_deduction(cls, shift_id, deduction_amount, amount):
        sql = '''UPDATE shift_records SET
            cross_store_deduction = cross_store_deduction + %s,
            pending_clearing_amount = pending_clearing_amount + %s,
            cross_store_issue_count = cross_store_issue_count + 1
            WHERE id = %s'''
        return execute(sql, (deduction_amount, amount, shift_id))

    @classmethod
    def count_by_shift_no_prefix(cls, prefix):
        sql = "SELECT COUNT(*) as cnt FROM shift_records WHERE shift_no LIKE %s"
        result = query_one(sql, (prefix + '%',))
        return int(result['cnt']) if result else 0

    @classmethod
    def list_all(cls):
        return super().list_all('start_time DESC')

    @classmethod
    def update(cls, shift_id, **kwargs):
        return super().update(shift_id, **kwargs)

    @classmethod
    def delete(cls, shift_id):
        return super().delete(shift_id)
