from datetime import datetime

from app.repositories import UserRepository, ShiftRecordRepository
from app.utils.security import verify_password
from app.utils.helpers import generate_shift_no


class AuthService:

    @classmethod
    def login(cls, username, password):
        user = UserRepository.get_by_username(username)
        if not user or not verify_password(password, user['password_hash']):
            return {
                'success': False,
                'message': '用户名或密码错误',
                'data': None
            }

        user_data = {
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'role': user['role']
        }

        operator_id = user['id']
        active_shift = ShiftRecordRepository.get_active_shift(operator_id)
        if not active_shift:
            shift_no = generate_shift_no()
            ShiftRecordRepository.create(shift_no, operator_id, datetime.now())

        return {
            'success': True,
            'message': '登录成功',
            'data': {
                'user': user_data,
                'session_data': {'user_id': user['id']}
            }
        }

    @classmethod
    def logout(cls, user_id):
        active_shift = ShiftRecordRepository.get_active_shift(user_id)
        if active_shift:
            ShiftRecordRepository.close_shift(active_shift['id'], datetime.now())

        return {
            'success': True,
            'message': '登出成功',
            'data': None
        }

    @classmethod
    def get_current_store_id(cls, user):
        if not user:
            return None
        return UserRepository.get_store_id(user['id'])
