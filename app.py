import os
import sys
import json
from datetime import datetime, date
from functools import wraps
from hashlib import pbkdf2_hmac
from binascii import hexlify

from bottle import Bottle, request, response, redirect, static_file, template, abort

from app.config import SECRET_KEY, hash_password, verify_password, DB_CONFIG
from app.database import query, query_one, execute, execute_and_return_id

_current_module = sys.modules[__name__]
_current_module.SECRET_KEY = SECRET_KEY
_current_module.hash_password = hash_password
_current_module.verify_password = verify_password
_current_module.query = query
_current_module.query_one = query_one
_current_module.execute = execute
_current_module.execute_and_return_id = execute_and_return_id
_current_module.DB_CONFIG = DB_CONFIG


from app import app as new_app
from app import services as app_services

new_app.TEMPLATE_PATH = ['./templates']

@new_app.error(404)
def new_app_error_404(error):
    return template('templates/404.html') if os.path.exists('templates/404.html') else '404 Not Found'

@new_app.route('/static/<filepath:path>')
def new_app_server_static(filepath):
    return static_file(filepath, root='./static')

new_app.services = app_services

app = new_app
_current_module.app = app


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=8080, debug=True, reloader=True)
