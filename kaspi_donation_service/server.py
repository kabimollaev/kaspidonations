import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import phonenumbers
import requests
from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   session, url_for)
from flask_login import (LoginManager, current_user, login_required, login_user,
                         logout_user)
from flask_sqlalchemy import SQLAlchemy
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash

# Инициализация приложения
app = Flask(__name__, static_url_path='/static', static_folder='static')

# Настройка секретного ключа
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Настройка базы данных
# Use the environment variable, or fall back to a local path (for development)
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL is None:
    # If DATABASE_URL is not set, use a local SQLite database for local development
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'site.db')
    app.logger.warning("Using local SQLite database. Set DATABASE_URL for production.")
elif DATABASE_URL.startswith("postgres://"):
    # Convert 'postgres://' to 'postgresql://' for SQLAlchemy 
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Увеличение кэш-бастера для статических файлов
cache_buster = int(datetime.now().timestamp())

# Настройки оповещений и звуков
ALERT_PRESETS = {
    'default': {'name': 'Default GIF', 'url': url_for('static', filename='media/alert.gif', v=cache_buster)},
    'money': {'name': 'Money GIF', 'url': 'https://media.giphy.com/media/l4pTsh4PFRzVf0l7tv/giphy.gif'},
    'cat': {'name': 'Cat GIF', 'url': 'https://media.giphy.com/media/JTVRBPxJ3xG3C/giphy.gif'},
    'explosion': {'name': 'Explosion GIF', 'url': 'https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMTA4ZGlrOWZpZmszNjV4MnRrdjJzZWVqOGU3M3g3YTh0Y3Q2NWZhbCZlcD12MV9pbnRlcm5hbF9naWYmY3Q9Zw/3osxYfV1JgGv7tQhG0/giphy.gif'},
}

SOUND_PRESETS = {
    'default': {'name': 'Default MP3', 'url': url_for('static', filename='media/alert.mp3', v=cache_buster)},
    'coin': {'name': 'Coin Sound', 'url': 'https://cdn.pixabay.com/audio/2022/03/10/audio_f55152ccac.mp3'},
    'bell': {'name': 'Bell Sound', 'url': 'https://cdn.pixabay.com/audio/2022/03/10/audio_33a010d80c.mp3'},
}

# Определение моделей
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    role = db.Column(db.String(10), default='user')  # 'user' or 'admin'
    status = db.Column(db.String(10), default='active') # 'active' or 'inactive'
    
    # Связи
    donations = db.relationship('Donation', backref='donor', lazy=True)
    settings = db.relationship('Settings', backref='owner', uselist=False, lazy=True)
    goal = db.relationship('Goal', backref='goal_owner', uselist=False, lazy=True)

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.api_key is None:
            self.api_key = secrets.token_urlsafe(32)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_active(self):
        return self.status == 'active'

    def get_id(self):
        return str(self.id)

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), default='Аноним')
    amount = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)
    
    # Поля для статистики
    date = db.Column(db.Date, default=datetime.now(timezone.utc).date()) # Для удобства агрегации

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    min_amount = db.Column(db.Float, default=100.0)
    tts_enabled = db.Column(db.Boolean, default=False)
    tts_volume = db.Column(db.Float, default=0.7)
    
    # Настройки кастомизации
    font_family = db.Column(db.String(50), default='Inter')
    title_color = db.Column(db.String(7), default='#ffffff')
    highlight_color = db.Column(db.String(7), default='#ffcc00')
    message_color = db.Column(db.String(7), default='#ffffff')
    alert_preset = db.Column(db.String(50), default='default')
    alert_custom_url = db.Column(db.String(255), nullable=True)
    sound_preset = db.Column(db.String(50), default='default')
    sound_custom_url = db.Column(db.String(255), nullable=True)
    
class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    title = db.Column(db.String(100), default='Сбор на новую камеру')
    target_amount = db.Column(db.Float, default=10000.0)

# Функции-помощники
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def calculate_stats(user_id):
    """Рассчитывает статистику донатов для конкретного пользователя."""
    today = datetime.now(timezone.utc).date()
    start_of_month = today.replace(day=1)
    
    # Суммы
    total_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).scalar() or 0.0
    today_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id, date=today).scalar() or 0.0
    month_sum = db.session.query(func.sum(Donation.amount)).filter(
        Donation.user_id == user_id,
        Donation.date >= start_of_month
    ).scalar() or 0.0
    
    # Количество
    total_count = db.session.query(Donation).filter_by(user_id=user_id).count()
    today_count = db.session.query(Donation).filter_by(user_id=user_id, date=today).count()
    month_count = db.session.query(Donation).filter(
        Donation.user_id == user_id,
        Donation.date >= start_of_month
    ).count()

    return {
        'total': {'sum': total_sum, 'count': total_count},
        'today': {'sum': today_sum, 'count': today_count},
        'month': {'sum': month_sum, 'count': month_count}
    }

# Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Маршруты
@app.before_first_request
def create_db():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html', cache_buster=cache_buster)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form_data = session.pop('register_form_data', {})
    error = session.pop('register_error', None)
    
    if request.method == 'POST':
        # Сброс сессии перед обработкой, чтобы избежать конфликтов
        logout_user() 
        session.clear()

        username = request.form.get('username')
        password = request.form.get('password')
        phone = request.form.get('phone') # Не используется, но собирается для формы

        session['register_form_data'] = request.form

        if not username or not password:
            session['register_error'] = 'Имя пользователя и пароль обязательны.'
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            session['register_error'] = 'Имя пользователя уже занято.'
            return redirect(url_for('register'))

        try:
            new_user = User(username=username)
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            # Инициализация настроек и цели
            new_settings = Settings(user_id=new_user.id)
            new_goal = Goal(user_id=new_user.id)
            db.session.add(new_settings)
            db.session.add(new_goal)
            db.session.commit()
            
            login_user(new_user)
            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Registration failed: {e}")
            session['register_error'] = 'Произошла ошибка при регистрации.'
            return redirect(url_for('register'))

    return render_template('register.html', error=error, form_data=form_data, cache_buster=cache_buster)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = session.pop('login_error', None)
    
    if request.method == 'POST':
        # Сброс сессии перед обработкой, чтобы избежать конфликтов
        logout_user() 
        session.clear()

        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if user.status == 'inactive':
                session['login_error'] = 'Ваш аккаунт не активен. Обратитесь к администратору.'
                return redirect(url_for('login'))
            
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            session['login_error'] = 'Неверное имя пользователя или пароль.'
            return redirect(url_for('login'))

    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    return render_template('login.html', error=error, cache_buster=cache_buster)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear() # Полная очистка сессии
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Проверка на наличие настроек/цели, если они не инициализировались (например, после db.drop_all)
    if not current_user.settings:
        new_settings = Settings(user_id=current_user.id)
        db.session.add(new_settings)
        db.session.commit()
        
    if not current_user.goal:
        new_goal = Goal(user_id=current_user.id)
        db.session.add(new_goal)
        db.session.commit()
        
    # --- НАЧАЛО ДИАГНОСТИКИ: Получение глобальной статистики ---
    # Мы получим общую сумму всех донатов в базе данных, чтобы сравнить ее с суммой пользователя.
    try:
        global_total_sum = db.session.query(func.sum(Donation.amount)).scalar()
        if global_total_sum is None:
            global_total_sum = 0.0
    except Exception as e:
        app.logger.error(f"Error calculating global total sum: {e}")
        global_total_sum = -1.0 # Индикатор ошибки
    
    # Получение статистики только для текущего пользователя (стандартная логика)
    stats = calculate_stats(current_user.id)
    
    # Добавление глобальной суммы в stats для удобства передачи в шаблон
    stats['global_total_sum'] = global_total_sum
    # --- КОНЕЦ ДИАГНОСТИКИ ---
    
    trial_info = None # Убрали логику триала
    
    return render_template('dashboard.html', user=current_user, trial_info=trial_info, 
                           stats=stats, # stats теперь содержит 'global_total_sum'
                           ALERT_PRESETS=ALERT_PRESETS, SOUND_PRESETS=SOUND_PRESETS,
                           cache_buster=cache_buster)

@app.route('/api/v1/ping', methods=['GET'])
def api_ping():
    api_key = request.args.get('api_key')
    user = User.query.filter_by(api_key=api_key).first()
    
    if user:
        return jsonify({'status': 'ok', 'user_id': user.id}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Invalid API Key'}), 401

@app.route('/api/v1/update_status', methods=['POST'])
def update_status():
    data = request.json
    api_key = data.get('api_key')
    new_status = data.get('status')
    
    user = User.query.filter_by(api_key=api_key).first()
    
    if user and new_status in ['connected', 'disconnected']:
        # Временная логика для простого индикатора
        if new_status == 'connected':
             # Обновляем статус в сессии или используем кэш
             # Здесь мы просто возвращаем 'ok' для агента
             return jsonify({'status': 'ok'}), 200
        elif new_status == 'disconnected':
            # Здесь мы просто возвращаем 'ok' для агента
            return jsonify({'status': 'ok'}), 200
    
    return jsonify({'status': 'error', 'message': 'Invalid API Key or status'}), 400

@app.route('/api/v1/donation', methods=['POST'])
def api_donation():
    data = request.json
    api_key = data.get('api_key')
    name = data.get('name', 'Аноним')
    amount = data.get('amount')
    message = data.get('message', '')

    user = User.query.filter_by(api_key=api_key).first()

    if not user:
        return jsonify({'status': 'error', 'message': 'Invalid API Key'}), 401
    
    if user.status == 'inactive':
        return jsonify({'status': 'error', 'message': 'Account is inactive'}), 403

    try:
        amount = float(amount)
        if amount <= 0:
            return jsonify({'status': 'error', 'message': 'Amount must be positive'}), 400
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid amount format'}), 400

    try:
        new_donation = Donation(
            user_id=user.id,
            name=name,
            amount=amount,
            message=message,
            timestamp=datetime.now(timezone.utc),
            date=datetime.now(timezone.utc).date()
        )
        
        db.session.add(new_donation)
        db.session.commit()
        
        return jsonify({'status': 'success', 'donation_id': new_donation.id}), 200
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Donation failed: {e}")
        return jsonify({'status': 'error', 'message': 'Database error'}), 500

@app.route('/api/v1/settings/<int:user_id>', methods=['GET', 'POST'])
@login_required
def settings_api(user_id):
    if user_id != current_user.id:
        abort(403)
        
    settings = Settings.query.filter_by(user_id=user_id).first()
    
    if request.method == 'GET':
        if not settings:
            return jsonify({'error': 'Settings not found'}), 404
            
        # Формирование URL для пресетов
        alert_url = ALERT_PRESETS.get(settings.alert_preset, {}).get('url') if settings.alert_preset in ALERT_PRESETS else settings.alert_custom_url
        sound_url = SOUND_PRESETS.get(settings.sound_preset, {}).get('url') if settings.sound_preset in SOUND_PRESETS else settings.sound_custom_url

        return jsonify({
            'min_amount': settings.min_amount,
            'tts_enabled': settings.tts_enabled,
            'tts_volume': settings.tts_volume,
            'font_family': settings.font_family,
            'title_color': settings.title_color,
            'highlight_color': settings.highlight_color,
            'message_color': settings.message_color,
            'alert_preset': settings.alert_preset,
            'alert_custom_url': settings.alert_custom_url,
            'sound_preset': settings.sound_preset,
            'sound_custom_url': settings.sound_custom_url,
            'alert_url': alert_url,
            'sound_url': sound_url
        }), 200
        
    elif request.method == 'POST':
        data = request.json
        if not settings:
            return jsonify({'error': 'Settings not found'}), 404
            
        try:
            settings.min_amount = float(data.get('min_amount', settings.min_amount))
            settings.tts_enabled = bool(data.get('tts_enabled', settings.tts_enabled))
            settings.tts_volume = float(data.get('tts_volume', settings.tts_volume))
            
            # Кастомизация
            settings.font_family = data.get('font_family', settings.font_family)
            settings.title_color = data.get('title_color', settings.title_color)
            settings.highlight_color = data.get('highlight_color', settings.highlight_color)
            settings.message_color = data.get('message_color', settings.message_color)
            settings.alert_preset = data.get('alert_preset', settings.alert_preset)
            settings.alert_custom_url = data.get('alert_custom_url', settings.alert_custom_url)
            settings.sound_preset = data.get('sound_preset', settings.sound_preset)
            settings.sound_custom_url = data.get('sound_custom_url', settings.sound_custom_url)
            
            db.session.commit()
            return jsonify({'status': 'success'}), 200
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Settings update failed: {e}")
            return jsonify({'status': 'error', 'message': 'Invalid data or database error'}), 400

@app.route('/api/v1/goal/<int:user_id>', methods=['GET', 'POST'])
@login_required
def goal_api(user_id):
    if user_id != current_user.id:
        abort(403)
        
    goal = Goal.query.filter_by(user_id=user_id).first()
    
    # Получаем текущую сумму
    current_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=user_id).scalar() or 0.0
    
    if request.method == 'GET':
        if not goal:
            return jsonify({'error': 'Goal not found'}), 404
            
        return jsonify({
            'title': goal.title,
            'target_amount': goal.target_amount,
            'current_amount': current_sum,
            'progress': min(100, (current_sum / goal.target_amount * 100) if goal.target_amount else 0)
        }), 200
        
    elif request.method == 'POST':
        data = request.json
        if not goal:
            return jsonify({'error': 'Goal not found'}), 404
            
        try:
            goal.title = data.get('title', goal.title)
            goal.target_amount = float(data.get('target_amount', goal.target_amount))
            db.session.commit()
            return jsonify({'status': 'success'}), 200
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Goal update failed: {e}")
            return jsonify({'status': 'error', 'message': 'Invalid data or database error'}), 400
            
@app.route('/api/v1/donations/<int:user_id>', methods=['GET'])
@login_required
def donations_api(user_id):
    if user_id != current_user.id:
        abort(403)
        
    # Донаты для текущего пользователя, отсортированные по времени
    donations = Donation.query.filter_by(user_id=user_id).order_by(Donation.timestamp.desc()).limit(100).all()
    
    donations_data = [{
        'id': d.id,
        'name': d.name,
        'amount': f"{d.amount:.2f}",
        'message': d.message,
        'timestamp': d.timestamp.isoformat(),
        'is_read': d.is_read
    } for d in donations]
    
    return jsonify(donations_data)

@app.route('/api/v1/donations/reset', methods=['POST'])
@login_required
def reset_donations():
    try:
        # Удаляем все донаты пользователя
        Donation.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        
        # Обновляем цель (сумма становится 0)
        goal = Goal.query.filter_by(user_id=current_user.id).first()
        if goal:
            # Устанавливаем целевую сумму снова, чтобы прогресс был 0
            # Если целевая сумма была 10000, она останется 10000.
            pass
            
        return jsonify({'status': 'success', 'message': 'Все донаты сброшены.'}), 200
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Donation reset failed: {e}")
        return jsonify({'status': 'error', 'message': 'Ошибка сброса донатов.'}), 500

@app.route('/alert_widget/<int:user_id>')
def alert_widget(user_id):
    user = User.query.get_or_404(user_id)
    if user.status != 'active':
         # Если пользователь не активен, возвращаем пустой виджет или заглушку
        return "<!-- Пользователь не активен -->"

    settings = user.settings or Settings(user_id=user.id) # Fallback
    
    # Получение URL из пресетов или кастомного URL
    alert_url = ALERT_PRESETS.get(settings.alert_preset, {}).get('url') if settings.alert_preset in ALERT_PRESETS else settings.alert_custom_url
    sound_url = SOUND_PRESETS.get(settings.sound_preset, {}).get('url') if settings.sound_preset in SOUND_PRESETS else settings.sound_custom_url

    return render_template('alert.html', 
                           user_id=user_id, 
                           settings=settings,
                           alert_url=alert_url,
                           sound_url=sound_url,
                           cache_buster=cache_buster)

@app.route('/goal_widget/<int:user_id>')
def goal_widget(user_id):
    user = User.query.get_or_404(user_id)
    goal = user.goal or Goal(user_id=user.id) # Fallback

    return render_template('goal.html', 
                           user_id=user_id, 
                           goal=goal,
                           settings=user.settings,
                           cache_buster=cache_buster)

@app.route('/top_donators_widget/<int:user_id>')
def top_donators_widget(user_id):
    user = User.query.get_or_404(user_id)
    settings = user.settings or Settings(user_id=user.id) # Fallback
    
    # Расчет топ-донатеров (по общей сумме)
    top_donators = db.session.query(Donation.name, func.sum(Donation.amount).label('total_amount')).\
        filter_by(user_id=user_id).\
        group_by(Donation.name).\
        order_by(func.sum(Donation.amount).desc()).\
        limit(5).all()

    return render_template('top_donators.html', 
                           top_donators=top_donators,
                           settings=settings,
                           title="ТОП Донатеры (Все время)",
                           cache_buster=cache_buster)

@app.route('/top_donators_day_widget/<int:user_id>')
def top_donators_day_widget(user_id):
    user = User.query.get_or_404(user_id)
    settings = user.settings or Settings(user_id=user.id) # Fallback
    today = datetime.now(timezone.utc).date()
    
    # Расчет топ-донатеров (за сегодня)
    top_donators = db.session.query(Donation.name, func.sum(Donation.amount).label('total_amount')).\
        filter_by(user_id=user_id, date=today).\
        group_by(Donation.name).\
        order_by(func.sum(Donation.amount).desc()).\
        limit(5).all()

    return render_template('top_donators.html', 
                           top_donators=top_donators,
                           settings=settings,
                           title="ТОП Донатеры (Сегодня)",
                           cache_buster=cache_buster)

@app.route('/latest_donations_widget/<int:user_id>')
def latest_donations_widget(user_id):
    user = User.query.get_or_404(user_id)
    settings = user.settings or Settings(user_id=user.id) # Fallback

    # Последние 5 донатов
    latest_donations = Donation.query.filter_by(user_id=user_id).\
        order_by(Donation.timestamp.desc()).\
        limit(5).all()

    return render_template('latest_donations.html', 
                           latest_donations=latest_donations,
                           settings=settings,
                           cache_buster=cache_buster)

@app.route('/latest_donations_popout/<int:user_id>')
def latest_donations_popout(user_id):
    user = User.query.get_or_404(user_id)
    settings = user.settings or Settings(user_id=user.id) # Fallback

    # Последние 20 донатов (для всплывающего окна)
    latest_donations = Donation.query.filter_by(user_id=user_id).\
        order_by(Donation.timestamp.desc()).\
        limit(20).all()

    return render_template('latest_donations_popout.html', 
                           latest_donations=latest_donations,
                           settings=settings,
                           cache_buster=cache_buster)

@app.route('/admin_panel')
@admin_required
def admin_panel():
    users = User.query.all()
    return render_template('admin_panel.html', users=users, cache_buster=cache_buster)

@app.route('/admin_panel/update_user/<int:user_id>', methods=['POST'])
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    
    role = request.form.get('role')
    status = request.form.get('status')
    
    if role in ['user', 'admin']:
        user.role = role
    if status in ['active', 'inactive']:
        user.status = status
        
    db.session.commit()
    return redirect(url_for('admin_panel'))

# Обработка ошибок
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error_code=404, error_message="Страница не найдена"), 404

@app.errorhandler(403)
def forbidden(error):
    return render_template('error.html', error_code=403, error_message="Доступ запрещен"), 403

if __name__ == '__main__':
    # Определение порта для Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
