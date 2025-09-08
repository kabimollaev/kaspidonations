# --- ИСПРАВЛЕНИЕ ДЛЯ СОВМЕСТИМОСТИ С GEVENT ---
from gevent import monkey
monkey.patch_all()

import time
import uuid
import os
import json
import webbrowser
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sock import Sock
from gtts import gTTS
from datetime import datetime, timedelta
import gevent
from functools import wraps
from sqlalchemy import func

# --- Настройка путей ---
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Конфигурация приложения ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key_12345')
# ИЗМЕНЕНИЕ: Используем environment-переменную DATABASE_URL для PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(basedir, 'instance', 'database.db')}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Создаем папки при старте, если их нет
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
TTS_CACHE_DIR = os.path.join(basedir, 'tts_cache')
os.makedirs(TTS_CACHE_DIR, exist_ok=True)
os.makedirs(os.path.join(basedir, 'static', 'media'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
sock = Sock(app)

# Хранилище для WebSocket клиентов и статуса Phone Link
clients = {}
PHONE_STATUS = {}

# --- Модели Базы Данных ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    status = db.Column(db.String(20), nullable=False, default='inactive')
    api_key = db.Column(db.String(120), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    trial_end_date = db.Column(db.DateTime, nullable=True) # Новое поле для пробного периода
    donations = db.relationship('Donation', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    goal = db.relationship('Goal', backref='user', uselist=False, lazy=True, cascade="all, delete-orphan")
    settings = db.relationship('Settings', backref='user', uselist=False, lazy=True, cascade="all, delete-orphan")

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
    # НОВЫЕ ПОЛЯ ДЛЯ КАСТОМИЗАЦИИ ВИДЖЕТОВ
    alert_preset = db.Column(db.String(50), nullable=False, default='kaspi_default')
    sound_preset = db.Column(db.String(50), nullable=False, default='default')
    alert_custom_url = db.Column(db.String(255), nullable=True)
    sound_custom_url = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)


# Константы для готовых пресетов
ALERT_PRESETS = {
    'kaspi_default': {'name': 'Kaspi (по умолчанию)', 'url': '/static/media/alert.gif'},
    'money_stack': {'name': 'Пачка денег', 'url': 'https://media.giphy.com/media/l4pTsh45Dg7mwfLgA/giphy.gif'},
    'cheering_crowd': {'name': 'Аплодирующая толпа', 'url': 'https://media.giphy.com/media/3o7aCWJavAgtNEpblK/giphy.gif'},
    'fire_animation': {'name': 'Анимация огня', 'url': 'https://media.giphy.com/media/l4pT4f1B6lM4sT6tO/giphy.gif'},
    'gold_explosion': {'name': 'Взрыв золота', 'url': 'https://media.giphy.com/media/3o7aCWJavAgtNEpblK/giphy.gif'},
}

SOUND_PRESETS = {
    'default': {'name': 'Классический звук', 'url': '/static/media/alert.mp3'},
    'cash_register': {'name': 'Кассовый аппарат', 'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'},
    'fanfare': {'name': 'Фанфары', 'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3'},
}

# --- Вспомогательные функции ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.context_processor
def inject_cache_buster():
    return dict(cache_buster=int(time.time()))

def get_donation_stats(user_id):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    total_donations_count = Donation.query.filter_by(user_id=user_id).count()
    total_donations_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).scalar() or 0
    
    today_donations_count = Donation.query.filter_by(user_id=user_id).filter(Donation.timestamp >= today_start).count()
    today_donations_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).filter(Donation.timestamp >= today_start).scalar() or 0
    
    month_donations_count = Donation.query.filter_by(user_id=user_id).filter(Donation.timestamp >= month_start).count()
    month_donations_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).filter(Donation.timestamp >= month_start).scalar() or 0
    
    return {
        'total': {'count': total_donations_count, 'sum': total_donations_sum},
        'today': {'count': today_donations_count, 'sum': today_donations_sum},
        'month': {'count': month_donations_count, 'sum': month_donations_sum},
    }

# --- Фоновые задачи ---
def cleanup_tts_files():
    while True:
        try:
            now = datetime.now()
            for filename in os.listdir(TTS_CACHE_DIR):
                file_path = os.path.join(TTS_CACHE_DIR, filename)
                if os.path.isfile(file_path):
                    file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if now - file_mod_time > timedelta(minutes=10):
                        os.remove(file_path)
        except Exception as e:
            print(f"❌ Ошибка при очистке TTS кэша: {e}")
        gevent.sleep(60 * 15)

# --- Функции для Real-time обновлений ---
def broadcast_to_user(user_id, message_data):
    if user_id in clients:
        message_str = json.dumps(message_data, ensure_ascii=False)
        for ws in list(clients[user_id]):
            try:
                ws.send(message_str)
            except Exception:
                clients[user_id].remove(ws)

def tts_task(text, user_id):
    # ИСПРАВЛЕНИЕ: Эта функция теперь не требует контекста приложения
    try:
        tts = gTTS(text, lang='ru')
        filename_part = f'tts_{uuid.uuid4()}.mp3'
        full_path = os.path.join(TTS_CACHE_DIR, filename_part)
        tts.save(full_path)
        print(f"✅ TTS создан: {full_path}")
        # Создаем относительный URL вручную, чтобы избежать ошибки контекста
        tts_url = f"/tts_cache/{filename_part}"
        broadcast_to_user(user_id, {"type": "tts", "url": tts_url})
    except Exception as e:
        print(f"❌ Ошибка создания TTS: {e}")

def get_full_update_message(user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        if not user: return {}
        
        donations = user.donations.order_by(Donation.timestamp.desc()).all()
        goal = user.goal
        settings = user.settings

        donations_list = [{'id': d.id, 'name': d.name, 'amount': d.amount, 'message': d.message, 'timestamp': d.timestamp.isoformat()} for d in donations]
        goal_data = {'title': goal.title, 'current': goal.current_amount, 'target': goal.target_amount} if goal else {}
        settings_data = {
            'min_amount': settings.min_amount,
            'tts_enabled': settings.tts_enabled,
            'tts_volume': settings.tts_volume,
            'alert_preset': settings.alert_preset,
            'sound_preset': settings.sound_preset,
            'alert_custom_url': settings.alert_custom_url,
            'sound_custom_url': settings.sound_custom_url,
            'alert_url': ALERT_PRESETS[settings.alert_preset]['url'] if settings.alert_preset != 'custom' else settings.alert_custom_url,
            'sound_url': SOUND_PRESETS[settings.sound_preset]['url'] if settings.sound_preset != 'custom' else settings.sound_custom_url,
        } if settings else {}
        phone_status_data = PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"})

        return {"type": "full_update", "data": {"donations": donations_list, "goal": goal_data, "settings": settings_data, "phone_status": phone_status_data}}

# --- Декоратор для API ---
def check_trial_status(user):
    # Если пользователь - админ, ему всегда разрешен доступ
    if user.role == 'admin':
        return True, None
    # Если пользователь активен (платная подписка), ему разрешен доступ
    if user.status == 'active':
        return True, None
    # Если у пользователя есть пробный период, проверяем, не истек ли он
    if user.trial_end_date:
        if datetime.now() < user.trial_end_date:
            return True, user.trial_end_date
        else:
            # Пробный период истек, меняем статус на "inactive"
            user.status = 'inactive'
            db.session.commit()
            return False, 'Пробный период истек.'
    # Если пользователь не активен и нет пробного периода, доступ запрещен
    return False, 'Аккаунт неактивен.'


def api_login_required(f):
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
        
        is_allowed, message = check_trial_status(user)
        if not is_allowed:
            return jsonify({'error': message}), 403

        g.user = user
        return f(*args, **kwargs)
    return decorated_function

# --- Основные маршруты ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: 
        is_allowed, message = check_trial_status(current_user)
        if is_allowed:
            return redirect(url_for('dashboard'))
        else:
            flash(message, 'error')
            logout_user()

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            is_allowed, message = check_trial_status(user)
            if is_allowed:
                login_user(user, remember=True)
                return redirect(url_for('dashboard'))
            else:
                flash(message, 'error')
        else:
            flash('Неверный логин или пароль.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form.get('username')).first():
            flash('Имя пользователя уже занято.', 'error')
        else:
            hashed_pw = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
            new_user = User(
                username=request.form.get('username'),
                password_hash=hashed_pw,
                status='trial', # Новый статус
                trial_end_date=datetime.now() + timedelta(days=14) # Дата окончания пробного периода
            )
            db.session.add(new_user)
            db.session.commit()
            db.session.add(Goal(user_id=new_user.id))
            db.session.add(Settings(user_id=new_user.id))
            db.session.commit()
            flash('Регистрация прошла успешно! Вам предоставлен 14-дневный бесплатный период.', 'success')
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
    trial_info = None
    if current_user.status == 'trial' and current_user.trial_end_date:
        remaining_days = (current_user.trial_end_date - datetime.now()).days
        if remaining_days > 0:
            trial_info = f'До конца пробного периода осталось {remaining_days} дней.'
        else:
            trial_info = 'Ваш пробный период истек. Для продолжения работы, пожалуйста, приобретите доступ.'
    
    stats = get_donation_stats(current_user.id)
    donations_history = Donation.query.filter_by(user_id=current_user.id).order_by(Donation.timestamp.desc()).limit(10).all()
    
    return render_template('dashboard.html', user=current_user, trial_info=trial_info, stats=stats, donations_history=donations_history, ALERT_PRESETS=ALERT_PRESETS, SOUND_PRESETS=SOUND_PRESETS)

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin': return redirect(url_for('dashboard'))
    users = User.query.all()
    # ИЗМЕНЕНИЕ: Создаем дополнительную информацию для шаблона
    users_data = []
    for u in users:
        trial_days = 'N/A'
        if u.status == 'trial' and u.trial_end_date:
            remaining = u.trial_end_date - datetime.now()
            trial_days = remaining.days
        users_data.append({
            'id': u.id,
            'username': u.username,
            'role': u.role,
            'status': u.status,
            'trial_days': trial_days
        })
    return render_template('admin_panel.html', users=users_data)

@app.route('/admin/update_user/<int:user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    if current_user.role != 'admin': return redirect(url_for('dashboard'))
    user = db.session.get(User, user_id)
    if not user:
        flash(f'Пользователь с ID {user_id} не найден.', 'error')
    else:
        user.role = request.form.get('role')
        user.status = request.form.get('status')
        db.session.commit()
        flash(f'Данные пользователя {user.username} обновлены.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/extend_trial/<int:user_id>', methods=['POST'])
@login_required
def extend_trial(user_id):
    if current_user.role != 'admin': return redirect(url_for('dashboard'))
    user = db.session.get(User, user_id)
    if not user:
        flash(f'Пользователь с ID {user_id} не найден.', 'error')
    else:
        # Продлеваем пробный период на 14 дней
        new_end_date = datetime.now() + timedelta(days=14)
        if user.trial_end_date and user.trial_end_date > datetime.now():
            new_end_date = user.trial_end_date + timedelta(days=14)
        user.trial_end_date = new_end_date
        user.status = 'trial' # Возвращаем статус на "trial"
        db.session.commit()
        flash(f'Пробный период пользователя {user.username} продлен.', 'success')
    return redirect(url_for('admin_panel'))

# --- API ---
@app.route('/api/get_all_data', methods=['GET'])
@api_login_required
def get_all_data():
    user = g.user
    full_update = get_full_update_message(user.id)
    
    # Добавляем статистику в API-ответ
    full_update['data']['stats'] = get_donation_stats(user.id)
    
    return jsonify(full_update['data'])

@app.route('/api/submit_donation', methods=['POST'])
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
    if user.settings.tts_enabled and float(data['amount']) >= user.settings.min_amount:
        tts_message = f"{data['name']} отправил {int(data['amount'])} тенге. Сообщение: {data.get('message', 'без сообщения')}"
        gevent.spawn(tts_task, tts_message, user.id)
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@app.route('/api/update_widget_settings', methods=['POST'])
@api_login_required
def update_widget_settings():
    user = g.user
    data = request.json
    
    settings = user.settings or Settings(user_id=user.id)
    
    settings.alert_preset = data.get('alert_preset')
    settings.sound_preset = data.get('sound_preset')
    settings.alert_custom_url = data.get('alert_custom_url')
    settings.sound_custom_url = data.get('sound_custom_url')
    
    if not user.settings:
        db.session.add(settings)
    
    db.session.commit()
    
    broadcast_to_user(user.id, get_full_update_message(user.id))
    
    return jsonify({'status': 'success'})


@app.route('/api/update_goal', methods=['POST'])
@api_login_required
def update_goal():
    user = g.user
    data = request.json
    user.goal.title = data.get('title')
    user.goal.target_amount = float(data.get('target', 0))
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@app.route('/api/update_settings', methods=['POST'])
@api_login_required
def update_settings():
    user = g.user
    data = request.json
    user.settings.min_amount = float(data.get('min_amount', 0))
    user.settings.tts_enabled = bool(data.get('tts_enabled'))
    user.settings.tts_volume = float(data.get('tts_volume', 0.7))
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@app.route('/api/add_manual_donation', methods=['POST'])
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
    if user.settings.tts_enabled and float(data['amount']) >= user.settings.min_amount:
        tts_message = f"{data['name']} отправил {int(data['amount'])} тенге. Сообщение: {data.get('message', 'без сообщения')}"
        gevent.spawn(tts_task, tts_message, user.id)
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@app.route('/api/reset_donations', methods=['POST'])
@api_login_required
def reset_donations():
    user = g.user
    user.donations.delete()
    user.goal.current_amount = 0
    db.session.commit()
    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success'})

@app.route('/api/delete_donation/<int:donation_id>', methods=['POST'])
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

@app.route('/api/replay_donation/<int:donation_id>', methods=['POST'])
@api_login_required
def replay_donation(donation_id):
    user = g.user
    donation = db.session.get(Donation, donation_id)
    if not donation or donation.user_id != user.id:
        return jsonify({'error': 'Донат не найден'}), 404
    donation_data = {'id': donation.id, 'name': donation.name, 'amount': donation.amount, 'message': donation.message}
    broadcast_to_user(user.id, {"type": "show_alert", "data": donation_data})
    if user.settings.tts_enabled:
        tts_message = f"{donation.name} отправил {donation.amount} тенге. Сообщение: {donation.message or 'без сообщения'}"
        gevent.spawn(tts_task, tts_message, user.id)
    return jsonify({'status': 'success'})

@app.route('/api/test_donation', methods=['POST'])
@api_login_required
def test_donation_api():
    user = g.user
    test_donation_data = {'id': f"test_{int(time.time())}",'name': 'Тестер','amount': 100,'message': 'Это тестовый донат!'}
    broadcast_to_user(user.id, {"type": "show_alert", "data": test_donation_data})
    if user.settings.tts_enabled:
        tts_message = "Тестер отправил 100 тенге. Сообщение: Это тестовый донат!"
        gevent.spawn(tts_task, tts_message, user.id)
    return jsonify({'status': 'success'})

@app.route('/api/get_phone_status', methods=['GET'])
@api_login_required
def get_phone_status():
    user = g.user
    return jsonify(PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"}))

@app.route('/api/update_phone_status', methods=['POST'])
@api_login_required
def update_phone_status():
    user = g.user
    PHONE_STATUS[user.id] = request.json
    broadcast_to_user(user.id, {"type": "phone_status_update", "data": PHONE_STATUS[user.id]})
    return jsonify({'status': 'success'})


# --- Маршруты для виджетов и файлов ---
@app.route('/alert/<int:user_id>')
def alert_widget(user_id):
    # Добавляем проверку статуса пользователя для виджетов
    user = User.query.get(user_id)
    if not user:
        return "Пользователь не найден", 404
    is_allowed, message = check_trial_status(user)
    if not is_allowed:
        return f"Доступ запрещен. {message}", 403
    return render_template('alert.html', user_id=user_id)

@app.route('/goal/<int:user_id>')
def goal_widget(user_id):
    user = User.query.get(user_id)
    if not user:
        return "Пользователь не найден", 404
    is_allowed, message = check_trial_status(user)
    if not is_allowed:
        return f"Доступ запрещен. {message}", 403
    return render_template('goal.html', user_id=user_id)

@app.route('/top_donators/<int:user_id>')
def top_donators_widget(user_id):
    user = User.query.get(user_id)
    if not user:
        return "Пользователь не найден", 404
    is_allowed, message = check_trial_status(user)
    if not is_allowed:
        return f"Доступ запрещен. {message}", 403
    return render_template('top_donators.html', user_id=user_id)

@app.route('/latest_donations/<int:user_id>')
def latest_donations_widget(user_id):
    user = User.query.get(user_id)
    if not user:
        return "Пользователь не найден", 404
    is_allowed, message = check_trial_status(user)
    if not is_allowed:
        return f"Доступ запрещен. {message}", 403
    return render_template('latest_donations.html', user_id=user_id)
    
@app.route('/latest_donations_popout/<int:user_id>')
def latest_donations_popout(user_id):
    user = User.query.get(user_id)
    if not user:
        return "Пользователь не найден", 404
    is_allowed, message = check_trial_status(user)
    if not is_allowed:
        return f"Доступ запрещен. {message}", 403
    return render_template('latest_donations_popout.html', user_id=user_id)

@app.route('/tts_cache/<path:filename>')
def serve_tts_cache(filename):
    return send_from_directory(TTS_CACHE_DIR, filename)

@app.route('/static/media/<path:filename>')
def serve_media_files(filename):
    return send_from_directory(os.path.join(basedir, 'static', 'media'), filename)

# --- WebSocket ---
@sock.route('/ws')
def ws(ws):
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        if current_user.is_authenticated:
            user_id = current_user.id
        else: return
        
    user = User.query.get(user_id)
    if not user:
        ws.close()
        return

    is_allowed, message = check_trial_status(user)
    if not is_allowed:
        # Отправляем сообщение об ошибке, если пробный период истек
        try:
            ws.send(json.dumps({"type": "error", "message": message}))
        except Exception:
            pass
        ws.close()
        return
        
    if user_id not in clients:
        clients[user_id] = set()
    clients[user_id].add(ws)
    print(f"🔗 WebSocket client connected for user {user_id}. Total: {len(clients[user_id])}")
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

# --- Запуск ---
if __name__ != '__main__':
    gevent.spawn(cleanup_tts_files)
    with app.app_context():
        db.create_all() # Создает все таблицы, если их нет
