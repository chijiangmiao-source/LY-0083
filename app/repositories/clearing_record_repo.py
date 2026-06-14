from app.database import query, query_one, execute
from .base import BaseRepository


class ClearingRecordRepository(BaseRepository):
    table_name = 'clearing_records'

    @classmethod
    def list(cls, store_id=None, status='', limit=200):
        sql = '''
            SELECT cr.*, csr.member_id, csr.operation_type, csr.deduction_amount,
                   m.name as member_name, s.name as store_name
            FROM clearing_records cr
            LEFT JOIN cross_store_records csr ON cr.cross_store_record_id = csr.id
            LEFT JOIN members m ON csr.member_id = m.id
            LEFT JOIN stores s ON cr.store_id = s.id
            WHERE 1=1
        '''
        params = []
        if store_id:
            sql += " AND cr.store_id = %s"
            params.append(int(store_id))
        if status:
            sql += " AND cr.status = %s"
            params.append(status)
        sql += " ORDER BY cr.created_at DESC LIMIT %s"
        try:
            params.append(int(limit))
        except ValueError:
            params.append(200)
        results = query(sql, params)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, record_id):
        sql = 'SELECT * FROM clearing_records WHERE id = %s'
        result = query_one(sql, (record_id,))
        return dict(result) if result else None

    @classmethod
    def get_by_cross_store_record(cls, cross_store_record_id, status=None):
        sql = 'SELECT * FROM clearing_records WHERE cross_store_record_id = %s'
        params = [cross_store_record_id]
        if status:
            sql += " AND status = %s"
            params.append(status)
        results = query(sql, params)
        return [dict(r) for r in results] if results else []

    @classmethod
    def sum_by_store_and_status(cls, store_id, status='pending', amount_type=None):
        sql = 'SELECT COALESCE(SUM(amount), 0) as total FROM clearing_records WHERE store_id = %s AND status = %s'
        params = [store_id, status]
        if amount_type:
            sql += " AND amount_type = %s"
            params.append(amount_type)
        result = query_one(sql, params)
        return float(result['total']) if result and result['total'] else 0.0

    @classmethod
    def sum_income_by_store_and_date(cls, store_id, date_str):
        sql = '''
            SELECT COALESCE(SUM(amount), 0) as total FROM clearing_records
            WHERE store_id = %s AND amount_type = 'target_income' AND status = 'settled'
              AND DATE(settled_at) = %s
        '''
        result = query_one(sql, (store_id, date_str))
        return float(result['total']) if result and result['total'] else 0.0

    @classmethod
    def create(cls, cross_store_record_id, store_id, amount_type, amount, status='pending'):
        sql = '''
            INSERT INTO clearing_records (cross_store_record_id, store_id, amount_type, amount, status)
            VALUES (%s, %s, %s, %s, %s)
        '''
        return execute(sql, (cross_store_record_id, store_id, amount_type, float(amount), status))

    @classmethod
    def mark_settled(cls, record_id, settled_at):
        sql = '''
            UPDATE clearing_records SET status = 'settled', settled_at = %s
            WHERE id = %s
        '''
        return execute(sql, (settled_at, record_id))

    @classmethod
    def mark_settled_by_cross_store(cls, cross_store_record_id, settled_at):
        sql = '''
            UPDATE clearing_records SET status = 'settled', settled_at = %s
            WHERE cross_store_record_id = %s AND status = 'pending'
        '''
        return execute(sql, (settled_at, cross_store_record_id))

    @classmethod
    def list_all(cls):
        return super().list_all('created_at DESC')

    @classmethod
    def update(cls, record_id, **kwargs):
        return super().update(record_id, **kwargs)

    @classmethod
    def delete(cls, record_id):
        return super().delete(record_id)
