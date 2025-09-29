import json
from functools import wraps
from flask import g, request, jsonify
from flask_login import current_user
from . import clients, PHONE_STATUS, db
from .models import User, Donation

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
        if current_user.is_authenticated:
            user = current_user
        else:
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

def get_full_update_message(user_id):
    """Собирает полное состояние данных для пользователя."""
    user = db.session.get(User, user_id)
    if not user: return {}

    donations = user.donations.order_by(Donation.timestamp.desc()).all()
    goal = user.goal
    settings = user.settings
    stats = user.get_donation_stats()

    donations_list = [{'id': d.id, 'name': d.name, 'amount': d.amount, 'message': d.message, 'timestamp': d.timestamp.isoformat()} for d in donations]
    goal_data = {'title': goal.title, 'current': goal.current_amount, 'target': goal.target_amount} if goal else {}
    
    settings_data = {
        'min_amount': settings.min_amount if settings else 100.0,
        'alert_url': '/static/media/alert.gif',
        'sound_url': '/static/media/alert.mp3',
        'widget_theme': settings.widget_theme if settings else 'dark'
    }
    
    phone_status_data = PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"})

    return {
        "donations": donations_list, 
        "goal": goal_data, 
        "settings": settings_data, 
        "phone_status": phone_status_data,
        "stats": stats
    }
