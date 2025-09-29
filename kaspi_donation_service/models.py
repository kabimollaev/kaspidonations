from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
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
    
    # ИСПРАВЛЕНИЕ: Используем server_default для миграции на существующей базе данных
    widget_theme = db.Column('theme', db.String(50), nullable=False, server_default='dark') 

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)

