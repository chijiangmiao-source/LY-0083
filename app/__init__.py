from bottle import Bottle

from app.config import SECRET_KEY, hash_password, verify_password, DB_CONFIG
from app import services as app_services

app = Bottle()

app.services = app_services
app.SECRET_KEY = SECRET_KEY

from app.routes import register_all_routes

register_all_routes(app)

__all__ = [
    'app',
    'services',
    'SECRET_KEY',
    'hash_password',
    'verify_password',
    'DB_CONFIG',
]

