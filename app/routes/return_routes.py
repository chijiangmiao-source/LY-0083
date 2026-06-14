from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response
from app.services import IssueService, ReturnService


def register_return_routes(app):

    @app.route('/return')
    @require_login
    def return_page():
        user = get_session_user()
        return template('templates/return.html', user=user)

    @app.route('/api/return/search', method='GET')
    @require_login
    def api_return_search():
        keyword = request.query.get('keyword', '').strip()
        records = IssueService.search_issue_records(keyword)
        return json_response(records)

    @app.route('/api/return/<record_id:int>', method='POST')
    @require_login
    def api_return_band(record_id):
        data = request.json
        user = get_session_user()

        try:
            result = ReturnService.return_band(
                record_id=record_id,
                operator_id=user['id'],
                extra_fee=data.get('extra_fee', 0),
                loss_fee=data.get('loss_fee', 0),
                reissue_fee=data.get('reissue_fee', 0),
                deposit_status=data.get('deposit_status', 'returned'),
                use_package_id=data.get('use_package_id'),
                use_balance=data.get('use_balance', False),
            )
            return json_response(result, True, '退牌结算成功')
        except ValueError as e:
            return json_response(None, False, str(e))
