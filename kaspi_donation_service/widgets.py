import json
import gevent
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from . import db, sock, clients
from .models import User
from .api import get_full_update_message
from .auth import check_account_status

bp = Blueprint('widgets', __name__)

def widget_access_check(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return "Пользователь не найден", 404
    is_allowed, message = check_account_status(user)
    if not is_allowed:
        return f"Доступ запрещен. {message}", 403
    return None, None # OK

@bp.route('/alert/<int:user_id>')
def alert_widget(user_id):
    error_message, status_code = widget_access_check(user_id)
    if error_message: return error_message, status_code
    return render_template('alert.html', user_id=user_id)

@bp.route('/goal/<int:user_id>')
def goal_widget(user_id):
    error_message, status_code = widget_access_check(user_id)
    if error_message: return error_message, status_code
    return render_template('goal.html', user_id=user_id)

@bp.route('/top_donators/<int:user_id>')
def top_donators_widget(user_id):
    error_message, status_code = widget_access_check(user_id)
    if error_message: return error_message, status_code
    return render_template('top_donators.html', user_id=user_id)

@bp.route('/top_donators_day/<int:user_id>')
def top_donators_day_widget(user_id):
    error_message, status_code = widget_access_check(user_id)
    if error_message: return error_message, status_code
    return render_template('top_donators_day.html', user_id=user_id)

@bp.route('/top_donators_month/<int:user_id>')
def top_donators_month_widget(user_id):
    error_message, status_code = widget_access_check(user_id)
    if error_message: return error_message, status_code
    return render_template('top_donators_month.html', user_id=user_id)

@bp.route('/latest_donations/<int:user_id>')
def latest_donations_widget(user_id):
    error_message, status_code = widget_access_check(user_id)
    if error_message: return error_message, status_code
    return render_template('latest_donations.html', user_id=user_id)
    
@bp.route('/latest_donations_popout/<int:user_id>')
def latest_donations_popout(user_id):
    error_message, status_code = widget_access_check(user_id)
    if error_message: return error_message, status_code
    return render_template('latest_donations_popout.html', user_id=user_id)

@sock.route('/ws')
def ws(ws):
    user_id = request.args.get('user_id', type=int)
    if not user_id and current_user.is_authenticated:
        user_id = current_user.id
    if not user_id: return

    error_message, _ = widget_access_check(user_id)
    if error_message:
        try:
            ws.send(json.dumps({"type": "error", "message": error_message}))
        except Exception: pass
        ws.close()
        return
        
    if user_id not in clients:
        clients[user_id] = set()
    clients[user_id].add(ws)
    print(f"🔗 WebSocket client connected for user {user_id}. Total: {len(clients[user_id])}")
    
    try:
        ws.send(json.dumps(get_full_update_message(user_id), ensure_ascii=False))
        while True:
            gevent.sleep(25)
            try:
                ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                break 
    finally:
        if user_id in clients and ws in clients[user_id]:
            clients[user_id].remove(ws)
        print(f"🔌 WebSocket client disconnected for user {user_id}.")
