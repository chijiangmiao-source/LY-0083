from app.database import query, query_one, execute
from .base import BaseRepository


class StoreRepository(BaseRepository):
    table_name = 'stores'

    @classmethod
    def list_all(cls):
        sql = 'SELECT * FROM stores ORDER BY is_headquarters DESC, id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def list_active(cls):
        sql = 'SELECT * FROM stores WHERE is_active = TRUE ORDER BY is_headquarters DESC, id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, store_id):
        sql = 'SELECT * FROM stores WHERE id = %s'
        result = query_one(sql, (store_id,))
        return dict(result) if result else None

    @classmethod
    def get_by_store_code(cls, store_code):
        sql = 'SELECT * FROM stores WHERE store_code = %s'
        result = query_one(sql, (store_code,))
        return dict(result) if result else None

    @classmethod
    def get_headquarters(cls):
        sql = 'SELECT id FROM stores WHERE is_headquarters = TRUE LIMIT 1'
        result = query_one(sql)
        return dict(result) if result else None

    @classmethod
    def get_stats(cls, store_id, date_str):
        def safe_count(sql, *params):
            try:
                r = query_one(sql, params)
                return int(r['cnt']) if r else 0
            except Exception:
                return 0

        def safe_sum(sql, *params):
            try:
                r = query_one(sql, params)
                return float(r['total']) if r and r['total'] else 0.0
            except Exception:
                return 0.0

        stats = {
            'today_local_income': safe_sum('''
                SELECT SUM(base_fee + extra_fee + loss_fee + reissue_fee) as total
                FROM issue_records WHERE store_id = %s AND fee_status = 'settled' AND DATE(issue_time) = %s
            ''', store_id, date_str),
            'today_cross_store_income': safe_sum('''
                SELECT COALESCE(SUM(amount), 0) as total FROM clearing_records
                WHERE store_id = %s AND amount_type = 'target_income' AND status = 'settled'
                  AND DATE(settled_at) = %s
            ''', store_id, date_str),
            'today_cross_store_deduction': safe_sum('''
                SELECT COALESCE(SUM(deduction_amount), 0) as total FROM cross_store_records
                WHERE consume_store_id = %s AND DATE(created_at) = %s
            ''', store_id, date_str),
            'pending_clearing': safe_sum('''
                SELECT COALESCE(SUM(amount), 0) as total FROM clearing_records
                WHERE store_id = %s AND status = 'pending'
            ''', store_id),
            'hq_subsidy_total': safe_sum('''
                SELECT COALESCE(SUM(amount), 0) as total FROM clearing_records
                WHERE store_id = %s AND amount_type = 'hq_subsidy' AND status = 'settled'
            ''', store_id),
            'total_members_home': safe_count('''
                SELECT COUNT(*) as cnt FROM members WHERE home_store_id = %s AND status = 'active'
            ''', store_id),
            'today_cross_store_visits': safe_count('''
                SELECT COUNT(*) as cnt FROM cross_store_records
                WHERE consume_store_id = %s AND DATE(created_at) = %s
            ''', store_id, date_str),
        }
        return stats

    @classmethod
    def create(cls, store_code, name, address='', contact_phone='', manager_name='', is_headquarters=False):
        sql = '''
            INSERT INTO stores (store_code, name, address, contact_phone, manager_name, is_headquarters)
            VALUES (%s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (store_code, name, address, contact_phone, manager_name, is_headquarters))

    @classmethod
    def update(cls, store_id, **kwargs):
        return super().update(store_id, **kwargs)

    @classmethod
    def has_bath_areas(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM bath_areas WHERE store_id = %s"
        result = query_one(sql, (store_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_wristbands(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM wristbands WHERE store_id = %s"
        result = query_one(sql, (store_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_users(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM users WHERE store_id = %s"
        result = query_one(sql, (store_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_issue_records(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM issue_records WHERE store_id = %s"
        result = query_one(sql, (store_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_shift_records(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM shift_records WHERE store_id = %s"
        result = query_one(sql, (store_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_members(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM members WHERE home_store_id = %s"
        result = query_one(sql, (store_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_cross_store_records(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM cross_store_records WHERE home_store_id = %s OR consume_store_id = %s"
        result = query_one(sql, (store_id, store_id))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_clearing_records(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM clearing_records WHERE store_id = %s"
        result = query_one(sql, (store_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def has_clearing_rules(cls, store_id):
        sql = "SELECT COUNT(*) as cnt FROM store_clearing_rules WHERE source_store_id = %s OR target_store_id = %s"
        result = query_one(sql, (store_id, store_id))
        return result['cnt'] > 0 if result else False

    @classmethod
    def get_related_data_count(cls, store_id):
        counts = {}
        checks = [
            ('bath_areas', "SELECT COUNT(*) as cnt FROM bath_areas WHERE store_id = %s"),
            ('wristbands', "SELECT COUNT(*) as cnt FROM wristbands WHERE store_id = %s"),
            ('users', "SELECT COUNT(*) as cnt FROM users WHERE store_id = %s"),
            ('issue_records', "SELECT COUNT(*) as cnt FROM issue_records WHERE store_id = %s"),
            ('shift_records', "SELECT COUNT(*) as cnt FROM shift_records WHERE store_id = %s"),
            ('members', "SELECT COUNT(*) as cnt FROM members WHERE home_store_id = %s"),
            ('cross_store_records', "SELECT COUNT(*) as cnt FROM cross_store_records WHERE home_store_id = %s OR consume_store_id = %s"),
            ('clearing_records', "SELECT COUNT(*) as cnt FROM clearing_records WHERE store_id = %s"),
            ('clearing_rules', "SELECT COUNT(*) as cnt FROM store_clearing_rules WHERE source_store_id = %s OR target_store_id = %s"),
        ]
        for name, sql in checks:
            params = (store_id, store_id) if 'OR' in sql else (store_id,)
            result = query_one(sql, params)
            counts[name] = int(result['cnt']) if result else 0
        return counts

    @classmethod
    def delete(cls, store_id):
        return super().delete(store_id)
