from flask import Blueprint, render_template
from flask_login import login_required, current_user
from . import db
from .models import Goal, Settings

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    user = current_user
    
    # Проверяем и создаем связанные записи, если они отсутствуют
    if not user.goal:
        db.session.add(Goal(user_id=user.id))
        db.session.commit()
    if not user.settings:
        db.session.add(Settings(user_id=user.id))
        db.session.commit()
    
    return render_template('dashboard.html')
