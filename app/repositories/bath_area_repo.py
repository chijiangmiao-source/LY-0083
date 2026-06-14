from app.database import query, query_one, execute
from .base import BaseRepository


class BathAreaRepository(BaseRepository):
    table_name = 'bath_areas'

    @classmethod
    def list_all(cls):
        sql = 'SELECT * FROM bath_areas ORDER BY id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def list_active(cls):
        sql = 'SELECT * FROM bath_areas WHERE is_active = TRUE ORDER BY id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, area_id):
        sql = 'SELECT * FROM bath_areas WHERE id = %s'
        result = query_one(sql, (area_id,))
        return dict(result) if result else None

    @classmethod
    def get_name_by_id(cls, area_id):
        sql = 'SELECT name FROM bath_areas WHERE id = %s'
        result = query_one(sql, (area_id,))
        return result['name'] if result else None

    @classmethod
    def create(cls, name, description='', base_price=0.0, deposit_amount=0.0):
        sql = '''
            INSERT INTO bath_areas (name, description, base_price, deposit_amount)
            VALUES (%s, %s, %s, %s)
        '''
        return execute(sql, (name, description, float(base_price), float(deposit_amount)))

    @classmethod
    def update(cls, area_id, **kwargs):
        return super().update(area_id, **kwargs)

    @classmethod
    def has_bands(cls, area_id):
        sql = "SELECT COUNT(*) as cnt FROM wristbands WHERE bath_area_id = %s"
        result = query_one(sql, (area_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def delete(cls, area_id):
        return super().delete(area_id)
