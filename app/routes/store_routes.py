from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response
from app.services import (
    list_stores,
    create_store,
    update_store,
    delete_store,
    get_store_stats,
)


def register_store_routes(app):

    @app.route('/store-management')
    @require_login
    def store_management_page():
        user = get_session_user()
        return template('templates/store_management.html', user=user)

    @app.route('/api/stores', method='GET')
    @require_login
    def api_stores_list():
        rows = list_stores()
        return json_response([dict(r) for r in rows])

    @app.route('/api/stores', method='POST')
    @require_login
    def api_create_store():
        data = request.json
        try:
            create_store(data)
            return json_response(None, True, '门店创建成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/stores/<store_id:int>', method='PUT')
    @require_login
    def api_update_store(store_id):
        data = request.json
        try:
            update_store(store_id, data)
            return json_response(None, True, '门店更新成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/stores/<store_id:int>', method='DELETE')
    @require_login
    def api_delete_store(store_id):
        try:
            delete_store(store_id)
            return json_response(None, True, '门店删除成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/stores/<store_id:int>/stats', method='GET')
    @require_login
    def api_store_stats(store_id):
        stats = get_store_stats(store_id)
        return json_response(stats)
