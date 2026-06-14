from app.database import query, query_one, execute
from .base import BaseRepository


class StatusLogRepository(BaseRepository):
    table_name = 'wristband_status_logs'

    @classmethod
    def get_by_wristband(cls, wristband_id):
        sql = '''
            SELECT l.*, u.full_name as operator_name, w.wristband_no
            FROM wristband_status_logs l
            LEFT JOIN users u ON l.operator_id = u.id
            LEFT JOIN wristbands w ON l.wristband_id = w.id
            WHERE l.wristband_id = %s
            ORDER BY l.change_time DESC
        '''
        results = query(sql, (wristband_id,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_issue_record(cls, issue_record_id):
        sql = '''
            SELECT l.*, u.full_name as operator_name, w.wristband_no
            FROM wristband_status_logs l
            LEFT JOIN users u ON l.operator_id = u.id
            LEFT JOIN wristbands w ON l.wristband_id = w.id
            WHERE l.issue_record_id = %s
            ORDER BY l.change_time ASC
        '''
        results = query(sql, (issue_record_id,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, log_id):
        sql = 'SELECT * FROM wristband_status_logs WHERE id = %s'
        result = query_one(sql, (log_id,))
        return dict(result) if result else None

    @classmethod
    def create(cls, wristband_id, new_status, change_reason, old_status=None,
               issue_record_id=None, operator_id=None, phone=None,
               customer_name=None, remark=None, change_time=None):
        if change_time is None:
            from datetime import datetime
            change_time = datetime.now()
        sql = '''
            INSERT INTO wristband_status_logs
            (wristband_id, issue_record_id, old_status, new_status, change_reason,
             operator_id, phone, customer_name, remark, change_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (wristband_id, issue_record_id, old_status, new_status, change_reason,
                           operator_id, phone, customer_name, remark, change_time))

    @classmethod
    def list_all(cls):
        return super().list_all('change_time DESC')

    @classmethod
    def delete(cls, log_id):
        return super().delete(log_id)
