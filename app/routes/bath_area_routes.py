from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response
from app.services import BathAreaService


def register_bath_area_routes(app):

    @app.route('/bath-areas')
    @require_login
    def bath_areas_page():
        user = get_session_user()
        return template('templates/bath_areas.html', user=user)

    @app.route('/api/bath-areas', method='GET')
    @require_login
    def api_bath_areas():
        areas = BathAreaService.list_all()
        return json_response(areas)

    @app.route('/api/bath-areas', method='POST')
    @require_login
    def api_create_bath_area():
        data = request.json
        try:
            BathAreaService.create(
                name=data['name'],
                description=data.get('description', ''),
                base_price=float(data['base_price']),
                deposit_amount=float(data['deposit_amount'])
            )
            return json_response(None, True, '创建成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/bath-areas/<area_id:int>', method='PUT')
    @require_login
    def api_update_bath_area(area_id):
        data = request.json
        try:
            BathAreaService.update(
                area_id=area_id,
                name=data['name'],
                description=data.get('description', ''),
                base_price=float(data['base_price']),
                deposit_amount=float(data['deposit_amount']),
                is_active=data.get('is_active', True)
            )
            return json_response(None, True, '更新成功')
        except Exception as e:
            return json_response(None, False, str(e))

    @app.route('/api/bath-areas/<area_id:int>', method='DELETE')
    @require_login
    def api_delete_bath_area(area_id):
        try:
            BathAreaService.delete(area_id)
            return json_response(None, True, '删除成功')
        except ValueError as e:
            return json_response(None, False, str(e))
        except Exception as e:
            return json_response(None, False, str(e))
