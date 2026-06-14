from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response
from app.services import (
    list_clearing_rules,
    create_clearing_rule,
    update_clearing_rule,
    delete_clearing_rule,
    list_cross_store_records,
    process_cross_store_clearing,
    batch_clearing,
    list_clearing_records,
)


def register_cross_store_routes(app):

    @app.route('/cross-store-report')
    @require_login
    def cross_store_report_page():
        user = get_session_user()
        return template('templates/cross_store_report.html', user=user)

    @app.route('/api/clearing-rules', method='GET')
    @require_login
    def api_clearing_rules_list():
        rows = list_clearing_rules()
        return json_response([dict(r) for r in rows])

    @app.route('/api/clearing-rules', method='POST')
    @require_login
    def api_create_clearing_rule():
        data = request.json
        try:
            create_clearing_rule(data)
            return json_response(None, True, '清分规则创建成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/clearing-rules/<rule_id:int>', method='PUT')
    @require_login
    def api_update_clearing_rule(rule_id):
        data = request.json
        try:
            update_clearing_rule(rule_id, data)
            return json_response(None, True, '清分规则更新成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/clearing-rules/<rule_id:int>', method='DELETE')
    @require_login
    def api_delete_clearing_rule(rule_id):
        try:
            delete_clearing_rule(rule_id)
            return json_response(None, True, '清分规则删除成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/cross-store/records', method='GET')
    @require_login
    def api_cross_store_records():
        status = request.query.get('status', '')
        store_id = request.query.get('store_id', '')
        start_date = request.query.get('start_date', '')
        end_date = request.query.get('end_date', '')
        limit = request.query.get('limit', '100')

        try:
            limit_val = int(limit)
        except ValueError:
            limit_val = 100

        rows = list_cross_store_records(
            status=status,
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit_val,
        )
        return json_response([dict(r) for r in rows])

    @app.route('/api/cross-store/clearing/<record_id:int>', method='POST')
    @require_login
    def api_cross_store_clearing(record_id):
        user = get_session_user()
        success = process_cross_store_clearing(record_id, user['id'])
        if success:
            return json_response(None, True, '清分结算完成')
        return json_response(None, False, '清分结算失败，记录不存在或已结算')

    @app.route('/api/cross-store/batch-clearing', method='POST')
    @require_login
    def api_cross_store_batch_clearing():
        data = request.json
        user = get_session_user()
        record_ids = data.get('record_ids', [])
        success_count = batch_clearing(record_ids, user['id'])
        return json_response({'success_count': success_count, 'total': len(record_ids)},
                             True, f'批量结算完成：{success_count}/{len(record_ids)}条成功')

    @app.route('/api/cross-store/clearing-records', method='GET')
    @require_login
    def api_clearing_records():
        store_id = request.query.get('store_id', '')
        status = request.query.get('status', '')
        rows = list_clearing_records(store_id=store_id, status=status)
        return json_response([dict(r) for r in rows])
