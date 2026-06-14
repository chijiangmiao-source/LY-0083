from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response, to_template_json
from app.services import BathAreaService, WristbandService, IssueService


def register_issue_routes(app):

    @app.route('/issue')
    @require_login
    def issue_page():
        user = get_session_user()
        areas = BathAreaService.list_active()
        return template('templates/issue.html', user=user, areas_json=to_template_json(areas))

    @app.route('/api/issue/available-bands', method='GET')
    @require_login
    def api_available_bands():
        area_id = request.query.get('area_id', '')
        bands = WristbandService.get_available_bands(area_id=area_id)
        return json_response(bands)

    @app.route('/api/issue/check-phone', method='GET')
    @require_login
    def api_check_phone():
        phone = request.query.get('phone', '')
        if not phone:
            return json_response({'can_issue': True})
        has_issue, records = WristbandService.phone_has_unsettled_loss(phone)
        return json_response({'can_issue': not has_issue, 'records': records})

    @app.route('/api/issue', method='POST')
    @require_login
    def api_issue_band():
        data = request.json
        user = get_session_user()

        try:
            result = IssueService.issue_band(
                wristband_id=data.get('wristband_id'),
                customer_name=data.get('customer_name', ''),
                phone=data.get('phone', ''),
                operator_id=user['id'],
            )
            return json_response(result, True, '发牌成功')
        except ValueError as e:
            return json_response(None, False, str(e))
