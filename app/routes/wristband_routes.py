from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response, to_template_json
from app.services import WristbandService, BathAreaService


def register_wristband_routes(app):

    @app.route('/wristbands')
    @require_login
    def wristbands_page():
        user = get_session_user()
        areas = BathAreaService.list_active()
        return template('templates/wristbands.html', user=user, areas_json=to_template_json(areas))

    @app.route('/api/wristbands', method='GET')
    @require_login
    def api_wristbands():
        status = request.query.get('status', '')
        area_id = request.query.get('area_id', '')
        bands = WristbandService.list_wristbands(status=status, area_id=area_id)
        return json_response(bands)

    @app.route('/api/wristbands', method='POST')
    @require_login
    def api_create_wristband():
        data = request.json
        user = get_session_user()
        try:
            WristbandService.create_wristband(
                wristband_no=data['wristband_no'],
                bath_area_id=data.get('bath_area_id'),
                operator_id=user['id']
            )
            return json_response(None, True, '创建成功')
        except ValueError as e:
            return json_response(None, False, str(e))
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/wristbands/<band_id:int>', method='PUT')
    @require_login
    def api_update_wristband(band_id):
        data = request.json
        user = get_session_user()
        try:
            WristbandService.update_wristband(
                band_id=band_id,
                bath_area_id=data.get('bath_area_id'),
                operator_id=user['id']
            )
            return json_response(None, True, '更新成功')
        except ValueError as e:
            return json_response(None, False, str(e))
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/wristbands/<band_id:int>', method='DELETE')
    @require_login
    def api_delete_wristband(band_id):
        user = get_session_user()
        try:
            WristbandService.delete_wristband(
                band_id=band_id,
                operator_id=user['id']
            )
            return json_response(None, True, '删除成功')
        except ValueError as e:
            return json_response(None, False, str(e))
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/wristbands/<band_id:int>/status-log', method='GET')
    @require_login
    def api_wristband_status_log(band_id):
        result = WristbandService.get_wristband_status_log(band_id)
        return json_response(result)
