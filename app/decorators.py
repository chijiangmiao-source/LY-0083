import json
import logging
from functools import wraps

from bottle import request, redirect

from app.config import SECRET_KEY
from app.database import query_one, transactional
from app.exceptions import BusinessException, ValidationException, NotFoundException
from app.utils.response import json_response

logger = logging.getLogger(__name__)


def get_session_user():
    session = request.get_cookie('session', secret=SECRET_KEY)
    if not session:
        return None
    try:
        data = json.loads(session)
        user = query_one('SELECT id, username, full_name, role FROM users WHERE id = %s', (data['user_id'],))
        return dict(user) if user else None
    except Exception:
        return None


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_session_user()
        if not user:
            redirect('/login')
        return f(*args, **kwargs)
    return wrapper


def handle_errors(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return json_response(None, success=False, message=str(e))
        except ValidationException as e:
            return json_response(None, success=False, message=e.message)
        except NotFoundException as e:
            return json_response(None, success=False, message=e.message)
        except BusinessException as e:
            return json_response(None, success=False, message=e.message)
        except Exception as e:
            logger.exception('服务器内部错误: %s', str(e))
            return json_response(None, success=False, message='服务器内部错误')
    return wrapper


def transactional_route(f):
    @wraps(f)
    @handle_errors
    def wrapper(*args, **kwargs):
        with transactional():
            return f(*args, **kwargs)
    return wrapper
