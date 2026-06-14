from app.database import query, query_one, execute
from .base import BaseRepository


class IssueRecordRepository(BaseRepository):
    table_name = 'issue_records'

    @classmethod
    def search_unreturned(cls, keyword):
        sql = '''SELECT ir.*, w.wristband_no, ba.name as bath_area_name, u.full_name as operator_name
                 FROM issue_records ir 
                 LEFT JOIN wristbands w ON ir.wristband_id = w.id
                 LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
                 LEFT JOIN users u ON ir.operator_id = u.id
                 WHERE ir.return_time IS NULL AND (
                     ir.serial_no LIKE %s OR w.wristband_no LIKE %s OR ir.phone LIKE %s OR ir.customer_name LIKE %s
                 ) ORDER BY ir.issue_time DESC'''
        like = f'%{keyword}%'
        results = query(sql, (like, like, like, like))
        return [dict(r) for r in results] if results else []

    @classmethod
    def search_active_normal(cls, keyword):
        sql = '''SELECT ir.*, w.wristband_no, ba.name as bath_area_name,
                        m.name as member_name, m.member_no, m.balance as member_balance,
                        ml.name as level_name, ml.discount_rate, ml.loss_fee_discount_rate, ml.reissue_fee_discount_rate
                 FROM issue_records ir 
                 LEFT JOIN wristbands w ON ir.wristband_id = w.id
                 LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
                 LEFT JOIN members m ON ir.member_id = m.id
                 LEFT JOIN member_levels ml ON m.level_id = ml.id
                 WHERE ir.return_time IS NULL AND ir.lost_status = 'normal' AND (
                     ir.serial_no LIKE %s OR w.wristband_no LIKE %s OR ir.phone LIKE %s OR ir.customer_name LIKE %s
                 ) ORDER BY ir.issue_time DESC'''
        like = f'%{keyword}%'
        results = query(sql, (like, like, like, like))
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_serial_no(cls, serial_no):
        sql = 'SELECT * FROM issue_records WHERE serial_no = %s'
        result = query_one(sql, (serial_no,))
        return dict(result) if result else None

    @classmethod
    def get_by_id(cls, record_id):
        sql = 'SELECT * FROM issue_records WHERE id = %s'
        result = query_one(sql, (record_id,))
        return dict(result) if result else None

    @classmethod
    def get_by_operator_and_time(cls, operator_id, start_time):
        sql = '''
            SELECT ir.*, w.wristband_no, ba.name as bath_area_name,
                   CASE WHEN ra.id IS NOT NULL THEN TRUE ELSE FALSE END as has_reissue,
                   m.name as member_name, m.member_no, ml.name as level_name
            FROM issue_records ir
            LEFT JOIN wristbands w ON ir.wristband_id = w.id
            LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
            LEFT JOIN reissue_applications ra ON ra.issue_record_id = ir.id
            LEFT JOIN members m ON ir.member_id = m.id
            LEFT JOIN member_levels ml ON m.level_id = ml.id
            WHERE ir.operator_id = %s AND ir.issue_time >= %s
            ORDER BY ir.issue_time DESC
        '''
        results = query(sql, (operator_id, start_time))
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_unsettled_count(cls, operator_id, start_time):
        sql = '''
            SELECT COUNT(*) as cnt FROM issue_records 
            WHERE operator_id = %s AND issue_time >= %s AND fee_status != 'settled'
        '''
        result = query_one(sql, (operator_id, start_time))
        return int(result['cnt']) if result else 0

    @classmethod
    def count_by_phone_with_unsettled_loss(cls, phone):
        if not phone:
            return False, []
        sql = '''
            SELECT ir.*, ra.review_status, ra.id as reissue_id
            FROM issue_records ir 
            LEFT JOIN reissue_applications ra ON ra.issue_record_id = ir.id 
            WHERE ir.phone = %s AND ir.lost_status = 'lost' AND ir.fee_status != 'settled'
            ORDER BY ir.issue_time DESC
        '''
        records = query(sql, (phone,))
        has_issue = len(records) > 0
        return has_issue, [dict(r) for r in records]

    @classmethod
    def count_by_status(cls, fee_status='unsettled'):
        sql = "SELECT COUNT(*) as cnt FROM issue_records WHERE fee_status = %s AND return_time IS NULL"
        result = query_one(sql, (fee_status,))
        return int(result['cnt']) if result else 0

    @classmethod
    def count_by_date_and_member(cls, date_str):
        sql = "SELECT COUNT(*) as cnt FROM issue_records WHERE member_id IS NOT NULL AND DATE(issue_time) = %s"
        result = query_one(sql, (date_str,))
        return int(result['cnt']) if result else 0

    @classmethod
    def sum_settled_income_by_store_and_date(cls, store_id, date_str):
        sql = '''
            SELECT COALESCE(SUM(base_fee + extra_fee + loss_fee + reissue_fee), 0) as total
            FROM issue_records WHERE store_id = %s AND fee_status = 'settled' AND DATE(issue_time) = %s
        '''
        result = query_one(sql, (store_id, date_str))
        return float(result['total']) if result and result['total'] else 0.0

    @classmethod
    def create(cls, serial_no, customer_name, phone, wristband_id, bath_area_id, issue_time,
               base_fee, deposit_amount, operator_id, fee_status='unsettled', lost_status='normal',
               member_id=None, actual_deposit=None, member_discount_rate=None, member_deposit_rate=None,
               store_id=None, is_cross_store=False, member_home_store_id=None):
        sql = '''
            INSERT INTO issue_records 
            (serial_no, customer_name, phone, wristband_id, bath_area_id, issue_time, 
             base_fee, deposit_amount, operator_id, fee_status, lost_status,
             member_id, actual_deposit, member_discount_rate, member_deposit_rate,
             store_id, is_cross_store, member_home_store_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (
            serial_no, customer_name, phone, wristband_id,
            bath_area_id, issue_time,
            base_fee, deposit_amount,
            operator_id, fee_status, lost_status,
            member_id, actual_deposit, member_discount_rate, member_deposit_rate,
            store_id, is_cross_store, member_home_store_id
        ))

    @classmethod
    def update_return(cls, record_id, return_time, extra_fee, loss_fee, reissue_fee,
                      package_deduction=0, balance_deduction=0, cross_store_deduction=0):
        sql = '''
            UPDATE issue_records SET return_time=%s, extra_fee=%s, loss_fee=%s, reissue_fee=%s,
                   fee_status='settled', package_deduction=%s, balance_deduction=%s,
                   cross_store_deduction=%s
            WHERE id=%s
        '''
        return execute(sql, (return_time, extra_fee, loss_fee, reissue_fee,
                           package_deduction, balance_deduction, cross_store_deduction, record_id))

    @classmethod
    def update_lost_status(cls, record_id, lost_status):
        sql = "UPDATE issue_records SET lost_status = %s WHERE id = %s"
        return execute(sql, (lost_status, record_id))

    @classmethod
    def update_wristband(cls, record_id, wristband_id):
        sql = "UPDATE issue_records SET wristband_id = %s WHERE id = %s"
        return execute(sql, (wristband_id, record_id))

    @classmethod
    def update_fees(cls, record_id, loss_fee, reissue_fee):
        sql = "UPDATE issue_records SET loss_fee=%s, reissue_fee=%s WHERE id=%s"
        return execute(sql, (loss_fee, reissue_fee, record_id))

    @classmethod
    def count_by_serial_prefix(cls, prefix):
        sql = "SELECT COUNT(*) as cnt FROM issue_records WHERE serial_no LIKE %s"
        result = query_one(sql, (prefix + '%',))
        return int(result['cnt']) if result else 0

    @classmethod
    def delete(cls, record_id):
        return super().delete(record_id)
