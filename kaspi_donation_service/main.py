from flask import Blueprint, render_template, g
from flask_login import login_required, current_user
from .. import db
from ..models import User, Goal, Settings, Donation
from sqlalchemy import func

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    user = db.session.get(User, current_user.id)
    if not user.goal:
        db.session.add(Goal(user_id=user.id))
        db.session.commit()
    if not user.settings:
        db.session.add(Settings(user_id=user.id))
        db.session.commit()
    
    # Расширенная статистика
    total_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=user.id).scalar() or 0
    total_count = Donation.query.filter_by(user_id=user.id).count()
    largest_donation = db.session.query(func.max(Donation.amount)).filter_by(user_id=user.id).scalar() or 0
    average_donation = total_sum / total_count if total_count > 0 else 0

    stats = {
        'largest': largest_donation,
        'average': average_donation
    }
    
    return render_template('dashboard.html', user=current_user, stats=stats)
