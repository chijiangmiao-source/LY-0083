from app.database import query, query_one, execute
from .base import BaseRepository


class WristbandRepository(BaseRepository):
    table_name = 'wristbands'

    @classmethod
    def list(cls, status='', area_id=None):
        sql = '''SELECT w.*, ba.name as bath_area_name FROM wristbands w 
                 LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id WHERE 1=1'''
        params = []
        if status:
            sql += " AND w.current_status = %s"
            params.append(status)
        if area_id:
            sql += " AND w.bath_area_id = %s"
            params.append(int(area_id))
        sql += ' ORDER BY w.id DESC'
        results = query(sql, params)
        return [dict(r) for r in results] if results else []

    @classmethod
    def list_available(cls, area_id=None):
        sql = '''SELECT w.*, ba.name as bath_area_name, ba.base_price, ba.deposit_amount 
                 FROM wristbands w LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id 
                 WHERE w.current_status = 'available' '''
        params = []
        if area_id:
            sql += " AND w.bath_area_id = %s"
            params.append(int(area_id))
        sql += ' ORDER BY w.wristband_no'
        results = query(sql, params)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_wristband_no(cls, wristband_no):
        sql = 'SELECT * FROM wristbands WHERE wristband_no = %s'
        result = query_one(sql, (wristband_no,))
        return dict(result) if result else None

    @classmethod
    def get_by_id(cls, band_id):
        sql = 'SELECT * FROM wristbands WHERE id = %s'
        result = query_one(sql, (band_id,))
        return dict(result) if result else None

    @classmethod
    def count_by_status(cls, status):
        sql = "SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = %s"
        result = query_one(sql, (status,))
        return int(result['cnt']) if result else 0

    @classmethod
    def create(cls, wristband_no, bath_area_id=None):
        sql = '''
            INSERT INTO wristbands (wristband_no, bath_area_id, current_status)
            VALUES (%s, %s, 'available')
        '''
        return execute(sql, (wristband_no, bath_area_id))

    @classmethod
    def update_bath_area(cls, band_id, bath_area_id):
        sql = "UPDATE wristbands SET bath_area_id=%s WHERE id=%s"
        return execute(sql, (bath_area_id, band_id))

    @classmethod
    def update_status(cls, band_id, status, deposit_status=None):
        sql = "UPDATE wristbands SET current_status = %s"
        params = [status]
        if deposit_status is not None:
            sql += ", deposit_status = %s"
            params.append(deposit_status)
        sql += " WHERE id = %s"
        params.append(band_id)
        return execute(sql, params)

    @classmethod
    def update_status_and_issued_time(cls, band_id, status, last_issued_at):
        sql = '''
            UPDATE wristbands SET current_status = %s, last_issued_at = %s WHERE id = %s
        '''
        return execute(sql, (status, last_issued_at, band_id))

    @classmethod
    def has_bands_in_area(cls, area_id):
        sql = "SELECT COUNT(*) as cnt FROM wristbands WHERE bath_area_id = %s"
        result = query_one(sql, (area_id,))
        return result['cnt'] > 0 if result else False

    @classmethod
    def delete(cls, band_id):
        return super().delete(band_id)
