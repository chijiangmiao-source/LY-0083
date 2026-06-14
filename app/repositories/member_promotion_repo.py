from app.database import query, query_one, execute
from .base import BaseRepository


class MemberPromotionRepository(BaseRepository):
    table_name = 'member_promotions'

    @classmethod
    def list_all(cls):
        sql = 'SELECT * FROM member_promotions ORDER BY id DESC'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_active(cls, level_id=None, promotion_type=None):
        from datetime import datetime
        now = datetime.now()
        sql = '''
            SELECT * FROM member_promotions
            WHERE is_active = TRUE AND start_time <= %s AND end_time >= %s
        '''
        params = [now, now]
        if promotion_type:
            sql += " AND promotion_type = %s"
            params.append(promotion_type)
        rows = query(sql, params)
        result = []
        for p in rows:
            p = dict(p)
            if level_id:
                applicable_ids = p.get('applicable_level_ids') or []
                if applicable_ids and int(level_id) not in applicable_ids:
                    continue
            result.append(p)
        return result

    @classmethod
    def get_active_by_level_and_type(cls, level_id, promotion_type):
        from datetime import datetime
        now = datetime.now()
        sql = '''
            SELECT * FROM member_promotions
            WHERE is_active = TRUE AND start_time <= %s AND end_time >= %s
              AND promotion_type = %s
        '''
        params = [now, now, promotion_type]
        rows = query(sql, params)
        result = []
        for p in rows:
            p = dict(p)
            applicable_ids = p.get('applicable_level_ids') or []
            if not applicable_ids or level_id in applicable_ids:
                result.append(p)
        return result

    @classmethod
    def create(cls, name, promotion_type, discount_rate, applicable_level_ids=None,
               start_time=None, end_time=None, description=''):
        sql = '''
            INSERT INTO member_promotions (name, promotion_type, discount_rate,
                                        applicable_level_ids, start_time, end_time, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (name, promotion_type, float(discount_rate or 100),
                          applicable_level_ids or [], start_time, end_time, description))

    @classmethod
    def update(cls, promo_id, **kwargs):
        return super().update(promo_id, **kwargs)

    @classmethod
    def delete(cls, promo_id):
        return super().delete(promo_id)
