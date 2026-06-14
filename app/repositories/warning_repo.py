from app.database import query, query_one, execute
from .base import BaseRepository


class WarningRepository(BaseRepository):
    table_name = 'warnings'

    @classmethod
    def list(cls, warning_type='', level='', is_read='', is_resolved='', limit=100):
        sql = '''
            SELECT w.*, u1.full_name as read_by_name, u2.full_name as resolved_by_name,
                   wr.wristband_no, ba.name as bath_area_name
            FROM warnings w
            LEFT JOIN users u1 ON w.read_by = u1.id
            LEFT JOIN users u2 ON w.resolved_by = u2.id
            LEFT JOIN wristbands wr ON w.wristband_id = wr.id
            LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id
            WHERE 1=1
        '''
        params = []
        if warning_type:
            sql += " AND w.warning_type = %s"
            params.append(warning_type)
        if level:
            sql += " AND w.warning_level = %s"
            params.append(level)
        if is_read:
            sql += " AND w.is_read = %s"
            params.append(is_read == 'true')
        if is_resolved:
            sql += " AND w.is_resolved = %s"
            params.append(is_resolved == 'true')
        sql += " ORDER BY w.created_at DESC LIMIT %s"
        try:
            params.append(int(limit))
        except ValueError:
            params.append(100)
        results = query(sql, params)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_recent(cls, limit=20):
        sql = '''
            SELECT w.*, u1.full_name as read_by_name, u2.full_name as resolved_by_name,
                   wr.wristband_no, ba.name as bath_area_name
            FROM warnings w
            LEFT JOIN users u1 ON w.read_by = u1.id
            LEFT JOIN users u2 ON w.resolved_by = u2.id
            LEFT JOIN wristbands wr ON w.wristband_id = wr.id
            LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id
            ORDER BY w.created_at DESC LIMIT %s
        '''
        results = query(sql, (limit,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_issue_record_ids(cls, record_ids):
        if not record_ids:
            return []
        placeholders = ','.join(['%s'] * len(record_ids))
        sql = f'''
            SELECT w.*, wr.wristband_no, ba.name as bath_area_name
            FROM warnings w
            LEFT JOIN wristbands wr ON w.wristband_id = wr.id
            LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id
            WHERE w.issue_record_id IN ({placeholders})
              AND w.issue_record_id IS NOT NULL
            ORDER BY w.created_at DESC
        '''
        results = query(sql, record_ids)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_unread_stats(cls):
        stats = {
            'total_unread': 0,
            'high_count': 0,
            'medium_count': 0,
            'normal_count': 0,
            'unresolved_count': 0
        }
        try:
            total = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE")
            stats['total_unread'] = int(total['cnt']) if total else 0
            high = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE AND warning_level = 'high'")
            stats['high_count'] = int(high['cnt']) if high else 0
            medium = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE AND warning_level = 'medium'")
            stats['medium_count'] = int(medium['cnt']) if medium else 0
            normal = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_read = FALSE AND warning_level = 'normal'")
            stats['normal_count'] = int(normal['cnt']) if normal else 0
            unresolved = query_one("SELECT COUNT(*) as cnt FROM warnings WHERE is_resolved = FALSE")
            stats['unresolved_count'] = int(unresolved['cnt']) if unresolved else 0
        except Exception:
            pass
        return stats

    @classmethod
    def get_by_id(cls, warning_id):
        sql = 'SELECT * FROM warnings WHERE id = %s'
        result = query_one(sql, (warning_id,))
        return dict(result) if result else None

    @classmethod
    def exists_unresolved(cls, warning_type, identifier, identifier_type='phone', since=None):
        sql = f'''
            SELECT id FROM warnings
            WHERE warning_type = %s AND is_resolved = FALSE
              AND {identifier_type} = %s
        '''
        params = [warning_type, identifier]
        if since:
            sql += " AND created_at >= %s"
            params.append(since)
        sql += " LIMIT 1"
        result = query_one(sql, params)
        return result is not None

    @classmethod
    def create(cls, warning_type, title, content, warning_level='normal',
               wristband_id=None, issue_record_id=None, bath_area_id=None,
               phone=None, related_data=None):
        import json
        data_json = json.dumps(related_data, ensure_ascii=False) if related_data else None
        sql = '''
            INSERT INTO warnings
            (warning_type, warning_level, title, content, wristband_id,
             issue_record_id, bath_area_id, phone, related_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (warning_type, warning_level, title, content, wristband_id,
                           issue_record_id, bath_area_id, phone, data_json))

    @classmethod
    def mark_read(cls, warning_id, user_id, read_time):
        sql = '''
            UPDATE warnings SET is_read = TRUE, read_by = %s, read_time = %s
            WHERE id = %s AND is_read = FALSE
        '''
        return execute(sql, (user_id, read_time, warning_id))

    @classmethod
    def mark_all_read(cls, user_id, read_time):
        sql = '''
            UPDATE warnings SET is_read = TRUE, read_by = %s, read_time = %s
            WHERE is_read = FALSE
        '''
        return execute(sql, (user_id, read_time))

    @classmethod
    def mark_resolved(cls, warning_id, user_id, resolved_time, resolve_note=''):
        sql = '''
            UPDATE warnings SET is_resolved = TRUE, resolved_by = %s,
                   resolved_time = %s, resolve_note = %s
            WHERE id = %s AND is_resolved = FALSE
        '''
        return execute(sql, (user_id, resolved_time, resolve_note, warning_id))

    @classmethod
    def count_by_type(cls, warning_type):
        sql = "SELECT COUNT(*) as cnt FROM warnings WHERE warning_type = %s"
        result = query_one(sql, (warning_type,))
        return int(result['cnt']) if result else 0

    @classmethod
    def list_all(cls):
        return super().list_all('created_at DESC')

    @classmethod
    def delete(cls, warning_id):
        return super().delete(warning_id)
