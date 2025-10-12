import secrets
import os
import sys
from getpass import getpass
from werkzeug.security import generate_password_hash

# Добавляем корневую директорию проекта (src) в путь Python,
# чтобы можно было импортировать пакет 'kaspi_donation_service'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from kaspi_donation_service import create_app, db
from kaspi_donation_service.models import User, Goal, Settings

# Создаем экземпляр Flask приложения, чтобы получить доступ к его контексту
app = create_app()

def create_admin():
    """Обновляет существующий аккаунт администратора или создает новый, если не найден."""
    # Используем контекст приложения для работы с базой данных
    with app.app_context():
        # Ищем существующего администратора
        admin = User.query.filter_by(role='admin').first()

        if admin:
            print("--- Обновление аккаунта администратора ---")
            password = getpass(f"Обновляем пароль для администратора '{admin.username}'. Введите НОВЫЙ пароль: ")
            
            # Проверка, что новый пароль не пустой
            if not password:
                print("Пароль не может быть пустым.")
                return
            
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            
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
            # Важно: нужно получить id нового админа после первого коммита
            db.session.add(Goal(user_id=new_admin.id))
            db.session.add(Settings(user_id=new_admin.id))
            db.session.commit()
            
            print(f"✅ Аккаунт администратора '{username}' успешно СОЗДАН!")


if __name__ == '__main__':
    create_admin()
