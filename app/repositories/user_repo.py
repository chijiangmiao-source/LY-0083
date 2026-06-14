from app.database import query, query_one, execute
from .base import BaseRepository


class UserRepository(BaseRepository):
    table_name = 'users'

    @classmethod
    def get_by_username(cls, username):
        sql = 'SELECT * FROM users WHERE username = %s'
        result = query_one(sql, (username,))
        return dict(result) if result else None

    @classmethod
    def get_by_id_with_store(cls, user_id):
        sql = 'SELECT id, username, full_name, role, store_id FROM users WHERE id = %s'
        result = query_one(sql, (user_id,))
        return dict(result) if result else None

    @classmethod
    def get_store_id(cls, user_id):
        sql = 'SELECT store_id FROM users WHERE id = %s'
        result = query_one(sql, (user_id,))
        return result['store_id'] if result and result.get('store_id') else None

    @classmethod
    def list_all(cls):
        sql = 'SELECT * FROM users ORDER BY id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def create(cls, username, password_hash, full_name, role='staff'):
        sql = '''INSERT INTO users (username, password_hash, full_name, role)
               VALUES (%s, %s, %s, %s)'''
        return execute(sql, (username, password_hash, full_name, role))

    @classmethod
    def update(cls, user_id, **kwargs):
        return super().update(user_id, **kwargs)

    @classmethod
    def delete(cls, user_id):
        return super().delete(user_id)
