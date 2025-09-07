import time
import uuid
import os
import json
import webbrowser
import threading
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sock import Sock
from gtts import gTTS

# --- Настройка путей ---
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Конфигурация приложения ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'instance', 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
os.makedirs(os.path.join(basedir, 'tts_cache'), exist_ok=True)
os.makedirs(os.path.join(basedir, 'static', 'media'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

sock = Sock(app)
app.clients = set()

# Глобальные переменные для статуса Phone Link
PHONE_STATUS = {
    "connected": False,
    "message": "Поиск Phone Link...",
    "last_check": None
}

# Путь к кешу TTS
TTS_CACHE_DIR = os.path.join(basedir, 'tts_cache')

# --- Модели Базы Данных ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    status = db.Column(db.String(20), nullable=False, default='inactive')
    api_key = db.Column(db.String(120), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    hardware_id = db.Column(db.String(200), unique=True, nullable=True)
    
    donations = db.relationship('Donation', backref='user', lazy=True)
    goal = db.relationship('Goal', backref='user', uselist=False, lazy=True)
    settings = db.relationship('Settings', backref='user', uselist=False, lazy=True)

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default='На новую цель')
    current_amount = db.Column(db.Float, nullable=False, default=0.0)
    target_amount = db.Column(db.Float, nullable=False, default=10000.0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    min_amount = db.Column(db.Float, nullable=False, default=100.0)
    tts_enabled = db.Column(db.Boolean, nullable=False, default=True)
    tts_volume = db.Column(db.Float, nullable=False, default=0.7)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_cache_buster():
    return dict(cache_buster=int(time.time()))

# --- Функции для WebSocket ---
def broadcast(data, user_id):
    """Отправляет данные всем клиентам WebSocket данного пользователя."""
    message = json.dumps(data, ensure_ascii=False)
    for ws in app.clients:
        if hasattr(ws, 'user_id') and ws.user_id == user_id:
            try:
                ws.send(message)
            except Exception as e:
                print(f"❌ Не удалось отправить WebSocket сообщение: {e}")

def trigger_tts(text, user_id):
    """Создает TTS файл и отправляет его через WebSocket."""
    try:
        if not os.path.exists(TTS_CACHE_DIR):
            os.makedirs(TTS_CACHE_DIR)
        
        tts = gTTS(text, lang='ru')
        filename = os.path.join(TTS_CACHE_DIR, f'tts_{int(time.time())}.mp3')
        tts.save(filename)
        
        # Отправляем URL для воспроизведения
        broadcast({"type": "tts", "url": f'/tts_cache/{os.path.basename(filename)}'}, user_id)
        
        print(f"✅ TTS создан: {filename}")
    except Exception as e:
        print(f"❌ Ошибка создания TTS: {e}")

def get_full_update_message(user_id):
    """Формирует полное сообщение-обновление для виджетов."""
    donations = Donation.query.filter_by(user_id=user_id).order_by(Donation.timestamp.desc()).all()
    goal = Goal.query.filter_by(user_id=user_id).first()
    settings = Settings.query.filter_by(user_id=user_id).first()

    donations_list = [
        {'id': int(d.id), 'name': d.name, 'amount': float(d.amount), 'message': d.message}
        for d in donations
    ]
    
    goal_data = {'title': goal.title, 'current': float(goal.current_amount), 'target': float(goal.target_amount)} if goal else {'title': 'На новую цель', 'current': 0.0, 'target': 10000.0}
    settings_data = {'min_amount': float(settings.min_amount), 'tts_enabled': settings.tts_enabled, 'tts_volume': float(settings.tts_volume)} if settings else {'min_amount': 100.0, 'tts_enabled': True, 'tts_volume': 0.7}

    return {"type": "full_update", "data": {"donations": donations_list, "goal": goal_data, "settings": settings_data, "phone_status": PHONE_STATUS}}


# --- Маршруты Аутентификации и Основные страницы ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash('Неверный логин или пароль.', 'error')
            return redirect(url_for('login'))
        if user.status != 'active':
            flash('Ваш аккаунт неактивен. Обратитесь к администратору.', 'error')
            return redirect(url_for('login'))
        login_user(user, remember=True)
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Имя пользователя уже занято.', 'error')
            return redirect(url_for('register'))
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(new_user)
        db.session.commit()
        
        user_goal = Goal(user_id=new_user.id)
        user_settings = Settings(user_id=new_user.id)
        db.session.add(user_goal)
        db.session.add(user_settings)
        db.session.commit()

        flash('Регистрация прошла успешно! Ожидайте активации аккаунта администратором.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if not current_user.goal:
        user_goal = Goal(user_id=current_user.id)
        db.session.add(user_goal)
        db.session.commit()
    if not current_user.settings:
        user_settings = Settings(user_id=current_user.id)
        db.session.add(user_settings)
        db.session.commit()
    return render_template('dashboard.html', user=current_user)

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('admin_panel.html', users=users, cache_buster=int(time.time()))

@app.route('/admin/update_user/<int:user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    user_to_update = User.query.get_or_404(user_id)
    user_to_update.role = request.form.get('role')
    user_to_update.status = request.form.get('status')
    db.session.commit()
    flash(f'Данные пользователя {user_to_update.username} обновлены.', 'success')
    return redirect(url_for('admin_panel'))

# --- API для Панели Управления и Агента ---

@app.before_request
def before_request_api():
    g.user = None
    if request.path.startswith('/api/submit_donation'):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key:
            user = User.query.filter_by(api_key=api_key).first()
            if user:
                g.user = user
    elif request.path.startswith('/api/'):
        if not current_user.is_authenticated:
            return jsonify({"status": "error", "message": "Доступ запрещен. Требуется аутентификация."}), 401
        g.user = current_user

@app.route('/api/get_all_data', methods=['GET'])
@login_required
def get_all_data():
    user_id = g.user.id if g.user else current_user.id
    donations = Donation.query.filter_by(user_id=user_id).order_by(Donation.timestamp.desc()).all()
    goal = Goal.query.filter_by(user_id=user_id).first()
    settings = Settings.query.filter_by(user_id=user_id).first()
    
    donations_list = [
        {
            'id': d.id,
            'name': d.name,
            'amount': d.amount,
            'message': d.message,
            'timestamp': d.timestamp.isoformat()
        } for d in donations
    ]
    
    goal_data = {
        'title': goal.title,
        'current_amount': goal.current_amount,
        'target_amount': goal.target_amount
    } if goal else {'title': 'На новую цель', 'current_amount': 0.0, 'target_amount': 10000.0}
    
    settings_data = {
        'min_amount': settings.min_amount,
        'tts_enabled': settings.tts_enabled,
        'tts_volume': settings.tts_volume
    } if settings else {'min_amount': 100.0, 'tts_enabled': True, 'tts_volume': 0.7}

    return jsonify({
        'donations': donations_list,
        'goal': goal_data,
        'settings': settings_data
    })

@app.route('/api/submit_donation', methods=['POST'])
def submit_donation():
    if not g.user:
        return jsonify({"status": "error", "message": "Неверный API-ключ."}), 401
    
    data = request.get_json()
    if not data or 'name' not in data or 'amount' not in data:
        return jsonify({"status": "error", "message": "Отсутствуют обязательные поля."}), 400
    
    user_id = g.user.id
    name = data['name']
    amount = float(data['amount'])
    message = data.get('message', '')

    new_donation = Donation(
        name=name,
        amount=amount,
        message=message,
        user_id=user_id
    )

    db.session.add(new_donation)
    
    goal = Goal.query.filter_by(user_id=user_id).first()
    if not goal:
        goal = Goal(user_id=user_id)
        db.session.add(goal)

    goal.current_amount += amount
    
    db.session.commit()
    
    broadcast(get_full_update_message(user_id), user_id)
    
    settings = Settings.query.filter_by(user_id=user_id).first()
    if settings and settings.tts_enabled and amount >= settings.min_amount:
        tts_message = f"{name} отправил {int(amount)} тенге. Сообщение: {message if message else 'без сообщения'}"
        trigger_tts(tts_message, user_id)
    
    # Показываем алерт если сумма больше минимальной
    if settings and amount >= settings.min_amount:
        donation_data = {
            "id": new_donation.id,
            "name": name,
            "amount": amount,
            "message": message
        }
        broadcast({"type": "show_alert", "data": donation_data}, user_id)
    
    return jsonify({"status": "success", "message": "Донат успешно добавлен."}), 200

@app.route('/api/update_goal', methods=['POST'])
@login_required
def update_goal():
    user_id = current_user.id
    data = request.get_json()
    goal = Goal.query.filter_by(user_id=user_id).first()
    if not goal:
        goal = Goal(user_id=user_id)
        db.session.add(goal)
    
    goal.title = data.get('title', goal.title)
    goal.target_amount = float(data.get('target', goal.target_amount))
    db.session.commit()
    
    broadcast(get_full_update_message(user_id), user_id)
    return jsonify({"status": "success", "message": "Цель обновлена."})

@app.route('/api/update_settings', methods=['POST'])
@login_required
def update_settings():
    user_id = current_user.id
    data = request.get_json()
    settings = Settings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = Settings(user_id=user_id)
        db.session.add(settings)
    
    settings.min_amount = float(data.get('min_amount', settings.min_amount))
    settings.tts_enabled = bool(data.get('tts_enabled', settings.tts_enabled))
    settings.tts_volume = float(data.get('tts_volume', settings.tts_volume))
    db.session.commit()
    
    broadcast(get_full_update_message(user_id), user_id)
    return jsonify({"status": "success", "message": "Настройки обновлены."})

@app.route('/api/add_manual_donation', methods=['POST'])
@login_required
def add_manual_donation():
    data = request.get_json()
    if not data or 'name' not in data or 'amount' not in data:
        return jsonify({"status": "error", "message": "Отсутствуют обязательные поля."}), 400
    
    user_id = current_user.id
    name = data['name']
    amount = float(data['amount'])
    message = data.get('message', '')

    new_donation = Donation(
        name=name,
        amount=amount,
        message=message,
        user_id=user_id
    )

    db.session.add(new_donation)
    
    goal = Goal.query.filter_by(user_id=user_id).first()
    if not goal:
        goal = Goal(user_id=user_id)
        db.session.add(goal)
    goal.current_amount += amount
    
    db.session.commit()
    
    broadcast(get_full_update_message(user_id), user_id)
    
    return jsonify({"status": "success", "message": "Донат успешно добавлен.", "donation": {'id': new_donation.id, 'name': new_donation.name, 'amount': new_donation.amount, 'message': new_donation.message, 'timestamp': new_donation.timestamp.isoformat()}})


@app.route('/api/reset_donations', methods=['POST'])
@login_required
def reset_donations():
    user_id = current_user.id
    Goal.query.filter_by(user_id=user_id).update({'current_amount': 0.0})
    Donation.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    
    broadcast(get_full_update_message(user_id), user_id)
    return jsonify({"status": "success", "message": "Все донаты сброшены."})


@app.route('/api/delete_donation/<int:donation_id>', methods=['POST'])
@login_required
def delete_donation(donation_id):
    user_id = current_user.id
    donation = Donation.query.filter_by(id=donation_id, user_id=user_id).first()
    if donation:
        goal = Goal.query.filter_by(user_id=user_id).first()
        goal.current_amount -= donation.amount
        db.session.delete(donation)
        db.session.commit()
        broadcast(get_full_update_message(user_id), user_id)
        return jsonify({"status": "success", "message": f"Донат #{donation_id} удален."})
    return jsonify({"status": "error", "message": "Донат не найден."}), 404


@app.route('/api/replay_donation/<int:donation_id>', methods=['POST'])
@login_required
def replay_donation(donation_id):
    user_id = current_user.id
    donation = Donation.query.filter_by(id=donation_id, user_id=user_id).first()
    if donation:
        # Показываем алерт
        donation_data = {
            "id": donation.id,
            "name": donation.name,
            "amount": float(donation.amount),
            "message": donation.message
        }
        broadcast({'type': 'show_alert', 'data': donation_data}, user_id)
        
        # Воспроизводим TTS если включен
        settings = Settings.query.filter_by(user_id=user_id).first()
        if settings and settings.tts_enabled:
            tts_message = f"{donation.name} отправил {int(donation.amount)} тенге. Сообщение: {donation.message if donation.message else 'без сообщения'}"
            trigger_tts(tts_message, user_id)
        
        return jsonify({"status": "success", "message": "Оповещение повторно отправлено."})
    return jsonify({"status": "error", "message": "Донат не найден."}), 404

@app.route('/api/test_donation', methods=['POST'])
@login_required
def test_donation_api():
    user_id = current_user.id
    
    # Создаем тестовый донат
    test_donation_data = Donation(
        name='Тестер',
        amount=100.0,
        message='Это тестовый донат для проверки оповещений!',
        user_id=user_id
    )
    
    db.session.add(test_donation_data)
    
    # Обновляем цель
    goal = Goal.query.filter_by(user_id=user_id).first()
    if not goal:
        goal = Goal(user_id=user_id)
        db.session.add(goal)
    goal.current_amount += 100.0
    
    db.session.commit()
    
    # Отправляем обновления
    broadcast(get_full_update_message(user_id), user_id)
    
    # Показываем алерт
    donation_data = {
        "id": test_donation_data.id,
        "name": 'Тестер',
        "amount": 100.0,
        "message": 'Это тестовый донат для проверки оповещений!'
    }
    broadcast({'type': 'show_alert', 'data': donation_data}, user_id)
    
    # TTS если включен
    settings = Settings.query.filter_by(user_id=user_id).first()
    if settings and settings.tts_enabled:
        tts_message = "Тестер отправил 100 тенге. Сообщение: Это тестовый донат для проверки оповещений!"
        trigger_tts(tts_message, user_id)
    
    return jsonify({"status": "success", "message": "Тестовый донат добавлен."})

@app.route('/api/get_phone_status', methods=['GET'])
@login_required
def get_phone_status():
    return jsonify(PHONE_STATUS)

@app.route('/api/update_phone_status', methods=['POST'])
def update_phone_status():
    if not g.user:
        return jsonify({"status": "error", "message": "Неверный API-ключ."}), 401
    
    data = request.get_json()
    if data:
        PHONE_STATUS.update(data)
        # Отправляем обновление статуса всем пользователям этого агента
        broadcast({"type": "phone_status_update", "data": PHONE_STATUS}, g.user.id)
    
    return jsonify({"status": "success"})


# --- Раздача файлов ---
@app.route('/tts_cache/<path:filename>')
def serve_tts_cache(filename):
    return send_from_directory(TTS_CACHE_DIR, filename)

@app.route('/static/media/<path:filename>')
def serve_media_files(filename):
    return send_from_directory(os.path.join(basedir, 'static', 'media'), filename)

# --- Маршруты для виджетов ---
@app.route('/alert/<int:user_id>')
def alert_widget(user_id):
    return render_template('alert.html', user_id=user_id)

@app.route('/goal/<int:user_id>')
def goal_widget(user_id):
    return render_template('goal.html', user_id=user_id)

@app.route('/latest_donations/<int:user_id>')
def latest_donations_widget(user_id):
    return render_template('latest_donations.html', user_id=user_id)
    
@app.route('/top_donators/<int:user_id>')
def top_donators_widget(user_id):
    return render_template('top_donators.html', user_id=user_id)


# WebSocket
@sock.route('/ws')
def ws_route(ws):
    user_id = request.args.get('user_id')
    if not user_id:
        ws.close()
        return

    try:
        ws.user_id = int(user_id)
        app.clients.add(ws)
        ws.send(json.dumps(get_full_update_message(ws.user_id), ensure_ascii=False))
        while True:
            data = ws.receive()
            if data is None: 
                break
    except Exception:
        pass
    finally:
        app.clients.remove(ws)


# --- Запуск приложения ---
if __name__ == '__main__':
    # Создаем папки если их нет
    if not os.path.exists(os.path.join(basedir, 'static', 'media')):
        os.makedirs(os.path.join(basedir, 'static', 'media'))
        print(f"ℹ️  Создана папка 'static/media' для ваших звуков и GIF.")
    
    with app.app_context():
        db.create_all()
    
    # Автооткрытие браузера только в локальной разработке
    if os.getenv('RENDER') != 'true':
        threading.Timer(1, lambda: webbrowser.open('http://127.0.0.1:5000/')).start()
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.getenv('RENDER') != 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
