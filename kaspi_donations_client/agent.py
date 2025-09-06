import os
import sqlite3
import re
import time
import json
import threading
import requests
import configparser

# --- КОНФИГУРАЦИЯ ---
# Путь к базе данных Phone Link на Windows
DB_PATH = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Windows', 'Notifications', 'wpndatabase.db')

# Чтение API ключа из файла config.ini
config = configparser.ConfigParser()
CONFIG_FILE = 'config.ini'
if not os.path.exists(CONFIG_FILE):
    print("❌ Ошибка: Файл 'config.ini' не найден. Создайте его и добавьте свой API ключ.")
    exit()
config.read(CONFIG_FILE)
API_KEY = config.get('api', 'key', fallback=None)
if not API_KEY:
    print("❌ Ошибка: API ключ не найден в 'config.ini'. Убедитесь, что он указан в секции [api].")
    exit()

# Адрес основного веб-сервиса, куда будут отправляться донаты
# TODO: Замените на реальный адрес сервера после развертывания (например, https://<ваше_приложение>.onrender.com)
SERVER_URL = "SERVER_URL = "https://kaspidonations.onrender.com"
SUBMIT_DONATION_ENDPOINT = f"{SERVER_URL}/api/submit_donation"

# Глобальные переменные
PHONE_STATUS = {
    "connected": False,
    "message": "Поиск Phone Link...",
    "last_check": None
}
# --- КОНЕЦ КОНФИГУРАЦИИ ---


# --- ФУНКЦИИ ---

def parse_kaspi_notification(xml_payload):
    """
    Парсит XML-данные уведомления Kaspi для извлечения информации о донате.
    Возвращает словарь с данными о донате или None в случае ошибки.
    """
    try:
        text_elements = re.findall(r'<text[^>]*>([^<]+)</text>', xml_payload)
        lines = [text.strip() for text in text_elements if text.strip()]
        
        print(f"🔍 Парсим Kaspi уведомление:")
        for i, line in enumerate(lines):
            print(f"   Строка {i}: \"{line}\"")

        amount = None
        sender = None
        message = None
        
        # Поиск суммы
        for line in lines:
            if "₸" in line:
                amount_match = re.search(r'([\d\s,]+)₸', line)
                if amount_match:
                    amount_str = amount_match.group(1).replace(' ', '').replace(',', '.')
                    try:
                        amount = float(amount_str)
                        print(f"✅ Сумма: {amount}₸")
                        break
                    except ValueError:
                        continue
        
        if not amount:
            print("❌ Не удалось найти сумму.")
            return None

        for i, line in enumerate(lines):
            if "Пополнение:" in line and "₸" in line:
                if '\n' in line:
                    parts = line.split('\n')
                    if len(parts) >= 2:
                        sender_line = parts[1].strip()
                        if ":" in sender_line:
                            sender_parts = sender_line.split(":", 1)
                            sender = sender_parts[0].strip()
                            if len(sender_parts) > 1:
                                message = sender_parts[1].strip()
                        else:
                            sender = sender_line
                            message = "Новый перевод!"
                        break
                elif i + 1 < len(lines):
                    sender_line = lines[i + 1]
                    if ":" in sender_line:
                        sender_parts = sender_line.split(":", 1)
                        sender = sender_parts[0].strip()
                        if len(sender_parts) > 1:
                            message = sender_parts[1].strip()
                    else:
                        sender = sender_line
                        message = "Новый перевод!"
                    break
        
        if not sender:
            for line in lines:
                if ":" in line and "Пополнение:" not in line:
                    parts = line.split(":", 1)
                    potential_sender = parts[0].strip()
                    if len(potential_sender) > 2:
                        sender = potential_sender
                        if len(parts) > 1:
                            message = parts[1].strip()
                        break
        
        if not sender:
            sender = "Аноним"
            print("⚠️  Отправитель не найден, используем 'Аноним'")
        
        if not message:
            message = "Новый перевод!"
            print("⚠️  Сообщение не найдено, используем 'Новый перевод!'")
        
        print(f"✅ Отправитель: {sender}")
        print(f"✅ Сообщение: {message}")
        
        return {"amount": amount, "sender": sender, "message": message}
        
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return None

def send_donation_to_server(donation_info):
    """
    Отправляет распарсенные данные о донате на основной веб-сервис.
    """
    headers = {'X-API-Key': API_KEY}
    
    # Формируем полезную нагрузку для отправки на сервер
    payload = {
        'name': donation_info.get('sender'),
        'amount': donation_info.get('amount'),
        'message': donation_info.get('message')
    }
    
    try:
        response = requests.post(SUBMIT_DONATION_ENDPOINT, json=payload, headers=headers)
        if response.status_code == 200:
            print(f"🟢 Успешно отправлено на сервер: {payload}")
        else:
            print(f"❌ Ошибка отправки на сервер ({response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Сетевая ошибка при отправке доната: {e}")
    except Exception as e:
        print(f"❌ Непредвиденная ошибка при отправке: {e}")


def notification_parser_thread():
    """
    Поток, который постоянно отслеживает новые уведомления в базе данных Phone Link.
    """
    last_processed_id = 0
    print("--- ЗАПУЩЕН ЛОКАЛЬНЫЙ АГЕНТ ---")
    print(f"Отправка донатов на адрес: {SUBMIT_DONATION_ENDPOINT}")

    while True:
        try:
            if not os.path.exists(DB_PATH):
                PHONE_STATUS.update({"connected": False, "message": "База данных не найдена", "last_check": time.time()})
                print(f"❌ База данных не найдена по пути: {DB_PATH}")
                time.sleep(10)
                continue
            
            try:
                # Открываем базу данных только для чтения, чтобы избежать блокировки
                con = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
                PHONE_STATUS.update({"connected": True, "message": "Подключено и отслеживается", "last_check": time.time()})
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    time.sleep(2)
                    continue
                else:
                    PHONE_STATUS.update({"connected": False, "message": f"Ошибка SQLite: {e}", "last_check": time.time()})
                    print(f"❌ Ошибка подключения к базе: {e}")
                    time.sleep(5)
                    continue

            cur = con.cursor()
            
            if last_processed_id == 0:
                cur.execute("SELECT MAX(ROWID) FROM Notification")
                res = cur.fetchone()
                if res and res[0]: 
                    last_processed_id = res[0]
                    print(f"ℹ️  Начальная точка парсинга: ID {last_processed_id}. Ожидаю новые уведомления.")

            cur.execute("SELECT ROWID, Payload FROM Notification WHERE ROWID > ?", (last_processed_id,))
            new_notifications = cur.fetchall()

            if new_notifications:
                print(f"📨 Найдено {len(new_notifications)} новых уведомлений.")

            for rowid, payload in new_notifications:
                last_processed_id = rowid
                try:
                    if payload is None:
                        continue 

                    payload_str = payload.decode('utf-8', errors='ignore')
                    
                    # Пропускаем служебные и слишком короткие уведомления
                    if '<badge' in payload_str or len(payload_str) < 50:
                        continue

                    text_elements = re.findall(r'<text[^>]*>([^<]+)</text>', payload_str)
                    
                    is_payment = any('Пополнение:' in text or 'Перевод на сумму' in text or '₸' in text for text in text_elements) if text_elements else False

                    if is_payment:
                        print(f"🔔 ОБНАРУЖЕН ПЕРЕВОД! ID: {rowid}")
                        donation_info = parse_kaspi_notification(payload_str)
                        if donation_info and donation_info.get('amount'):
                            send_donation_to_server(donation_info)
                        else:
                            print("   ❌ Не удалось распарсить уведомление о переводе")
                    
                except Exception as e:
                    print(f"❌ Не удалось обработать уведомление ID {rowid}: {e}")
            
            con.close()
        except Exception as e:
            PHONE_STATUS.update({"connected": False, "message": f"Критическая ошибка: {e}", "last_check": time.time()})
            print(f"❌ Критическая ошибка в парсере: {e}")
        
        time.sleep(2)


if __name__ == '__main__':
    parser_thread = threading.Thread(target=notification_parser_thread, daemon=True)
    parser_thread.start()
    
    # Этот цикл удерживает скрипт активным, пока поток работает
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("\nЗавершение работы...")
            break

