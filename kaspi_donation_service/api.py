from flask import Blueprint, jsonify, g, request
from . import db
from .models import Donation
from .utils import api_login_required, broadcast_to_user, get_full_update_message
import time
import json # Добавлен для логирования

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

    try:
        amount_float = float(data['amount'])
    except ValueError:
        print(f"Ошибка: 'amount' не является числом: {data['amount']}")
        return jsonify({'error': 'Сумма доната должна быть числом.'}), 400

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
# ... (остальная часть api.py без изменений)
