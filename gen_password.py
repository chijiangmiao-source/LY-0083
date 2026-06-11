from hashlib import pbkdf2_hmac
from binascii import hexlify
import sys


def hash_password(password, salt='admin'):
    dk = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260000)
    return f'pbkdf2:sha256:260000${salt}${hexlify(dk).decode()}'


if __name__ == '__main__':
    if len(sys.argv) > 1:
        pwd = sys.argv[1]
    else:
        pwd = 'admin123'
    print(f'Password: {pwd}')
    print(f'Hash: {hash_password(pwd)}')
