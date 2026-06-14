from bottle import request, template

from app import app
from app.decorators import require_login
from app.decorators import get_session_user
from app.utils.response import json_response
from app.services import ReportService


@app.route('/cross-store-report')
@require_login
def cross_store_report_page():
    user = get_session_user()
    return template('templates/cross_store_report.html', user=user)


@app.route('/api/hq/report', method='GET')
@require_login
def api_hq_report():
    start_date = request.query.get('start_date', '')
    end_date = request.query.get('end_date', '')

    result = ReportService.get_hq_report(start_date=start_date, end_date=end_date)
    return json_response(result)


@app.route('/api/hq/store-summary', method='GET')
@require_login
def api_hq_store_summary():
    result = ReportService.get_hq_store_summary()
    return json_response(result)
