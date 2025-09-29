import time
from functools import wraps
from flask import Blueprint, request, g, jsonify
from flask_login import current_user
from .. import db, clients, PHONE_STATUS
from ..models import User, Donation, Settings
from datetime import datetime, timedelta
from sqlalchemy import func

bp = Blueprint('api', __name__, url_prefix='/api')

# --- Helper Functions ---

def broadcast_to_user(user_id, message_data):
    # This logic is now part of the API blueprint
    import json
    if user_id in clients:
        message_str = json.dumps(message_data, ensure_ascii=False)
        for ws in list(clients[user_id]):
            try:
                ws.send(message_str)
            except Exception:
                clients[user_id].remove(ws)

def get_full_update_message(user_id):
    user = db.session.get(User, user_id)
    if not user: return {}
    
    donations = user.donations.order_by(Donation.timestamp.desc()).all()
    goal = user.goal
    settings = user.settings

    donations_list = [{'id': d.id, 'name': d.name, 'amount': d.amount, 'message': d.message} for d in donations]
    goal_data = {'title': goal.title, 'current': goal.current_amount, 'target': goal.target_amount} if goal else {}
    settings_data = {
        'min_amount': settings.min_amount,
        'theme': settings.theme,
        'alert_url': '/static/media/alert.gif',
        'sound_url': '/static/media/alert.mp3',
    } if settings else {}
    phone_status_data = PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"})

    return {"type": "full_update", "data": {"donations": donations_list, "goal": goal_data, "settings": settings_data, "phone_status": phone_status_data}}


def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = None
        if current_user.is_authenticated:
            user = current_user
        else:
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                return jsonify({'error': 'Доступ запрещен.'}), 401
            user = User.query.filter_by(api_key=api_key).first()
            if not user:
                return jsonify({'error': 'Неверный API-ключ.'}), 403
        
        g.user = user
        return f(*args, **kwargs)
    return decorated_function

# --- API Routes ---

@bp.route('/get_all_data')
@api_login_required
def get_all_data():
    user = g.user
    full_update = get_full_update_message(user.id)
    return jsonify(full_update.get('data', {}))

@bp.route('/get_chart_data')
@api_login_required
def get_chart_data():
    user = g.user
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    donations = db.session.query(
        func.date(Donation.timestamp),
        func.sum(Donation.amount)
    ).filter(
        Donation.user_id == user.id,
        Donation.timestamp >= thirty_days_ago
    ).group_by(
        func.date(Donation.timestamp)
    ).order_by(
        func.date(Donation.timestamp)
    ).all()
    
    # Форматируем данные для Chart.js
    labels = [d[0].strftime('%Y-%m-%d') for d in donations]
    data = [float(d[1]) for d in donations]
    
    return jsonify({'labels': labels, 'data': data})


@bp.route('/submit_donation', methods=['POST'])
@api_login_required
def submit_donation():
    user = g.user
    data = request.json
    if not data or 'name' not in data or 'amount' not in data:
        return jsonify({'error': 'Отсутствуют обязательные поля.'}), 400
    
    new_donation = Donation(name=data['name'], amount=float(data['amount']), message=data.get('message'), user_id=user.id)
    db.session.add(new_donation)
    user.goal.current_amount += float(data['amount'])
    db.session.commit()
    
    donation_data = {'id': new_donation.id, 'name': new_donation.name, 'amount': new_donation.amount, 'message': new_donation.message}
    broadcast_to_user(user.id, {"type": "show_alert", "data": donation_data})
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@bp.route('/update_settings', methods=['POST'])
@api_login_required
def update_settings():
    user = g.user
    data = request.json
    settings = user.settings or Settings(user_id=user.id)
    
    settings.min_amount = float(data.get('min_amount', settings.min_amount))
    settings.theme = data.get('theme', settings.theme)
    
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

# ... Остальные API маршруты (reset, delete, replay и т.д.) переносятся сюда аналогичным образом ...
# (Для краткости я опущу их здесь, но они должны быть перенесены)
