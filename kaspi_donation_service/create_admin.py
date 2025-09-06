import secrets
from getpass import getpass
from werkzeug.security import generate_password_hash
from server import app, db, User

def create_admin():
    """Создает первого администратора в системе."""
    with app.app_context():
        db.create_all()
        # Проверяем, есть ли уже администраторы
        if User.query.filter_by(role='admin').first():
            print("Администратор уже существует.")
            return

        print("--- Создание аккаунта администратора ---")
        username = input("Введите логин администратора: ")
        password = getpass("Введите пароль: ")
        
        # Проверка, не занят ли логин
        if User.query.filter_by(username=username).first():
            print(f"Пользователь с логином '{username}' уже существует.")
            return
            
        password_hash = generate_password_hash(password, method='pbkdf2:sha224')
        api_key = secrets.token_hex(16)

        admin = User(
            username=username,
            password_hash=password_hash,
            api_key=api_key,
            role='admin',
            status='active' # Администратор всегда активен
        )

        db.session.add(admin)
        db.session.commit()
        print(f"Аккаунт администратора '{username}' успешно создан!")

if __name__ == '__main__':
    create_admin()

