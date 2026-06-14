from app.database import query, query_one, execute
from .base import BaseRepository


class ClearingRuleRepository(BaseRepository):
    table_name = 'store_clearing_rules'

    @classmethod
    def list_all(cls):
        sql = '''
            SELECT scr.*, s1.name as source_store_name, s2.name as target_store_name
            FROM store_clearing_rules scr
            LEFT JOIN stores s1 ON scr.source_store_id = s1.id
            LEFT JOIN stores s2 ON scr.target_store_id = s2.id
            ORDER BY scr.priority DESC, scr.id
        '''
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, rule_id):
        sql = 'SELECT * FROM store_clearing_rules WHERE id = %s'
        result = query_one(sql, (rule_id,))
        return dict(result) if result else None

    @classmethod
    def get_clearing_rule(cls, home_store_id, consume_store_id, member_level_id=None):
        sql = '''
            SELECT * FROM store_clearing_rules
            WHERE is_active = TRUE AND source_store_id = %s AND target_store_id = %s
            ORDER BY priority DESC
        '''
        rules = query(sql, (home_store_id, consume_store_id))
        for r in rules:
            r = dict(r)
            applicable_ids = r.get('applicable_level_ids') or []
            if not applicable_ids or (member_level_id and member_level_id in applicable_ids):
                return r
        sql2 = '''
            SELECT * FROM store_clearing_rules
            WHERE is_active = TRUE AND source_store_id = %s AND target_store_id IS NULL
            ORDER BY priority DESC
        '''
        rules2 = query(sql2, (home_store_id,))
        for r in rules2:
            r = dict(r)
            applicable_ids = r.get('applicable_level_ids') or []
            if not applicable_ids or (member_level_id and member_level_id in applicable_ids):
                return r
        return None

    @classmethod
    def create(cls, name, rule_type, source_store_id, target_store_id,
               source_ratio=50, target_ratio=50, hq_subsidy_ratio=0, hq_subsidy_max=0,
               applicable_level_ids=None, priority=0, description=''):
        sql = '''
            INSERT INTO store_clearing_rules
            (name, rule_type, source_store_id, target_store_id,
             source_ratio, target_ratio, hq_subsidy_ratio, hq_subsidy_max,
             applicable_level_ids, priority, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (name, rule_type, source_store_id, target_store_id,
                          float(source_ratio or 50), float(target_ratio or 50),
                          float(hq_subsidy_ratio or 0), float(hq_subsidy_max or 0),
                          applicable_level_ids or [], int(priority or 0), description))

    @classmethod
    def update(cls, rule_id, **kwargs):
        return super().update(rule_id, **kwargs)

    @classmethod
    def delete(cls, rule_id):
        return super().delete(rule_id)
