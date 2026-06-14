from app.database import query, query_one, execute
from .base import BaseRepository


class MemberTransactionRepository(BaseRepository):
    table_name = 'member_transactions'

    @classmethod
    def get_by_member(cls, member_id, limit=50):
        sql = '''
            SELECT mt.*, u.full_name as operator_name
            FROM member_transactions mt
            LEFT JOIN users u ON mt.operator_id = u.id
            WHERE mt.member_id = %s
            ORDER BY mt.created_at DESC LIMIT %s
        '''
        results = query(sql, (member_id, int(limit)))
        return [dict(r) for r in results] if results else []

    @classmethod
    def count_by_type_and_date(cls, transaction_type, date_str):
        if isinstance(transaction_type, list):
            placeholders = ','.join(['%s'] * len(transaction_type))
            sql = f"SELECT COUNT(*) as cnt FROM member_transactions WHERE transaction_type IN ({placeholders}) AND DATE(created_at) = %s"
            params = transaction_type + [date_str]
            result = query_one(sql, params)
            return int(result['cnt']) if result else 0
        sql = "SELECT COUNT(*) as cnt FROM member_transactions WHERE transaction_type = %s AND DATE(created_at) = %s"
        result = query_one(sql, (transaction_type, date_str))
        return int(result['cnt']) if result else 0

    @classmethod
    def sum_by_type_and_date(cls, transaction_type, date_str):
        sql = "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = %s AND DATE(created_at) = %s"
        result = query_one(sql, (transaction_type, date_str))
        return float(result['total']) if result and result['total'] else 0.0

    @classmethod
    def get_topup_stats(cls, member_id, since):
        sql = '''
            SELECT member_id, SUM(amount) as total_topup, COUNT(*) as topup_count
            FROM member_transactions
            WHERE transaction_type = 'topup' AND created_at >= %s
            GROUP BY member_id
            HAVING SUM(amount) >= %s OR COUNT(*) >= 5
        '''
        results = query(sql, (since, 5000.00))
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_consume_stats(cls, member_id, since):
        sql = '''
            SELECT member_id, SUM(amount) as total_consume, COUNT(*) as consume_count
            FROM member_transactions
            WHERE transaction_type IN ('consumption', 'package_deduction') AND created_at >= %s
            GROUP BY member_id
            HAVING SUM(amount) >= %s OR COUNT(*) >= 10
        '''
        results = query(sql, (since, 3000.00))
        return [dict(r) for r in results] if results else []

    @classmethod
    def create(cls, member_id, transaction_type, amount, balance_after, operator_id, remark, issue_record_id=None, package_purchase_id=None):
        sql = '''
            INSERT INTO member_transactions (member_id, transaction_type, amount, balance_after,
                                         issue_record_id, operator_id, remark, package_purchase_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (member_id, transaction_type, float(amount),
                          float(balance_after), issue_record_id, operator_id,
                          remark, package_purchase_id))

    @classmethod
    def list_all(cls):
        return super().list_all('created_at DESC')
