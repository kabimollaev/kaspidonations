import json
import gevent
from flask import request
from flask_login import current_user
from . import sock, db, clients
from .models import User
from .utils import check_user_status, get_full_update_message

@sock.route('/ws')
def ws(ws):
    """Основной маршрут для WebSocket соединений."""
    user_id = request.args.get('user_id', type=int)
    api_key = request.args.get('api_key')
    user = None
    
    # Определяем пользователя: сначала по сессии, потом по ключу в URL
    if current_user.is_authenticated:
        user = current_user
        user_id = current_user.id
    elif api_key:
        user = User.query.filter_by(api_key=api_key).first()
        if user:
            user_id = user.id

    if not user:
        ws.close()
        return

    # Проверка статуса пользователя
    is_allowed, message = check_user_status(user)
    if not is_allowed:
        try:
            ws.send(json.dumps({"type": "error", "message": message}))
        except Exception:
            pass
        ws.close()
        return
        
    # Регистрация клиента
    if user_id not in clients:
        clients[user_id] = set()
    clients[user_id].add(ws)
    print(f"🔗 WebSocket client connected for user {user_id}. Total: {len(clients[user_id])}")

    try:
        # Отправляем полное состояние при подключении
        ws.send(json.dumps({"type": "full_update", "data": get_full_update_message(user.id)}, ensure_ascii=False))
        
        # Цикл для поддержания соединения
        while True:
            gevent.sleep(25)
            try:
                ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                break 
    finally:
        # Удаление клиента при отключении
        if user_id in clients and ws in clients[user_id]:
            clients[user_id].remove(ws)
        print(f"🔌 WebSocket client disconnected for user {user_id}.")

