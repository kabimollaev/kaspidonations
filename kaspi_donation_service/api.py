import time
import json
from datetime import datetime
from functools import wraps
from flask import Blueprint, g, jsonify, request
from flask_login import current_user
from sqlalchemy import func
from . import db, sock, clients, PHONE_STATUS
from .models import User, Donation

bp = Blueprint('api', __name__, url_prefix='/api')

# --- Вспомогательные функции ---

def get_full_update_message(user_id):
    user = db.session.get(User, user_id)
    if not user: return {}
    
    donations = user.donations.order_by(Donation.timestamp.desc()).all()
    goal = user.goal
    settings = user.settings

    donations_list = [{'id': d.id, 'name': d.name, 'amount': d.amount, 'message': d.message, 'timestamp': d.timestamp.isoformat()} for d in donations]
    goal_data = {'title': goal.title, 'current': goal.current_amount, 'target': goal.target_amount} if goal else {}
    settings_data = {
        'min_amount': settings.min_amount,
        'widget_theme': settings.widget_theme,
        'alert_url': '/static/media/alert.gif',
        'sound_url': '/static/media/alert.mp3',
    } if settings else {}
    phone_status_data = PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"})

    return {"type": "full_update", "data": {"donations": donations_list, "goal": goal_data, "settings": settings_data, "phone_status": phone_status_data}}

def broadcast_to_user(user_id, message_data):
    if user_id in clients:
        message_str = json.dumps(message_data, ensure_ascii=False)
        for ws in list(clients[user_id]):
            try:
                ws.send(message_str)
            except Exception:
                clients[user_id].remove(ws)

def get_donation_stats(user_id):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    total_donations = Donation.query.filter_by(user_id=user_id)
    today_donations = total_donations.filter(Donation.timestamp >= today_start)
    month_donations = total_donations.filter(Donation.timestamp >= month_start)

    return {
        'total': {'count': total_donations.count(), 'sum': db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).scalar() or 0},
        'today': {'count': today_donations.count(), 'sum': db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).filter(Donation.timestamp >= today_start).scalar() or 0},
        'month': {'count': month_donations.count(), 'sum': db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).filter(Donation.timestamp >= month_start).scalar() or 0},
    }

def api_login_required(f):
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
        
        from .auth import check_account_status
        is_allowed, message = check_account_status(user)
        if not is_allowed:
            return jsonify({'error': message}), 403

        g.user = user
        return f(*args, **kwargs)
    return decorated_function


# --- Маршруты API ---

@bp.route('/get_all_data', methods=['GET'])
@api_login_required
def get_all_data():
    user = g.user
    full_update = get_full_update_message(user.id)
    full_update['data']['stats'] = get_donation_stats(user.id)
    return jsonify(full_update['data'])

@bp.route('/submit_donation', methods=['POST'])
@api_login_required
def submit_donation():
    user = g.user
    data = request.get_json()
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


@bp.route('/update_goal', methods=['POST'])
@api_login_required
def update_goal():
    user = g.user
    data = request.json
    user.goal.title = data.get('title')
    user.goal.target_amount = float(data.get('target', 0))
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@bp.route('/update_settings', methods=['POST'])
@api_login_required
def update_settings():
    user = g.user
    data = request.json
    user.settings.min_amount = float(data.get('min_amount', 0))
    user.settings.widget_theme = data.get('widget_theme', 'dark')
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@bp.route('/add_manual_donation', methods=['POST'])
@api_login_required
def add_manual_donation():
    user = g.user
    data = request.json
    donation = Donation(name=data['name'], amount=float(data['amount']), message=data.get('message'), user_id=user.id)
    db.session.add(donation)
    user.goal.current_amount += float(data['amount'])
    db.session.commit()
    donation_data = {'id': donation.id, 'name': donation.name, 'amount': donation.amount, 'message': donation.message}
    broadcast_to_user(user.id, {"type": "show_alert", "data": donation_data})
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@bp.route('/reset_donations', methods=['POST'])
@api_login_required
def reset_donations():
    user = g.user
    Donation.query.filter_by(user_id=user.id).delete()
    user.goal.current_amount = 0
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@bp.route('/delete_donation/<int:donation_id>', methods=['POST'])
@api_login_required
def delete_donation(donation_id):
    user = g.user
    donation = db.session.get(Donation, donation_id)
    if not donation or donation.user_id != user.id:
        return jsonify({'error': 'Донат не найден'}), 404
    user.goal.current_amount -= donation.amount
    db.session.delete(donation)
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@bp.route('/replay_donation/<int:donation_id>', methods=['POST'])
@api_login_required
def replay_donation(donation_id):
    user = g.user
    donation = db.session.get(Donation, donation_id)
    if not donation or donation.user_id != user.id:
        return jsonify({'error': 'Донат не найден'}), 404
    donation_data = {'id': donation.id, 'name': donation.name, 'amount': donation.amount, 'message': donation.message}
    broadcast_to_user(user.id, {"type": "show_alert", "data": donation_data})
    return jsonify({'status': 'success'})

@bp.route('/test_donation', methods=['POST'])
@api_login_required
def test_donation_api():
    user = g.user
    test_donation_data = {'id': f"test_{int(time.time())}",'name': 'Тестер','amount': 100,'message': 'Это тестовый донат!'}
    broadcast_to_user(user.id, {"type": "show_alert", "data": test_donation_data})
    return jsonify({'status': 'success'})

@bp.route('/get_phone_status', methods=['GET'])
@api_login_required
def get_phone_status():
    user = g.user
    return jsonify(PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"}))

@bp.route('/update_phone_status', methods=['POST'])
@api_login_required
def update_phone_status():
    user = g.user
    PHONE_STATUS[user.id] = request.json
    broadcast_to_user(user.id, {"type": "phone_status_update", "data": PHONE_STATUS[user.id]})
    return jsonify({'status': 'success'})

@bp.route('/get_daily_top_donators', methods=['GET'])
@api_login_required
def get_daily_top_donators():
    user = g.user
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    donations = Donation.query.filter_by(user_id=user.id).filter(Donation.timestamp >= today_start).order_by(Donation.amount.desc()).all()
    top_donators = {}
    for d in donations:
        name = d.name
        top_donators[name] = top_donators.get(name, 0) + d.amount
    sorted_top = sorted(top_donators.items(), key=lambda item: item[1], reverse=True)
    formatted_list = [{'name': name, 'amount': amount} for name, amount in sorted_top]
    return jsonify({'top_donators_day': formatted_list})

@bp.route('/get_monthly_top_donators', methods=['GET'])
@api_login_required
def get_monthly_top_donators():
    user = g.user
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    donations = Donation.query.filter_by(user_id=user.id).filter(Donation.timestamp >= month_start).order_by(Donation.amount.desc()).all()
    top_donators = {}
    for d in donations:
        name = d.name
        top_donators[name] = top_donators.get(name, 0) + d.amount
    sorted_top = sorted(top_donators.items(), key=lambda item: item[1], reverse=True)
    formatted_list = [{'name': name, 'amount': amount} for name, amount in sorted_top]
    return jsonify({'top_donators_month': formatted_list})
