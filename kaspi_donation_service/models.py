from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
import uuid

# ... остальной код ...

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    min_amount = db.Column(db.Float, nullable=False, default=100.0)
    
    # ИСПРАВЛЕНИЕ: Временно делаем поле необязательным, чтобы миграция прошла успешно
    widget_theme = db.Column('theme', db.String(50), nullable=True, default='dark') 

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
