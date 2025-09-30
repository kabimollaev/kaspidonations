from flask import Blueprint, render_template, abort
from . import db
from .models import User
from .utils import check_user_status

bp = Blueprint('widgets', __name__)

def get_user_and_check_status(user_id):
    """Вспомогательная функция для получения пользователя и проверки его статуса."""
    user = db.session.get(User, user_id)
    if not user:
        abort(404, "Пользователь не найден")
    
    is_allowed, message = check_user_status(user)
    if not is_allowed:
        abort(403, f"Доступ запрещен. {message}")
        
    return user

@bp.route('/alert/<int:user_id>')
def alert_widget(user_id):
    user = get_user_and_check_status(user_id)
    return render_template('alert.html', user=user, api_key=user.api_key)

@bp.route('/goal/<int:user_id>')
def goal_widget(user_id):
    user = get_user_and_check_status(user_id)
    return render_template('goal.html', user=user, api_key=user.api_key)

@bp.route('/top_donators/<int:user_id>')
def top_donators_widget(user_id):
    user = get_user_and_check_status(user_id)
    return render_template('top_donators.html', user=user, api_key=user.api_key)

@bp.route('/top_donators_day/<int:user_id>')
def top_donators_day_widget(user_id):
    user = get_user_and_check_status(user_id)
    return render_template('top_donators_day.html', user=user, api_key=user.api_key)

@bp.route('/top_donators_month/<int:user_id>')
def top_donators_month_widget(user_id):
    user = get_user_and_check_status(user_id)
    return render_template('top_donators_month.html', user=user, api_key=user.api_key)

@bp.route('/latest_donations/<int:user_id>')
def latest_donations_widget(user_id):
    user = get_user_and_check_status(user_id)
    return render_template('latest_donations.html', user=user, api_key=user.api_key)
    
@bp.route('/latest_donations_popout/<int:user_id>')
def latest_donations_popout(user_id):
    user = get_user_and_check_status(user_id)
    return render_template('latest_donations_popout.html', user=user, api_key=user.api_key)
