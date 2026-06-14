from app.database import query, query_one, execute
from .base import BaseRepository


class ReissueApplicationRepository(BaseRepository):
    table_name = 'reissue_applications'

    @classmethod
    def list_pending(cls):
        sql = '''
            SELECT ra.*, ir.serial_no, ir.customer_name, ir.phone, ir.base_fee, ir.deposit_amount,
                   ir.member_id, ir.actual_deposit, ir.member_discount_rate, ir.member_deposit_rate,
                   w.wristband_no as old_wristband_no, ba.name as bath_area_name,
                   m.name as member_name, m.member_no, m.balance as member_balance,
                   ml.name as level_name, ml.discount_rate as level_discount_rate,
                   ml.loss_fee_discount_rate, ml.reissue_fee_discount_rate, m.level_id as member_level_id
            FROM reissue_applications ra
            LEFT JOIN issue_records ir ON ra.issue_record_id = ir.id
            LEFT JOIN wristbands w ON ir.wristband_id = w.id
            LEFT JOIN bath_areas ba ON ir.bath_area_id = ba.id
            LEFT JOIN members m ON ir.member_id = m.id
            LEFT JOIN member_levels ml ON m.level_id = ml.id
            ORDER BY ra.report_time DESC
        '''
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, app_id):
        sql = 'SELECT * FROM reissue_applications WHERE id = %s'
        result = query_one(sql, (app_id,))
        return dict(result) if result else None

    @classmethod
    def get_by_issue_record_id(cls, issue_record_id):
        sql = 'SELECT * FROM reissue_applications WHERE issue_record_id = %s'
        result = query_one(sql, (issue_record_id,))
        return dict(result) if result else None

    @classmethod
    def count_pending(cls):
        sql = "SELECT COUNT(*) as cnt FROM reissue_applications WHERE review_status = 'pending'"
        result = query_one(sql)
        return int(result['cnt']) if result else 0

    @classmethod
    def create(cls, issue_record_id, report_time, reported_by, loss_description=''):
        sql = '''
            INSERT INTO reissue_applications 
            (issue_record_id, report_time, reported_by, loss_description)
            VALUES (%s, %s, %s, %s)
        '''
        return execute(sql, (issue_record_id, report_time, reported_by, loss_description))

    @classmethod
    def review(cls, app_id, review_status, review_time, reviewer_id, review_comment='',
               is_responsible=True, new_wristband_id=None):
        sql = '''
            UPDATE reissue_applications 
            SET review_status=%s, review_time=%s, reviewer_id=%s, review_comment=%s,
                is_responsible=%s, new_wristband_id=%s
            WHERE id=%s
        '''
        return execute(sql, (review_status, review_time, reviewer_id, review_comment,
                           is_responsible, new_wristband_id, app_id))

    @classmethod
    def update(cls, app_id, **kwargs):
        return super().update(app_id, **kwargs)

    @classmethod
    def delete(cls, app_id):
        return super().delete(app_id)
