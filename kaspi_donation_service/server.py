import time
import uuid
import os
import json
import webbrowser
import threading
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sock import Sock
from gtts import gTTS
from datetime import datetime

# --- Настройка путей ---
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Конфигурация приложения ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key_12345')
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

# Хранилище для WebSocket клиентов
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
    donations = db.relationship('Donation', backref='user', lazy=True, cascade="all, delete-orphan")
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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)

@login_manager.user_loader
def load_user(user_id):
    # This function should not have a legacy warning.
    # Using Session.get() is the modern approach.
    return db.session.get(User, int(user_id))


@app.context_processor
def inject_cache_buster():
    return dict(cache_buster=int(time.time()))

# --- Функции для Real-time обновлений ---
def broadcast_to_user(user_id, message_data):
    if user_id in clients:
        message_str = json.dumps(message_data, ensure_ascii=False)
        for ws in list(clients[user_id]):
            try:
                ws.send(message_str)
            except Exception as e:
                print(f"❌ Не удалось отправить WebSocket сообщение клиенту пользователя {user_id}: {e}")
                clients[user_id].remove(ws)

def trigger_tts(text, user_id):
    with app.app_context():
        try:
            tts = gTTS(text, lang='ru')
            filename_part = f'tts_{uuid.uuid4()}.mp3'
            full_path = os.path.join(TTS_CACHE_DIR, filename_part)
            tts.save(full_path)
            print(f"✅ TTS создан: {full_path}")
            tts_url = url_for('serve_tts_cache', filename=filename_part, _external=True)
            broadcast_to_user(user_id, {"type": "tts", "url": tts_url})
        except Exception as e:
            print(f"❌ Ошибка создания TTS: {e}")

def get_full_update_message(user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        if not user: return {}
        
        donations = Donation.query.filter_by(user_id=user.id).order_by(Donation.timestamp.desc()).all()
        goal = user.goal
        settings = user.settings

        donations_list = [{'id': d.id, 'name': d.name, 'amount': d.amount, 'message': d.message, 'timestamp': d.timestamp.isoformat()} for d in donations]
        goal_data = {'title': goal.title, 'current': goal.current_amount, 'target': goal.target_amount} if goal else {}
        settings_data = {'min_amount': settings.min_amount, 'tts_enabled': settings.tts_enabled, 'tts_volume': settings.tts_volume} if settings else {}
        phone_status_data = PHONE_STATUS.get(user.id, {"connected": False, "message": "Нет данных"})

        return {"type": "full_update", "data": {"donations": donations_list, "goal": goal_data, "settings": settings_data, "phone_status": phone_status_data}}

# --- Маршруты ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            if user.status == 'active':
                login_user(user, remember=True)
                return redirect(url_for('dashboard'))
            else:
                flash('Ваш аккаунт неактивен.', 'error')
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
            new_user = User(username=request.form.get('username'), password_hash=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            
            db.session.add(Goal(user_id=new_user.id))
            db.session.add(Settings(user_id=new_user.id))
            db.session.commit()

            flash('Регистрация прошла успешно! Ожидайте активации.', 'success')
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
    return render_template('dashboard.html', user=current_user)

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin': return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('admin_panel.html', users=users)

@app.route('/admin/update_user/<int:user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    if current_user.role != 'admin': return redirect(url_for('dashboard'))
    user = db.session.get(User, user_id)
    if not user:
        flash(f'Пользователь с ID {user_id} не найден.', 'error')
        return redirect(url_for('admin_panel'))
    user.role = request.form.get('role')
    user.status = request.form.get('status')
    db.session.commit()
    flash(f'Данные пользователя {user.username} обновлены.', 'success')
    return redirect(url_for('admin_panel'))

# --- API ---
@app.before_request
def before_request_api():
    if request.path.startswith('/api/'):
        # ИСПРАВЛЕНИЕ: Сначала проверяем аутентификацию по сессии.
        # Если пользователь уже залогинен, ничего не делаем.
        if current_user.is_authenticated:
            return

        # Если сессии нет, тогда проверяем API ключ (для agent.py)
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key:
            return jsonify({'error': 'Доступ запрещен. Требуется аутентификация.'}), 401
        
        user = User.query.filter_by(api_key=api_key).first()
        if not user or user.status != 'active':
            return jsonify({'error': 'Неверный API-ключ или пользователь неактивен.'}), 403
        
        g.user = user

@app.route('/api/get_all_data')
@login_required
def get_all_data():
    return jsonify(get_full_update_message(current_user.id)['data'])

@app.route('/api/submit_donation', methods=['POST'])
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
        threading.Thread(target=trigger_tts, args=(tts_message, user.id)).start()

    broadcast_to_user(user.id, get_full_update_message(user.id))
    return jsonify({'status': 'success', 'message': 'Донат успешно добавлен.'})

@app.route('/api/update_goal', methods=['POST'])
@login_required
def update_goal():
    data = request.json
    current_user.goal.title = data.get('title')
    current_user.goal.target_amount = float(data.get('target', 0))
    db.session.commit()
    broadcast_to_user(current_user.id, get_full_update_message(current_user.id))
    return jsonify({'status': 'success'})

@app.route('/api/update_settings', methods=['POST'])
@login_required
def update_settings():
    data = request.json
    current_user.settings.min_amount = float(data.get('min_amount', 0))
    current_user.settings.tts_enabled = bool(data.get('tts_enabled'))
    current_user.settings.tts_volume = float(data.get('tts_volume', 0.7))
    db.session.commit()
    broadcast_to_user(current_user.id, get_full_update_message(current_user.id))
    return jsonify({'status': 'success'})

@app.route('/api/add_manual_donation', methods=['POST'])
@login_required
def add_manual_donation():
    data = request.json
    donation = Donation(name=data['name'], amount=float(data['amount']), message=data.get('message'), user_id=current_user.id)
    db.session.add(donation)
    current_user.goal.current_amount += float(data['amount'])
    db.session.commit()
    broadcast_to_user(current_user.id, get_full_update_message(current_user.id))
    return jsonify({'status': 'success'})

@app.route('/api/reset_donations', methods=['POST'])
@login_required
def reset_donations():
    Donation.query.filter_by(user_id=current_user.id).delete()
    current_user.goal.current_amount = 0
    db.session.commit()
    broadcast_to_user(current_user.id, get_full_update_message(current_user.id))
    return jsonify({'status': 'success'})

@app.route('/api/delete_donation/<int:donation_id>', methods=['POST'])
@login_required
def delete_donation(donation_id):
    donation = db.session.get(Donation, donation_id)
    if not donation or donation.user_id != current_user.id:
        return jsonify({'error': 'Donation not found or unauthorized'}), 404
    current_user.goal.current_amount -= donation.amount
    db.session.delete(donation)
    db.session.commit()
    broadcast_to_user(current_user.id, get_full_update_message(current_user.id))
    return jsonify({'status': 'success'})

@app.route('/api/replay_donation/<int:donation_id>', methods=['POST'])
@login_required
def replay_donation(donation_id):
    donation = db.session.get(Donation, donation_id)
    if not donation or donation.user_id != current_user.id:
        return jsonify({'error': 'Donation not found or unauthorized'}), 404
    donation_data = {'id': donation.id, 'name': donation.name, 'amount': donation.amount, 'message': donation.message}
    broadcast_to_user(current_user.id, {"type": "show_alert", "data": donation_data})
    if current_user.settings.tts_enabled:
        tts_message = f"{donation.name} отправил {int(donation.amount)} тенге. Сообщение: {donation.message or 'без сообщения'}"
        threading.Thread(target=trigger_tts, args=(tts_message, current_user.id)).start()
    return jsonify({'status': 'success'})

@app.route('/api/test_donation', methods=['POST'])
@login_required
def test_donation_api():
    test_donation_data = {
        'id': int(time.time()),
        'name': 'Тестер',
        'amount': 100,
        'message': 'Это тестовый донат для проверки оповещений!'
    }
    broadcast_to_user(current_user.id, {"type": "show_alert", "data": test_donation_data})
    if current_user.settings.tts_enabled:
        tts_message = f"Тестер отправил 100 тенге. Сообщение: Это тестовый донат для проверки оповещений!"
        threading.Thread(target=trigger_tts, args=(tts_message, current_user.id)).start()
    return jsonify({'status': 'success'})

@app.route('/api/get_phone_status')
@login_required
def get_phone_status():
    return jsonify(PHONE_STATUS.get(current_user.id, {"connected": False, "message": "Нет данных"}))

@app.route('/api/update_phone_status', methods=['POST'])
def update_phone_status():
    user = g.user
    PHONE_STATUS[user.id] = request.json
    broadcast_to_user(user.id, {"type": "phone_status_update", "data": PHONE_STATUS[user.id]})
    return jsonify({'status': 'success'})

# --- ВИДЖЕТЫ ---
@app.route('/alert/<int:user_id>')
def alert_widget(user_id):
    return render_template('alert.html', user_id=user_id)

@app.route('/goal/<int:user_id>')
def goal_widget(user_id):
    return render_template('goal.html', user_id=user_id)

@app.route('/top_donators/<int:user_id>')
def top_donators_widget(user_id):
    return render_template('top_donators.html', user_id=user_id)

@app.route('/latest_donations/<int:user_id>')
def latest_donations_widget(user_id):
    return render_template('latest_donations.html', user_id=user_id)
    
@app.route('/latest_donations_popout/<int:user_id>')
def latest_donations_popout(user_id):
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
    # ИСПРАВЛЕНИЕ: Определяем user_id по сессии, если он не передан в URL
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            ws.close(reason=1008, message="User ID is required")
            return

    if user_id not in clients:
        clients[user_id] = set()
    clients[user_id].add(ws)
    print(f"🔗 WebSocket client connected for user {user_id}. Total: {len(clients[user_id])}")

    try:
        initial_data = get_full_update_message(user_id)
        ws.send(json.dumps(initial_data, ensure_ascii=False))

        while not ws.closed:
            message = ws.receive(timeout=30)
            if message is None:
                ws.send(json.dumps({"type": "heartbeat"}))
    except Exception as e:
        print(f"WebSocket error for user {user_id}: {e}")
    finally:
        if user_id in clients and ws in clients[user_id]:
            clients[user_id].remove(ws)
            if not clients[user_id]:
                del clients[user_id]
        print(f"🔌 WebSocket client disconnected for user {user_id}.")

# --- Запуск ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    if os.getenv('RENDER') != 'true':
        webbrowser.open('http://127.0.0.1:5000/')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=os.getenv('RENDER') != 'true')

