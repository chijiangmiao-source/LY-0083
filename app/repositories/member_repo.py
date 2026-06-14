from app.database import query, query_one, execute
from .base import BaseRepository


class MemberRepository(BaseRepository):
    table_name = 'members'

    @classmethod
    def get_by_phone(cls, phone):
        if not phone:
            return None
        sql = '''
            SELECT m.*, ml.name as level_name, ml.discount_rate, ml.deposit_discount_rate,
                   ml.loss_fee_discount_rate, ml.reissue_fee_discount_rate,
                   COALESCE(m.gift_balance, 0) as gift_balance
            FROM members m
            LEFT JOIN member_levels ml ON m.level_id = ml.id
            WHERE m.phone = %s AND m.status = 'active'
        '''
        result = query_one(sql, (phone,))
        return dict(result) if result else None

    @classmethod
    def get_by_member_no(cls, member_no):
        sql = 'SELECT * FROM members WHERE member_no = %s'
        result = query_one(sql, (member_no,))
        return dict(result) if result else None

    @classmethod
    def get_by_id_with_level(cls, member_id):
        sql = '''
            SELECT m.*, ml.name as level_name, ml.discount_rate
            FROM members m
            LEFT JOIN member_levels ml ON m.level_id = ml.id
            WHERE m.id = %s
        '''
        result = query_one(sql, (member_id,))
        return dict(result) if result else None

    @classmethod
    def list(cls, keyword='', level_id=None, status=''):
        sql = '''
            SELECT m.*, ml.name as level_name, ml.discount_rate
            FROM members m
            LEFT JOIN member_levels ml ON m.level_id = ml.id
            WHERE 1=1
        '''
        params = []
        if keyword:
            sql += " AND (m.name LIKE %s OR m.phone LIKE %s OR m.member_no LIKE %s)"
            like = f'%{keyword}%'
            params.extend([like, like, like])
        if level_id:
            sql += " AND m.level_id = %s"
            params.append(int(level_id))
        if status:
            sql += " AND m.status = %s"
            params.append(status)
        sql += ' ORDER BY m.id DESC'
        results = query(sql, params)
        return [dict(r) for r in results] if results else []

    @classmethod
    def count_by_status(cls, status='active'):
        sql = "SELECT COUNT(*) as cnt FROM members WHERE status = %s"
        result = query_one(sql, (status,))
        return int(result['cnt']) if result else 0

    @classmethod
    def count_by_date(cls, date_str):
        sql = "SELECT COUNT(*) as cnt FROM members WHERE DATE(registered_at) = %s"
        result = query_one(sql, (date_str,))
        return int(result['cnt']) if result else 0

    @classmethod
    def create(cls, member_no, name, phone, gender='', id_card='', level_id=1, remark='',
               home_store_id=None, balance_cross_store_enabled=False):
        sql = '''
            INSERT INTO members (member_no, name, phone, gender, id_card, level_id, remark,
                               home_store_id, balance_cross_store_enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (member_no, name, phone, gender, id_card, level_id, remark,
                          home_store_id, balance_cross_store_enabled))

    @classmethod
    def update(cls, member_id, **kwargs):
        return super().update(member_id, **kwargs)

    @classmethod
    def update_balance(cls, member_id, balance, gift_balance, total_top_up=None, total_gift=None):
        sql = '''
            UPDATE members SET balance = %s, gift_balance = %s, last_active_at = %s
        '''
        params = [balance, gift_balance]
        if total_top_up is not None:
            sql += ', total_top_up = total_top_up + %s'
            params.append(total_top_up)
        if total_gift is not None:
            sql += ', total_gift = total_gift + %s'
            params.append(total_gift)
        from datetime import datetime
        params.append(datetime.now())
        params.append(member_id)
        sql += ' WHERE id = %s'
        return execute(sql, params)

    @classmethod
    def update_level(cls, member_id, level_id):
        sql = "UPDATE members SET level_id = %s WHERE id = %s"
        return execute(sql, (level_id, member_id))

    @classmethod
    def delete(cls, member_id):
        return super().delete(member_id)

    @classmethod
    def get_next_level(cls, total_top_up):
        sql = '''
            SELECT * FROM member_levels WHERE is_active = TRUE AND min_top_up > %s
            ORDER BY min_top_up ASC LIMIT 1
        '''
        result = query_one(sql, (float(total_top_up),))
        return dict(result) if result else None
