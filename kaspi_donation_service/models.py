from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import uuid

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    status = db.Column(db.String(20), nullable=False, default='inactive')
    api_key = db.Column(db.String(120), unique=True, nullable=False)
    
    donations = db.relationship('Donation', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    goal = db.relationship('Goal', backref='user', uselist=False, lazy=True, cascade="all, delete-orphan")
    settings = db.relationship('Settings', backref='user', uselist=False, lazy=True, cascade="all, delete-orphan")

    def get_donation_stats(self):
        """Возвращает статистику донатов для пользователя."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        total_donations_count = db.session.query(func.count(Donation.id)).filter_by(user_id=self.id).scalar() or 0
        total_donations_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=self.id).scalar() or 0
        
        today_donations_count = db.session.query(func.count(Donation.id)).filter_by(user_id=self.id).filter(Donation.timestamp >= today_start).scalar() or 0
        today_donations_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=self.id).filter(Donation.timestamp >= today_start).scalar() or 0
        
        month_donations_count = db.session.query(func.count(Donation.id)).filter_by(user_id=self.id).filter(Donation.timestamp >= month_start).scalar() or 0
        month_donations_sum = db.session.query(func.sum(Donation.amount)).filter_by(user_id=self.id).filter(Donation.timestamp >= month_start).scalar() or 0
        
        return {
            'total': {'count': total_donations_count, 'sum': total_donations_sum},
            'today': {'count': today_donations_count, 'sum': today_donations_sum},
            'month': {'count': month_donations_count, 'sum': month_donations_sum},
        }

    def get_donations_by_period(self, period='all'):
        """Возвращает донаты за определенный период."""
        if period == 'day':
            start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            return self.donations.filter(Donation.timestamp >= start_date).order_by(Donation.amount.desc()).all()
        elif period == 'month':
            start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return self.donations.filter(Donation.timestamp >= start_date).order_by(Donation.amount.desc()).all()
        else: # all time
            return self.donations.order_by(Donation.amount.desc()).all()


class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, server_default=func.now())
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
    widget_theme = db.Column('theme', db.String(50), nullable=False, server_default='dark') 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
