import json
from datetime import date

from bottle import request, response, redirect, template

from app.decorators import require_login, get_session_user
from app.utils.response import json_response, to_template_json
from app.services import AuthService, ReportService, run_all_warning_checks
from app.config import SECRET_KEY


def register_auth_routes(app):

    @app.route('/login', method='GET')
    def login_page():
        return template('templates/login.html', error='')

    @app.route('/login', method='POST')
    def login_post():
        data = request.json if request.json else request.forms
        username = data.get('username', '').strip()
        password = data.get('password', '')

        result = AuthService.login(username, password)
        if not result['success']:
            if request.json:
                return json_response(None, False, result['message'])
            return template('templates/login.html', error=result['message'])

        session_data = json.dumps(result['data']['session_data'])
        response.set_cookie('session', session_data, secret=SECRET_KEY, path='/', max_age=86400)

        if request.json:
            return json_response({'redirect': '/'})
        redirect('/')

    @app.route('/logout')
    def logout():
        user = get_session_user()
        if user:
            AuthService.logout(user['id'])
        response.delete_cookie('session', path='/')
        redirect('/login')

    @app.route('/')
    @require_login
    def index():
        user = get_session_user()
        run_all_warning_checks()

        def safe_count(sql, *params):
            try:
                from app.database import query_one
                r = query_one(sql, params)
                return int(r['cnt']) if r else 0
            except Exception:
                return 0

        def safe_sum(sql, *params):
            try:
                from app.database import query_one
                r = query_one(sql, params)
                return float(r['total']) if r and r['total'] else 0.0
            except Exception:
                return 0.0

        stats = {
            'available_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'available'"),
            'issued_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'issued'"),
            'frozen_bands': safe_count("SELECT COUNT(*) as cnt FROM wristbands WHERE current_status = 'frozen'"),
            'unsettled': safe_count("SELECT COUNT(*) as cnt FROM issue_records WHERE fee_status = 'unsettled' AND return_time IS NULL"),
            'pending_review': safe_count("SELECT COUNT(*) as cnt FROM reissue_applications WHERE review_status = 'pending'"),
        }

        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        member_stats = {
            'total_members': safe_count("SELECT COUNT(*) as cnt FROM members WHERE status = 'active'"),
            'today_new_members': safe_count(
                "SELECT COUNT(*) as cnt FROM members WHERE DATE(registered_at) = %s", today_str),
            'today_consume_count': safe_count(
                "SELECT COUNT(*) as cnt FROM member_transactions WHERE transaction_type IN ('consumption','package_deduction') AND DATE(created_at) = %s", today_str),
            'today_top_up': safe_sum(
                "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'topup' AND DATE(created_at) = %s", today_str),
            'today_package_verify': safe_count(
                "SELECT COUNT(*) as cnt FROM member_package_usages WHERE DATE(used_at) = %s", today_str),
            'today_balance_deduction': safe_sum(
                "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'consumption' AND DATE(created_at) = %s", today_str),
            'today_package_deduction': safe_sum(
                "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'package_deduction' AND DATE(created_at) = %s", today_str),
            'today_gift_bonus': safe_sum(
                "SELECT SUM(amount) as total FROM member_transactions WHERE transaction_type = 'gift_bonus' AND DATE(created_at) = %s", today_str),
            'today_member_issue_count': safe_count(
                "SELECT COUNT(*) as cnt FROM issue_records WHERE member_id IS NOT NULL AND DATE(issue_time) = %s", today_str),
        }

        from app.services import get_unread_warning_stats, get_current_store_id
        warning_stats = get_unread_warning_stats()
        recent_warnings = []
        cross_store_stats = {'today_local_income': 0.0, 'today_cross_income': 0.0, 'today_cross_deduction': 0.0, 'pending_clearing': 0.0}

        try:
            current_store_id = get_current_store_id(user)
            if current_store_id:
                today_cs = date.today().strftime('%Y-%m-%d')
                from app.database import query_one
                li = query_one('''SELECT COALESCE(SUM(base_fee + extra_fee + loss_fee + reissue_fee), 0) as total
                                  FROM issue_records WHERE store_id = %s AND fee_status = 'settled' AND DATE(issue_time) = %s''', (current_store_id, today_cs))
                ci = query_one('''SELECT COALESCE(SUM(amount), 0) as total FROM clearing_records
                                  WHERE store_id = %s AND amount_type = 'target_income' AND status = 'settled' AND DATE(settled_at) = %s''', (current_store_id, today_cs))
                cd = query_one('''SELECT COALESCE(SUM(deduction_amount), 0) as total FROM cross_store_records
                                  WHERE consume_store_id = %s AND DATE(created_at) = %s''', (current_store_id, today_cs))
                pc = query_one('''SELECT COALESCE(SUM(amount), 0) as total FROM clearing_records
                                  WHERE store_id = %s AND status = 'pending' ''', (current_store_id,))
                cross_store_stats = {
                    'today_local_income': float(li['total']) if li else 0.0,
                    'today_cross_income': float(ci['total']) if ci else 0.0,
                    'today_cross_deduction': float(cd['total']) if cd else 0.0,
                    'pending_clearing': float(pc['total']) if pc else 0.0,
                }
        except Exception:
            pass

        try:
            from app.database import query
            rows = query('''
                SELECT w.*, u1.full_name as read_by_name, u2.full_name as resolved_by_name,
                       wr.wristband_no, ba.name as bath_area_name
                FROM warnings w
                LEFT JOIN users u1 ON w.read_by = u1.id
                LEFT JOIN users u2 ON w.resolved_by = u2.id
                LEFT JOIN wristbands wr ON w.wristband_id = wr.id
                LEFT JOIN bath_areas ba ON w.bath_area_id = ba.id
                ORDER BY w.created_at DESC LIMIT 20
            ''')
            recent_warnings = [dict(r) for r in rows]
        except Exception:
            pass

        return template(
            'templates/index.html',
            user=user,
            stats=stats,
            member_stats=member_stats,
            warning_stats_json=to_template_json(warning_stats),
            recent_warnings_json=to_template_json(recent_warnings),
            cross_store_stats_json=to_template_json(cross_store_stats)
        )
