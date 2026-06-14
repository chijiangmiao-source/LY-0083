from app.database import query, query_one, execute, execute_and_return_id
from .base import BaseRepository


class CrossStoreRepository(BaseRepository):
    table_name = 'cross_store_records'

    @classmethod
    def list(cls, status='', store_id=None, start_date='', end_date='', limit=100):
        sql = '''
            SELECT csr.*, m.name as member_name, m.phone as member_phone, m.member_no,
                   s1.name as home_store_name, s2.name as consume_store_name,
                   scr.name as rule_name, u.full_name as operator_name
            FROM cross_store_records csr
            LEFT JOIN members m ON csr.member_id = m.id
            LEFT JOIN stores s1 ON csr.home_store_id = s1.id
            LEFT JOIN stores s2 ON csr.consume_store_id = s2.id
            LEFT JOIN store_clearing_rules scr ON csr.clearing_rule_id = scr.id
            LEFT JOIN users u ON csr.operator_id = u.id
            WHERE 1=1
        '''
        params = []
        if status:
            sql += " AND csr.clearing_status = %s"
            params.append(status)
        if store_id:
            sql += " AND (csr.home_store_id = %s OR csr.consume_store_id = %s)"
            params.extend([int(store_id), int(store_id)])
        if start_date:
            sql += " AND csr.created_at >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND csr.created_at <= %s"
            params.append(end_date + ' 23:59:59')
        sql += " ORDER BY csr.created_at DESC LIMIT %s"
        try:
            params.append(int(limit))
        except ValueError:
            params.append(100)
        results = query(sql, params)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, record_id):
        sql = 'SELECT * FROM cross_store_records WHERE id = %s'
        result = query_one(sql, (record_id,))
        return dict(result) if result else None

    @classmethod
    def get_outgoing_stats(cls, store_id, start_date='', end_date=''):
        params = [store_id]
        date_filter = ''
        if start_date:
            date_filter += " AND csr.created_at >= %s"
            params.append(start_date)
        if end_date:
            date_filter += " AND csr.created_at <= %s"
            params.append(end_date + ' 23:59:59')
        sql = f'''
            SELECT COUNT(*) as cnt, COALESCE(SUM(deduction_amount), 0) as total_deduction
            FROM cross_store_records csr
            WHERE csr.home_store_id = %s AND csr.clearing_status = 'pending' {date_filter}
        '''
        result = query_one(sql, params)
        return {
            'count': int(result['cnt']) if result else 0,
            'total': float(result['total_deduction']) if result else 0.0,
        }

    @classmethod
    def get_incoming_stats(cls, store_id, start_date='', end_date=''):
        params = [store_id]
        date_filter = ''
        if start_date:
            date_filter += " AND csr.created_at >= %s"
            params.append(start_date)
        if end_date:
            date_filter += " AND csr.created_at <= %s"
            params.append(end_date + ' 23:59:59')
        sql = f'''
            SELECT COUNT(*) as cnt, COALESCE(SUM(deduction_amount), 0) as total_deduction
            FROM cross_store_records csr
            WHERE csr.consume_store_id = %s {date_filter}
        '''
        result = query_one(sql, params)
        return {
            'count': int(result['cnt']) if result else 0,
            'total': float(result['total_deduction']) if result else 0.0,
        }

    @classmethod
    def get_cross_store_discount_anomaly(cls, since):
        sql = '''
            SELECT csr.member_id, m.name as member_name, m.phone, m.level_id,
                   ml.name as level_name, COUNT(*) as cross_count,
                   SUM(csr.deduction_amount) as total_deduction
            FROM cross_store_records csr
            LEFT JOIN members m ON csr.member_id = m.id
            LEFT JOIN member_levels ml ON m.level_id = ml.id
            WHERE csr.created_at >= %s
            GROUP BY csr.member_id, m.name, m.phone, m.level_id, ml.name
            HAVING COUNT(*) >= 5 OR SUM(csr.deduction_amount) >= 3000
        '''
        results = query(sql, (since,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def sum_deduction_by_store_and_date(cls, consume_store_id, date_str):
        sql = '''
            SELECT COALESCE(SUM(deduction_amount), 0) as total FROM cross_store_records
            WHERE consume_store_id = %s AND DATE(created_at) = %s
        '''
        result = query_one(sql, (consume_store_id, date_str))
        return float(result['total']) if result and result['total'] else 0.0

    @classmethod
    def count_visits_by_store_and_date(cls, consume_store_id, date_str):
        sql = '''
            SELECT COUNT(*) as cnt FROM cross_store_records
            WHERE consume_store_id = %s AND DATE(created_at) = %s
        '''
        result = query_one(sql, (consume_store_id, date_str))
        return int(result['cnt']) if result else 0

    @classmethod
    def create(cls, member_id, issue_record_id, home_store_id, consume_store_id,
               operation_type, original_amount, deduction_amount,
               clearing_rule_id=None, operator_id=None, remark=''):
        sql = '''
            INSERT INTO cross_store_records
            (member_id, issue_record_id, home_store_id, consume_store_id,
             operation_type, original_amount, deduction_amount,
             clearing_rule_id, operator_id, remark)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        '''
        return execute_and_return_id(sql, (member_id, issue_record_id, home_store_id, consume_store_id,
                                         operation_type, original_amount, deduction_amount,
                                         clearing_rule_id, operator_id, remark))

    @classmethod
    def process_clearing(cls, cross_store_record_id):
        record = query_one("SELECT * FROM cross_store_records WHERE id = %s", (cross_store_record_id,))
        if not record:
            return False
        if record['clearing_status'] != 'pending':
            return False
        from datetime import datetime
        clearings = query('''
            SELECT * FROM clearing_records WHERE cross_store_record_id = %s AND status = 'pending'
        ''', (cross_store_record_id,))
        for c in clearings:
            execute('''
                UPDATE clearing_records SET status = 'settled', settled_at = %s
                WHERE id = %s
            ''', (datetime.now(), c['id']))
        execute('''
            UPDATE cross_store_records SET clearing_status = 'settled', settled_at = %s
            WHERE id = %s
        ''', (datetime.now(), cross_store_record_id))
        return True

    @classmethod
    def list_all(cls):
        return super().list_all('created_at DESC')

    @classmethod
    def update(cls, record_id, **kwargs):
        return super().update(record_id, **kwargs)

    @classmethod
    def delete(cls, record_id):
        return super().delete(record_id)
