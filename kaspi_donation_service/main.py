from flask import Blueprint, render_template, g
from flask_login import login_required, current_user
from .models import User
from .api import get_donation_stats # Импортируем функцию статистики

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    # Проверяем и создаем связанные записи, если их нет
    user = User.query.get(current_user.id)
    if not user.goal:
        from . import db
        from .models import Goal
        db.session.add(Goal(user_id=user.id))
        db.session.commit()
    if not user.settings:
        from . import db
        from .models import Settings
        db.session.add(Settings(user_id=user.id))
        db.session.commit()
    
    trial_info = None 
    stats = get_donation_stats(current_user.id)
    
    return render_template('dashboard.html', user=current_user, trial_info=trial_info, stats=stats)
