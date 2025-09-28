import secrets
from getpass import getpass
from werkzeug.security import generate_password_hash
# ИЗМЕНЕНИЕ: Импортируем Path для совместимости с server.py
from pathlib import Path
# ИЗМЕНЕНИЕ: Импортируем app, db, User, Goal, Settings из server.py
from server import app, db, User, Goal, Settings

def create_admin():
    """Обновляет существующий аккаунт администратора или создает новый, если не найден."""
    with app.app_context():
        # Ищем существующего администратора
        admin = User.query.filter_by(role='admin').first()

        if admin:
            print("--- Обновление аккаунта администратора ---")
            username = input(f"Обновляем пароль для администратора: {admin.username}. Введите НОВЫЙ пароль: ")
            
            # Проверка, что новый пароль не пустой
            if not username:
                print("Пароль не может быть пустым.")
                return
            
            password_hash = generate_password_hash(username, method='pbkdf2:sha256')
            
            admin.password_hash = password_hash
            admin.status = 'active' # Гарантируем активный статус
            admin.api_key = secrets.token_hex(16) # Обновляем ключ на всякий случай
            
            db.session.commit()
            
            print(f"✅ Аккаунт администратора '{admin.username}' успешно ОБНОВЛЕН! Используйте новый пароль.")
        else:
            print("--- Создание нового аккаунта администратора ---")
            username = input("Введите логин нового администратора: ")
            password = getpass("Введите пароль: ")
            
            if User.query.filter_by(username=username).first():
                print(f"Пользователь с логином '{username}' уже существует.")
                return
                
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            api_key = secrets.token_hex(16)

            new_admin = User(
                username=username,
                password_hash=password_hash,
                api_key=api_key,
                role='admin',
                status='active'
            )

            db.session.add(new_admin)
            db.session.commit()
            
            # Создаем связанные записи
            db.session.add(Goal(user_id=new_admin.id))
            db.session.add(Settings(user_id=new_admin.id))
            db.session.commit()
            
            print(f"✅ Аккаунт администратора '{username}' успешно СОЗДАН!")


if __name__ == '__main__':
    create_admin()
