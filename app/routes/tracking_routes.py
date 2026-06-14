from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response, to_template_json
from app.services import WristbandService, BathAreaService


def register_tracking_routes(app):

    @app.route('/wristband-tracking')
    @require_login
    def wristband_tracking_page():
        user = get_session_user()
        areas = BathAreaService.list_active()
        return template('templates/wristband_tracking.html', user=user, areas_json=to_template_json(areas))

    @app.route('/api/issue-records/<record_id:int>/status-log', method='GET')
    @require_login
    def api_issue_record_status_log(record_id):
        logs = WristbandService.get_issue_record_status_log(record_id)
        return json_response(logs)
