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
# Ключ - user_id, значение - set с объектами ws
clients = {}

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
    return User.query.get(int(user_id))

@app.context_processor
def inject_cache_buster():
    return dict(cache_buster=int(time.time()))

# --- Функции для Real-time обновлений ---
def broadcast_to_user(user_id, message_data):
    if user_id in clients:
        message_str = json.dumps(message_data, ensure_ascii=False)
        # Создаем копию сета, чтобы избежать ошибок при изменении сета во время итерации
        for ws in list(clients[user_id]):
            try:
                ws.send(message_str)
            except Exception as e:
                print(f"❌ Не удалось отправить WebSocket сообщение клиенту пользователя {user_id}: {e}")
                # Удаляем "мертвое" соединение
                clients[user_id].remove(ws)

def trigger_tts(text, user_id):
    with app.app_context():
        try:
            tts = gTTS(text, lang='ru')
            # Используем uuid для уникальности имени файла
            filename_part = f'tts_{uuid.uuid4()}.mp3'
            full_path = os.path.join(TTS_CACHE_DIR, filename_part)
            tts.save(full_path)
            print(f"✅ TTS создан: {full_path}")
            
            # Собираем URL для клиента
            tts_url = url_for('serve_tts_cache', filename=filename_part, _external=True)
            
            broadcast_to_user(user_id, {"type": "tts", "url": tts_url})
        except Exception as e:
            print(f"❌ Ошибка создания TTS: {e}")

def get_full_update_message(user_id):
    with app.app_context():
        user = User.query.get(user_id)
        if not user: return {}
        
        donations = user.donations.order_by(Donation.timestamp.desc()).all()
        goal = user.goal
        settings = user.settings

        donations_list = [{'id': d.id, 'name': d.name, 'amount': d.amount, 'message': d.message, 'timestamp': d.timestamp.isoformat()} for d in donations]
        goal_data = {'title': goal.title, 'current': goal.current_amount, 'target': goal.target_amount} if goal else {}
        settings_data = {'min_amount': settings.min_amount, 'tts_enabled': settings.tts_enabled, 'tts_volume': settings.tts_volume} if settings else {}
        
        return {"type": "full_update", "data": {"donations": donations_list, "goal": goal_data, "settings": settings_data}}

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
    user = User.query.get_or_404(user_id)
    user.role = request.form.get('role')
    user.status = request.form.get('status')
    db.session.commit()
    flash(f'Данные пользователя {user.username} обновлены.', 'success')
    return redirect(url_for('admin_panel'))

# --- API ---
# ... (API routes are correct and don't need changes)

# --- ВИДЖЕТЫ (ИСПРАВЛЕНО) ---
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


# --- WebSocket Route ---
@sock.route('/ws')
def ws(ws):
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        ws.close(reason=1008, message="User ID is required")
        return

    # Регистрация клиента
    if user_id not in clients:
        clients[user_id] = set()
    clients[user_id].add(ws)
    print(f"🔗 WebSocket client connected for user {user_id}. Total clients for user: {len(clients[user_id])}")

    try:
        # Отправляем начальное состояние
        initial_data = get_full_update_message(user_id)
        ws.send(json.dumps(initial_data, ensure_ascii=False))

        # Держим соединение открытым
        while not ws.closed:
            # Просто ждем, можно добавить обработку входящих сообщений при необходимости
            message = ws.receive(timeout=30) # timeout to prevent indefinite blocking
            if message is None: # timeout occurred
                ws.send(json.dumps({"type": "heartbeat"}))
    
    except Exception as e:
        print(f"WebSocket error for user {user_id}: {e}")
    finally:
        # Удаление клиента при отключении
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

