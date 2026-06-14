from app.database import query, query_one, execute
from .base import BaseRepository


class TopupBonusRepository(BaseRepository):
    table_name = 'member_topup_bonus_rules'

    @classmethod
    def list_all(cls):
        sql = 'SELECT * FROM member_topup_bonus_rules ORDER BY priority DESC, min_amount ASC'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_bonus_for_topup(cls, level_id, amount):
        sql = '''
            SELECT * FROM member_topup_bonus_rules
            WHERE is_active = TRUE AND min_amount <= %s
            ORDER BY priority DESC, min_amount DESC
        '''
        rules = query(sql, (amount,))
        best_rule = None
        for r in rules:
            r = dict(r)
            applicable_ids = r.get('applicable_level_ids') or []
            if not applicable_ids or level_id in applicable_ids:
                best_rule = r
                break
        if not best_rule:
            return 0.0, None
        bonus = float(best_rule['bonus_amount'] or 0)
        if best_rule['bonus_percent'] and float(best_rule['bonus_percent']) > 0:
            bonus += round(amount * float(best_rule['bonus_percent']) / 100.0, 2)
        return bonus, best_rule

    @classmethod
    def create(cls, name, min_amount, bonus_amount=0, bonus_percent=0,
               applicable_level_ids=None, priority=0, description=''):
        sql = '''
            INSERT INTO member_topup_bonus_rules (name, min_amount, bonus_amount, bonus_percent,
                                                 applicable_level_ids, priority, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (name, float(min_amount), float(bonus_amount or 0),
                          float(bonus_percent or 0), applicable_level_ids or [],
                          int(priority or 0), description))

    @classmethod
    def update(cls, rule_id, **kwargs):
        return super().update(rule_id, **kwargs)

    @classmethod
    def delete(cls, rule_id):
        return super().delete(rule_id)
