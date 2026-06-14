from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response
from app.services import (
    run_all_warning_checks,
    get_unread_warning_stats,
    list_warnings,
    mark_read,
    mark_all_read,
    resolve_warning,
    delete_warning,
    get_warning_types,
)


def register_warning_routes(app):

    @app.route('/warnings')
    @require_login
    def warnings_page():
        user = get_session_user()
        return template('templates/warnings.html', user=user)

    @app.route('/api/warnings/stats', method='GET')
    @require_login
    def api_warnings_stats():
        try:
            run_all_warning_checks()
            stats = get_unread_warning_stats()
            return json_response(stats)
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/warnings', method='GET')
    @require_login
    def api_warnings_list():
        try:
            warning_type = request.query.get('type', '')
            level = request.query.get('level', '')
            is_read = request.query.get('is_read', '')
            is_resolved = request.query.get('is_resolved', '')
            limit = request.query.get('limit', '100')
            rows = list_warnings(
                warning_type=warning_type,
                level=level,
                is_read=is_read,
                is_resolved=is_resolved,
                limit=limit,
            )
            return json_response(rows)
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/warnings/refresh', method='POST')
    @require_login
    def api_warnings_refresh():
        try:
            run_all_warning_checks()
            return json_response({'status': 'ok'}, True, '预警检测完成')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/warnings/<warning_id:int>/read', method='POST')
    @require_login
    def api_warning_mark_read(warning_id):
        try:
            user = get_session_user()
            mark_read(warning_id, user['id'])
            return json_response(None, True, '已标记为已读')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/warnings/read-all', method='POST')
    @require_login
    def api_warning_read_all():
        try:
            user = get_session_user()
            mark_all_read(user['id'])
            return json_response(None, True, '已全部标记为已读')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/warnings/<warning_id:int>/resolve', method='POST')
    @require_login
    def api_warning_resolve(warning_id):
        try:
            user = get_session_user()
            data = request.json or {}
            resolve_warning(warning_id, user['id'], data.get('resolve_note', ''))
            return json_response(None, True, '已标记为已解决')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/warnings/<warning_id:int>', method='DELETE')
    @require_login
    def api_warning_delete(warning_id):
        try:
            delete_warning(warning_id)
            return json_response(None, True, '删除成功')
        except ValueError as e:
            return json_response(None, False, str(e))

    @app.route('/api/warnings/types', method='GET')
    @require_login
    def api_warning_types():
        try:
            types = get_warning_types()
            return json_response(types)
        except ValueError as e:
            return json_response(None, False, str(e))
