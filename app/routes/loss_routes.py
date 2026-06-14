from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response
from app.services import LossReissueService


def register_loss_routes(app):

    @app.route('/report-loss')
    @require_login
    def report_loss_page():
        user = get_session_user()
        return template('templates/report_loss.html', user=user)

    @app.route('/api/loss/search', method='GET')
    @require_login
    def api_loss_search():
        keyword = request.query.get('keyword', '').strip()
        records = LossReissueService.search_loss_records(keyword)
        return json_response(records)

    @app.route('/api/loss/report', method='POST')
    @require_login
    def api_report_loss():
        data = request.json
        user = get_session_user()

        try:
            LossReissueService.report_loss(
                issue_record_id=data.get('issue_record_id'),
                loss_description=data.get('loss_description', ''),
                operator_id=user['id'],
            )
            return json_response(None, True, '遗失申报成功，原手牌已冻结')
        except ValueError as e:
            return json_response(None, False, str(e))
