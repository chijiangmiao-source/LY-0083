import os
import json
from hashlib import pbkdf2_hmac
from binascii import hexlify

SECRET_KEY = 'bathhouse-secret-key-2024'


def hash_password(password, salt='admin'):
    dk = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260000)
    return f'pbkdf2:sha256:260000${salt}${hexlify(dk).decode()}'


def verify_password(password, password_hash):
    parts = password_hash.split('$')
    if len(parts) != 3:
        return False
    _, salt, stored_hash = parts
    dk = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260000)
    return hexlify(dk).decode() == stored_hash


DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'bathhouse'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', 'postgres'),
}
