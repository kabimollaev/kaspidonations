from kaspi_donation_service import create_app, db
from kaspi_donation_service.models import User, Donation, Goal, Settings

app = create_app()

# ИСПРАВЛЕНИЕ: Добавляем контекст приложения для командной строки
@app.shell_context_processor
def make_shell_context():
    return {
        "db": db,
        "User": User,
        "Donation": Donation,
        "Goal": Goal,
        "Settings": Settings
    }

if __name__ == '__main__':
    # Эта часть не используется на Render, но полезна для локального запуска
    from kaspi_donation_service import sock
    sock.run(app, debug=True)
