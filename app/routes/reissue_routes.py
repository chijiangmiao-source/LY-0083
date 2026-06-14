from bottle import request, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response
from app.services import LossReissueService


def register_reissue_routes(app):

    @app.route('/reissue-review')
    @require_login
    def reissue_review_page():
        user = get_session_user()
        return template('templates/reissue_review.html', user=user)

    @app.route('/api/reissue/pending', method='GET')
    @require_login
    def api_reissue_pending():
        records = LossReissueService.get_pending_reissues()
        return json_response(records)

    @app.route('/api/reissue/<app_id:int>/review', method='POST')
    @require_login
    def api_review_reissue(app_id):
        data = request.json
        user = get_session_user()

        try:
            LossReissueService.review_reissue(
                app_id=app_id,
                decision=data.get('decision'),
                operator_id=user['id'],
                is_responsible=data.get('is_responsible', True),
                loss_fee=data.get('loss_fee', 0),
                reissue_fee=data.get('reissue_fee', 0),
                new_wristband_id=data.get('new_wristband_id'),
                review_comment=data.get('review_comment', ''),
                skip_auto_discount=data.get('skip_auto_discount'),
                loss_fee_original=data.get('loss_fee_original'),
                reissue_fee_original=data.get('reissue_fee_original'),
            )
            if data.get('decision') == 'reject':
                return json_response(None, True, '审核驳回成功')
            return json_response(None, True, '审核通过成功')
        except ValueError as e:
            return json_response(None, False, str(e))
