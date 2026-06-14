from app.database import query, query_one, execute
from .base import BaseRepository


class MemberUpgradeLogRepository(BaseRepository):
    table_name = 'member_level_upgrade_logs'

    @classmethod
    def get_by_member(cls, member_id):
        sql = '''
            SELECT mul.*, ml1.name as old_level_name, ml2.name as new_level_name,
                   u.full_name as operator_name
            FROM member_level_upgrade_logs mul
            LEFT JOIN member_levels ml1 ON mul.old_level_id = ml1.id
            LEFT JOIN member_levels ml2 ON mul.new_level_id = ml2.id
            LEFT JOIN users u ON mul.operator_id = u.id
            WHERE mul.member_id = %s
            ORDER BY mul.created_at DESC
        '''
        results = query(sql, (member_id,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def create(cls, member_id, old_level_id, new_level_id, trigger_type, operator_id, remark=''):
        sql = '''
            INSERT INTO member_level_upgrade_logs (member_id, old_level_id, new_level_id,
                                                trigger_type, operator_id, remark)
            VALUES (%s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (member_id, old_level_id, new_level_id, trigger_type, operator_id, remark))

    @classmethod
    def list_all(cls):
        return super().list_all('created_at DESC')
