from app.database import query, query_one, execute


class BaseRepository:
    table_name = ''
    primary_key = 'id'

    @classmethod
    def get_by_id(cls, id):
        sql = f'SELECT * FROM {cls.table_name} WHERE {cls.primary_key} = %s'
        result = query_one(sql, (id,))
        return dict(result) if result else None

    @classmethod
    def list_all(cls, order_by=None):
        sql = f'SELECT * FROM {cls.table_name}'
        if order_by:
            sql += f' ORDER BY {order_by}'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def create(cls, **kwargs):
        if not kwargs:
            return None
        columns = ', '.join(kwargs.keys())
        placeholders = ', '.join(['%s'] * len(kwargs))
        values = list(kwargs.values())
        sql = f'INSERT INTO {cls.table_name} ({columns}) VALUES ({placeholders})'
        return execute(sql, values)

    @classmethod
    def update(cls, id, **kwargs):
        if not kwargs:
            return None
        set_clause = ', '.join([f'{k} = %s' for k in kwargs.keys()])
        values = list(kwargs.values()) + [id]
        sql = f'UPDATE {cls.table_name} SET {set_clause} WHERE {cls.primary_key} = %s'
        return execute(sql, values)

    @classmethod
    def delete(cls, id):
        sql = f'DELETE FROM {cls.table_name} WHERE {cls.primary_key} = %s'
        return execute(sql, (id,))

    @classmethod
    def count(cls, where_sql='', params=None):
        sql = f'SELECT COUNT(*) as cnt FROM {cls.table_name}'
        if where_sql:
            sql += f' WHERE {where_sql}'
        result = query_one(sql, params or ())
        return int(result['cnt']) if result and result['cnt'] else 0

    @classmethod
    def exists(cls, where_sql, params=None):
        sql = f'SELECT 1 FROM {cls.table_name} WHERE {where_sql} LIMIT 1'
        result = query_one(sql, params or ())
        return result is not None
