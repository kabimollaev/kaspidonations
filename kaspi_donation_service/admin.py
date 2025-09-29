from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from . import db
from .models import User

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.before_request
@login_required
def before_request():
    if current_user.role != 'admin':
        return redirect(url_for('main.dashboard'))

@bp.route('/')
def admin_panel():
    users = User.query.all()
    return render_template('admin_panel.html', users=users)

@bp.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash(f'Пользователь с ID {user_id} не найден.', 'error')
    else:
        user.role = request.form.get('role')
        user.status = request.form.get('status')
        db.session.commit()
        flash(f'Данные пользователя {user.username} обновлены.', 'success')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'status': 'error', 'message': 'Вы не можете удалить свой собственный аккаунт.'}), 400
    
    user = db.session.get(User, user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        return jsonify({'status': 'success', 'message': f'Пользователь {user.username} был удален.'})
    return jsonify({'status': 'error', 'message': 'Пользователь не найден.'}), 404
