from kaspi_donation_service import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Используем порт из переменных окружения, что важно для Render.com
    port = int(os.environ.get("PORT", 5000))
    # Запускаем приложение через Gunicorn-совместимый способ
    # В локальной среде Gunicorn не используется, Flask запустит свой сервер
    app.run(host='0.0.0.0', port=port)
