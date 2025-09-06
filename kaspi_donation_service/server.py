import time
import uuid
import os
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# --- Настройка путей ---
# Устанавливаем базовую директорию проекта
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Конфигурация приложения ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'
# Указываем абсолютный путь к базе данных
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'instance', 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Убедимся, что папка instance существует
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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

# --- API для Панели Управления ---

@app.before_request
def before_request_api():
    if request.path.startswith('/api'):
        g.user = None
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            api_key = request.args.get('api_key')
        
        if api_key:
            user = User.query.filter_by(api_key=api_key).first()
            if user:
                g.user = user

def api_login_required(f):
    @login_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

# --- ИСПРАВЛЕНИЕ: Добавлен недостающий API-маршрут ---
@app.route('/api/get_all_data', methods=['GET'])
@api_login_required
def get_all_data():
    """
    Собирает все данные пользователя (донаты, цель, настройки)
    и возвращает их в одном JSON-ответе.
    """
    donations = Donation.query.filter_by(user_id=current_user.id).order_by(Donation.timestamp.desc()).all()
    goal = Goal.query.filter_by(user_id=current_user.id).first()
    settings = Settings.query.filter_by(user_id=current_user.id).first()
    
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
    } if goal else {}
    
    settings_data = {
        'min_amount': settings.min_amount,
        'tts_enabled': settings.tts_enabled,
        'tts_volume': settings.tts_volume
    } if settings else {}

    return jsonify({
        'donations': donations_list,
        'goal': goal_data,
        'settings': settings_data
    })


# --- Запуск приложения ---

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)

