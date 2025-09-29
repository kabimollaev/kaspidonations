from kaspi_donation_service import create_app

app = create_app()

if __name__ == '__main__':
    # Эта часть не используется на Render, но полезна для локального запуска
    from kaspi_donation_service import sock
    sock.run(app, debug=True)
