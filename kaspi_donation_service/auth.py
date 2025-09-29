import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, current_user
from ..models import User, Goal, Settings
from .. import db

bp = Blueprint('auth', __name__)

def check_trial_status(user):
    # Эта функция теперь тоже здесь для логической группировки
    if user.role == 'admin' or user.status == 'active':
        return True, None
    else:
        return False, 'Аккаунт неактивен. Пожалуйста, обратитесь к администратору для активации.'

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            is_allowed, message = check_trial_status(user)
            if is_allowed:
                login_user(user, remember=True)
                return redirect(url_for('main.dashboard'))
            else:
                flash(message, 'error')
        else:
            flash('Неверный логин или пароль.', 'error')
    return render_template('login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form.get('username')).first():
            flash('Имя пользователя уже занято.', 'error')
        else:
            hashed_pw = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
            new_user = User(
                username=request.form.get('username'),
                password_hash=hashed_pw,
                api_key=str(uuid.uuid4()),
                status='inactive'
            )
            db.session.add(new_user)
            db.session.commit()
            
            db.session.add(Goal(user_id=new_user.id))
            db.session.add(Settings(user_id=new_user.id))
            db.session.commit()
            
            flash('Регистрация прошла успешно! Ваш аккаунт ожидает активации администратором.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('register.html')

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))
