import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_sock import Sock
from flask_migrate import Migrate
from pathlib import Path

# --- Инициализация расширений ---
db = SQLAlchemy()
login_manager = LoginManager()
sock = Sock()
migrate = Migrate()

# Глобальные переменные для WebSocket и статуса
clients = {}
PHONE_STATUS = {}

def create_app():
    """
    Создает и конфигурирует экземпляр приложения Flask (App Factory).
    """
    app = Flask(__name__)

    # --- Улучшенная конфигурация ---
    basedir = Path(__file__).parent.parent
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    if not app.config['SECRET_KEY']:
        raise ValueError("Необходимо установить переменную окружения SECRET_KEY")

    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f"sqlite:///{basedir / 'instance' / 'database.db'}")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Убедимся, что папка instance существует
    (basedir / 'instance').mkdir(exist_ok=True)

    # --- Привязка расширений к приложению ---
    db.init_app(app)
    login_manager.init_app(app)
    sock.init_app(app)
    migrate.init_app(app, db) # Инициализация Flask-Migrate

    # Настройка LoginManager
    login_manager.login_view = 'auth.login'
    
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- Регистрация Blueprints (ИСПРАВЛЕНО) ---
    from .views import main, auth, admin, api, widgets
    
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(widgets.bp)

    return app

