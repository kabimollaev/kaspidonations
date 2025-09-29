import json
from functools import wraps
from flask import g, request, jsonify
from flask_login import current_user
from . import clients, PHONE_STATUS
from .models import User

def check_user_status(user):
    """Проверяет, активен ли пользователь."""
    if user.role == 'admin' or user.status == 'active':
        return True, None
    return False, 'Аккаунт неактивен. Пожалуйста, обратитесь к администратору для активации.'

def api_login_required(f):
    """Декоратор для проверки API-ключа или сессии пользователя."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = None
        # Проверка по сессии (для браузера)
        if current_user.is_authenticated:
            user = current_user
        else:
            # Проверка по API-ключу (для приложения на ПК)
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                return jsonify({'error': 'Доступ запрещен. Требуется аутентификация.'}), 401
            user = User.query.filter_by(api_key=api_key).first()
            if not user:
                return jsonify({'error': 'Неверный API-ключ.'}), 403
        
        is_allowed, message = check_user_status(user)
        if not is_allowed:
            return jsonify({'error': message}), 403

        g.user = user
        return f(*args, **kwargs)
    return decorated_function

def broadcast_to_user(user_id, message_data):
    """Отправляет сообщение всем WebSocket клиентам пользователя."""
    if user_id in clients:
        message_str = json.dumps(message_data, ensure_ascii=False)
        for ws in list(clients[user_id]):
            try:
                ws.send(message_str)
            except Exception:
                clients[user_id].remove(ws)
