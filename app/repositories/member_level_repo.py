from app.database import query, query_one, execute
from .base import BaseRepository


class MemberLevelRepository(BaseRepository):
    table_name = 'member_levels'

    @classmethod
    def list_active(cls):
        sql = 'SELECT * FROM member_levels WHERE is_active = TRUE ORDER BY id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def list_all(cls):
        sql = 'SELECT * FROM member_levels ORDER BY id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, level_id):
        return super().get_by_id(level_id)

    @classmethod
    def get_for_upgrade(cls, current_level_id, total_top_up):
        sql = '''
            SELECT * FROM member_levels
            WHERE is_active = TRUE AND id != %s
            ORDER BY min_top_up DESC
        '''
        results = query(sql, (current_level_id,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def create(cls, name, discount_rate, deposit_discount_rate, loss_fee_discount_rate,
               reissue_fee_discount_rate, min_top_up=0, description=''):
        sql = '''
            INSERT INTO member_levels (name, discount_rate, deposit_discount_rate,
                                     loss_fee_discount_rate, reissue_fee_discount_rate,
                                     min_top_up, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (name, float(discount_rate), float(deposit_discount_rate),
                          float(loss_fee_discount_rate), float(reissue_fee_discount_rate),
                          float(min_top_up), description))

    @classmethod
    def update(cls, level_id, **kwargs):
        return super().update(level_id, **kwargs)

    @classmethod
    def delete(cls, level_id):
        return super().delete(level_id)
