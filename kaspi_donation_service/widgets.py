from flask import Blueprint, render_template, request, g
from flask_login import current_user
from .. import db, sock, clients
from ..models import User, Settings
import json
import gevent

bp = Blueprint('widgets', __name__)

def get_user_and_check_status(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return None, ("Пользователь не найден", 404)
    if user.status != 'active' and user.role != 'admin':
        return None, ("Доступ к виджету запрещен", 403)
    return user, None

@bp.route('/alert/<int:user_id>')
def alert_widget(user_id):
    user, error = get_user_and_check_status(user_id)
    if error: return error
    return render_template('alert.html', user=user)

@bp.route('/goal/<int:user_id>')
def goal_widget(user_id):
    user, error = get_user_and_check_status(user_id)
    if error: return error
    return render_template('goal.html', user=user)

# ... Аналогичные маршруты для всех остальных виджетов ...

@sock.route('/ws')
def ws(ws):
    user_id = request.args.get('user_id', type=int)
    if not user_id and current_user.is_authenticated:
        user_id = current_user.id
    
    if not user_id:
        ws.close()
        return

    user, error = get_user_and_check_status(user_id)
    if error:
        ws.close()
        return
        
    if user_id not in clients:
        clients[user_id] = set()
    clients[user_id].add(ws)
    print(f"🔗 WebSocket client connected for user {user_id}. Total: {len(clients.get(user_id, []))}")
    
    from .api import get_full_update_message
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
