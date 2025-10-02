from flask import Blueprint, jsonify, g, request
from . import db
from .models import Donation
from .utils import api_login_required, broadcast_to_user, get_full_update_message
import time
import json 

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/get_all_data', methods=['GET'])
@api_login_required
def get_all_data():
    """Возвращает полное состояние данных для пользователя."""
    return jsonify(get_full_update_message(g.user.id))

@bp.route('/submit_donation', methods=['POST'])
@api_login_required
def submit_donation():
    user = g.user
    data = request.get_json()

    # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
    print(f"--- [SUBMIT DONATION] Пользователь: {user.username} (ID: {user.id}) ---")
    print(f"--- Полученные данные: {json.dumps(data, ensure_ascii=False)} ---")
    # -----------------------------
    
    if not data or 'name' not in data or 'amount' not in data:
        print("Ошибка: Отсутствуют обязательные поля 'name' или 'amount'.")
        return jsonify({'error': 'Отсутствуют обязательные поля.'}), 400

    raw_amount = data['amount']
    amount_float = 0.0

    try:
        # 1. Попытка чистой конвертации (для тестовых/чистых данных)
        amount_float = float(raw_amount)
    except ValueError:
        # 2. Очистка строки: удаляем все символы, кроме цифр и точки/запятой
        cleaned_amount = str(raw_amount).replace(' ', '').replace('₸', '').replace(',', '.')
        
        # Если в Казахстане используется запятая как разделитель, то заменяем ее на точку.
        # Удаляем все, кроме цифр и точки.
        
        # Убедимся, что очистка прошла успешно и не оставила лишних символов
        try:
            amount_float = float(cleaned_amount)
            print(f"Успех: Сумма '{raw_amount}' очищена до {amount_float}")
        except ValueError:
            print(f"Критическая ошибка: Не удалось преобразовать сумму '{raw_amount}' в число.")
            return jsonify({'error': f'Сумма доната "{raw_amount}" имеет неверный формат.'}), 400

    new_donation = Donation(name=data['name'], amount=amount_float, message=data.get('message'), user_id=user.id)
    db.session.add(new_donation)
    
    if user.goal:
        user.goal.current_amount += amount_float
    
    db.session.commit()

    donation_data = {'id': new_donation.id, 'name': new_donation.name, 'amount': new_donation.amount, 'message': new_donation.message}
    
    alert_message = {"type": "show_alert", "data": donation_data}
    
    # Отправляем алерт и полное обновление
    broadcast_to_user(user.id, alert_message)
    broadcast_to_user(user.id, {"type": "full_update", "data": get_full_update_message(user.id)})
    
    print("Успех: Донат обработан и отправлен в WebSocket.")
    return jsonify({'status': 'success'})

@bp.route('/update_goal', methods=['POST'])
@api_login_required
def update_goal():
    user = g.user
    data = request.json
    if user.goal:
        user.goal.title = data.get('title', user.goal.title)
        user.goal.target_amount = float(data.get('target', user.goal.target_amount))
        db.session.commit()
        broadcast_to_user(user.id, {"type": "full_update", "data": get_full_update_message(user.id)})
    return jsonify({'status': 'success'})

@bp.route('/update_settings', methods=['POST'])
@api_login_required
def update_settings():
    user = g.user
    data = request.json
    if user.settings:
        user.settings.min_amount = float(data.get('min_amount', user.settings.min_amount))
        user.settings.widget_theme = data.get('widget_theme', user.settings.widget_theme)
        db.session.commit()
        broadcast_to_user(user.id, {"type": "full_update", "data": get_full_update_message(user.id)})
    return jsonify({'status': 'success'})

@bp.route('/add_manual_donation', methods=['POST'])
@api_login_required
def add_manual_donation():
    return submit_donation()

@bp.route('/reset_donations', methods=['POST'])
@api_login_required
def reset_donations():
    user = g.user
    user.donations.delete()
    if user.goal:
        user.goal.current_amount = 0
    db.session.commit()
    broadcast_to_user(user.id, {"type": "full_update", "data": get_full_update_message(user.id)})
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
    broadcast_to_user(user.id, {"type": "full_update", "data": get_full_update_message(user.id)})
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
    from . import PHONE_STATUS
    user = g.user
    return jsonify(PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"}))

@bp.route('/update_phone_status', methods=['POST'])
@api_login_required
def update_phone_status():
    from . import PHONE_STATUS
    user = g.user
    PHONE_STATUS[user.id] = request.json
    broadcast_to_user(user.id, {"type": "phone_status_update", "data": PHONE_STATUS[user.id]})
    return jsonify({'status': 'success'})
