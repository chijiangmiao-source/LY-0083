from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response, to_template_json
from app.database import query
from app.services import (
    ShiftService,
    run_all_warning_checks,
    get_unread_warning_stats,
)


def register_shift_routes(app):

    @app.route('/shift-summary')
    @require_login
    def shift_summary_page():
        user = get_session_user()
        run_all_warning_checks()
        shift = ShiftService.get_active_shift(user['id'])
        if not shift:
            return template('templates/shift_summary.html', user=user, shift_json='null', records_json='[]', summary_json='null',
                            warning_stats_json=to_template_json({'total_unread':0,'high_count':0,'medium_count':0,'normal_count':0,'unresolved_count':0}),
                            shift_warnings_json='[]')

        records = ShiftService.get_shift_records(user['id'], shift['start_time'])
        summary_data = ShiftService.calculate_shift_summary(records, shift)

        warning_stats = get_unread_warning_stats()
        shift_warnings = []
        try:
            record_ids = [r['id'] for r in records]
            if record_ids:
                shift_warnings = get_warnings_by_issue_record_ids(record_ids)
        except Exception:
            pass

        return template('templates/shift_summary.html', user=user, shift_json=to_template_json(shift),
                        records_json=to_template_json(records), summary_json=to_template_json(summary_data),
                        warning_stats_json=to_template_json(warning_stats),
                        shift_warnings_json=to_template_json(shift_warnings))

    @app.route('/api/shift/close', method='POST')
    @require_login
    def api_close_shift():
        user = get_session_user()
        result = ShiftService.close_shift(user['id'])
        return json_response(result.get('data'), result.get('success', True), result.get('message', ''))
