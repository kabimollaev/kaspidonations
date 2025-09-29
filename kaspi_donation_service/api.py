from flask import Blueprint, jsonify, g, request
from . import db, clients, PHONE_STATUS
from .models import Donation
from .utils import api_login_required, broadcast_to_user
import time

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/get_all_data', methods=['GET'])
@api_login_required
def get_all_data():
    user = g.user
    
    # Получаем все данные одним запросом для эффективности
    donations = user.donations.order_by(Donation.timestamp.desc()).all()
    goal = user.goal
    settings = user.settings
    stats = user.get_donation_stats()

    # Формируем данные для JSON
    donations_list = [{'id': d.id, 'name': d.name, 'amount': d.amount, 'message': d.message, 'timestamp': d.timestamp.isoformat()} for d in donations]
    goal_data = {'title': goal.title, 'current': goal.current_amount, 'target': goal.target_amount} if goal else {}
    
    settings_data = {
        'min_amount': settings.min_amount if settings else 100.0,
        'alert_url': '/static/media/alert.gif',
        'sound_url': '/static/media/alert.mp3',
        # ИСПРАВЛЕНИЕ: Жестко задаем темную тему, так как убрали ее из настроек
        'widget_theme': 'dark' 
    }
    
    phone_status_data = PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"})

    full_data = {
        "donations": donations_list, 
        "goal": goal_data, 
        "settings": settings_data, 
        "phone_status": phone_status_data,
        "stats": stats
    }
    
    return jsonify(full_data)


@bp.route('/submit_donation', methods=['POST'])
@api_login_required
def submit_donation():
    user = g.user
    data = request.get_json()
    if not data or 'name' not in data or 'amount' not in data:
        return jsonify({'error': 'Отсутствуют обязательные поля.'}), 400

    new_donation = Donation(name=data['name'], amount=float(data['amount']), message=data.get('message'), user_id=user.id)
    db.session.add(new_donation)
    
    if user.goal:
        user.goal.current_amount += float(data['amount'])
    
    db.session.commit()

    donation_data = {'id': new_donation.id, 'name': new_donation.name, 'amount': new_donation.amount, 'message': new_donation.message}
    
    # Формируем полное сообщение для виджета
    alert_message = {
        "type": "show_alert",
        "data": donation_data
    }
    
    broadcast_to_user(user.id, alert_message)
    broadcast_to_user(user.id, {"type": "full_update", "data": get_all_data().json})
    
    return jsonify({'status': 'success'})

# ... (остальные API маршруты без изменений) ...

@bp.route('/update_goal', methods=['POST'])
@api_login_required
def update_goal():
    user = g.user
    data = request.json
    if user.goal:
        user.goal.title = data.get('title', user.goal.title)
        user.goal.target_amount = float(data.get('target', user.goal.target_amount))
        db.session.commit()
        broadcast_to_user(user.id, {"type": "full_update", "data": get_all_data().json})
    return jsonify({'status': 'success'})

@bp.route('/update_settings', methods=['POST'])
@api_login_required
def update_settings():
    user = g.user
    data = request.json
    if user.settings:
        user.settings.min_amount = float(data.get('min_amount', user.settings.min_amount))
        # ИСПРАВЛЕНИЕ: Убрали обновление темы
        # user.settings.widget_theme = data.get('widget_theme', user.settings.widget_theme)
        db.session.commit()
        broadcast_to_user(user.id, {"type": "full_update", "data": get_all_data().json})
    return jsonify({'status': 'success'})

@bp.route('/add_manual_donation', methods=['POST'])
@api_login_required
def add_manual_donation():
    # Эта логика идентична submit_donation, можно использовать ее
    return submit_donation()

@bp.route('/reset_donations', methods=['POST'])
@api_login_required
def reset_donations():
    user = g.user
    user.donations.delete()
    if user.goal:
        user.goal.current_amount = 0
    db.session.commit()
    broadcast_to_user(user.id, {"type": "full_update", "data": get_all_data().json})
    return jsonify({'status': 'success'})

@bp.route('/delete_donation/<int:donation_id>', methods=['POST'])
@api_login_required
def delete_donation(donation_id):
    user = g.user
    donation = db.session.get(Donation, donation_id)
    if not donation or donation.user_id != user.id:
        return jsonify({'error': 'Донат не найден'}), 404
    if user.goal:
        user.goal.current_amount -= donation.amount
    db.session.delete(donation)
    db.session.commit()
    broadcast_to_user(user.id, {"type": "full_update", "data": get_all_data().json})
    return jsonify({'status': 'success'})

@bp.route('/replay_donation/<int:donation_id>', methods=['POST'])
@api_login_required
def replay_donation(donation_id):
    user = g.user
    donation = db.session.get(Donation, donation_id)
    if not donation or donation.user_id != user.id:
        return jsonify({'error': 'Донат не найден'}), 404
    
    donation_data = {'id': donation.id, 'name': donation.name, 'amount': donation.amount, 'message': donation.message}
    alert_message = {"type": "show_alert", "data": donation_data}
    broadcast_to_user(user.id, alert_message)
    
    return jsonify({'status': 'success'})

@bp.route('/test_donation', methods=['POST'])
@api_login_required
def test_donation_api():
    user = g.user
    test_donation_data = {'id': f"test_{int(time.time())}",'name': 'Тестер','amount': 100,'message': 'Это тестовый донат!'}
    
    alert_message = {"type": "show_alert", "data": test_donation_data}
    broadcast_to_user(user.id, alert_message)
    
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
    donations = user.get_donations_by_period('day')
    
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
    donations = user.get_donations_by_period('month')

    top_donators = {}
    for d in donations:
        name = d.name
        top_donators[name] = top_donators.get(name, 0) + d.amount
    
    sorted_top = sorted(top_donators.items(), key=lambda item: item[1], reverse=True)
    formatted_list = [{'name': name, 'amount': amount} for name, amount in sorted_top]
    
    return jsonify({'top_donators_month': formatted_list})
