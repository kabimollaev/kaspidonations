import os
import sqlite3
import re
import time
import json
import threading
import webbrowser
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sock import Sock
from gtts import gTTS

# --- НАСТРОЙКИ ---
WINDOWS_USERNAME = os.getlogin()
# --- КОНЕЦ НАСТРОЕК ---

app = Flask(__name__)
sock = Sock(app)

# Пути к папкам
DB_PATH = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Windows', 'Notifications', 'wpndatabase.db')
TTS_CACHE_DIR = 'tts_cache'

# Глобальные переменные
donations_data = {
    "donations": [],
    "goal": {"current": 0, "target": 10000, "title": "На новую видеокарту"},
    "settings": {"min_amount": 100, "tts_enabled": True, "tts_volume": 0.7}
}
PHONE_STATUS = {
    "connected": False,
    "message": "Поиск Phone Link...",
    "last_check": None
}

# --- ФУНКЦИИ ---

def load_data():
    global donations_data
    if os.path.exists('donations_data.json'):
        with open('donations_data.json', 'r', encoding='utf-8') as f:
            donations_data = json.load(f)
        print("ℹ️  Данные успешно загружены из файла.")
    else:
        print("ℹ️  Файл данных не найден. Начинаем с чистого листа.")

def save_data():
    with open('donations_data.json', 'w', encoding='utf-8') as f:
        json.dump(donations_data, f, ensure_ascii=False, indent=4)

def broadcast(data):
    for ws in app.clients:
        try:
            ws.send(json.dumps(data))
        except Exception as e:
            print(f"❌ Не удалось отправить WebSocket сообщение: {e}")

def get_full_update_message():
    return {"type": "full_update", "data": donations_data}

def parse_kaspi_notification(xml_payload):
    try:
        # Извлекаем все текстовые элементы из XML
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

        # Ищем строку с информацией о переводе
        for i, line in enumerate(lines):
            if "Пополнение:" in line and "₸" in line:
                # Если это комбинированная строка, разбиваем ее
                if '\n' in line:
                    parts = line.split('\n')
                    if len(parts) >= 2:
                        # Первая часть: "Пополнение: 100 ₸"
                        # Вторая часть: "Темірлан А.: Жазп койдм не де еде Торо Латвии"
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
                
                # Если нет переноса строки, ищем следующую строку
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
            # Если не нашли стандартным способом, пробуем найти в других строках
            for line in lines:
                if ":" in line and "Пополнение:" not in line:
                    parts = line.split(":", 1)
                    potential_sender = parts[0].strip()
                    if len(potential_sender) > 2:  # Фильтруем слишком короткие имена
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
        import traceback
        traceback.print_exc()
        return None

def add_donation_from_parser(name, amount, message):
    global donations_data
    if not name:
        name = "Аноним"
    
    donation = {
        "id": int(time.time() * 1000),
        "name": name,
        "amount": float(amount),
        "message": message
    }
    donations_data["donations"].insert(0, donation)
    donations_data["goal"]["current"] += float(amount)
    save_data()
    
    broadcast(get_full_update_message())
    
    if float(amount) >= donations_data["settings"]["min_amount"]:
        broadcast({"type": "show_alert", "data": donation})
        if donations_data["settings"]["tts_enabled"]:
            tts_message = f"{donation['name']} отправил {int(donation['amount'])} тенге. Сообщение: {donation['message'] if donation['message'] else 'без сообщения'}"
            trigger_tts(tts_message)

def trigger_tts(text):
    try:
        if not os.path.exists(TTS_CACHE_DIR):
            os.makedirs(TTS_CACHE_DIR)
        tts = gTTS(text, lang='ru')
        filename = os.path.join(TTS_CACHE_DIR, f'tts_{int(time.time())}.mp3')
        tts.save(filename)
        broadcast({"type": "tts", "url": f'/{TTS_CACHE_DIR}/{os.path.basename(filename)}'})
    except Exception as e:
        print(f"❌ Ошибка создания TTS: {e}")

def notification_parser_thread():
    global PHONE_STATUS
    last_processed_id = 0
    print("[INFO] Поток парсера уведомлений запущен. Режим отладки: показываю ВСЕ уведомления")

    while True:
        try:
            if not os.path.exists(DB_PATH):
                PHONE_STATUS.update({"connected": False, "message": "База данных не найдена", "last_check": time.time()})
                print(f"❌ База данных не найдена по пути: {DB_PATH}")
                time.sleep(10)
                continue
            
            try:
                con = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
                last_modified_time = os.path.getmtime(DB_PATH)
                if (time.time() - last_modified_time) > 120:
                    PHONE_STATUS.update({"connected": True, "message": "Подключено (ожидание уведомлений)", "last_check": time.time()})
                    print("Ожидание новых уведомлений...")
                else:
                    PHONE_STATUS.update({"connected": True, "message": "Подключено и отслеживается", "last_check": time.time()})
                    print("Сканирование...")
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    PHONE_STATUS.update({"connected": True, "message": "Подключено и отслеживается", "last_check": time.time()})
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
                    print(f"[INFO] Начальная точка парсинга: ID {last_processed_id}. Ожидаю новые уведомления.")
                else:
                    print("[INFO] База пуста или не содержит уведомлений")

            cur.execute("SELECT ROWID, Payload FROM Notification WHERE ROWID > ?", (last_processed_id,))
            new_notifications = cur.fetchall()

            if new_notifications:
                print(f"📨 Найдено {len(new_notifications)} новых уведомлений:")

            for rowid, payload in new_notifications:
                last_processed_id = rowid
                try:
                    if payload is None:
                        print(f"   ID {rowid}: Пустой payload")
                        continue 

                    payload_str = payload.decode('utf-8', errors='ignore')
                    
                    # Пропускаем служебные уведомления (badge, системные)
                    if '<badge' in payload_str or payload_str.startswith('<badge'):
                        continue
                    
                    # Пропускаем слишком короткие уведомления (системные)
                    if len(payload_str) < 50:
                        continue

                    # Извлекаем все текстовые элементы для отладки
                    text_elements = re.findall(r'<text[^>]*>([^<]+)</text>', payload_str)
                    
                    # Показываем только уведомления с текстом
                    if text_elements:
                        print(f"   🔔 Уведомление ID {rowid}:")
                        print("   📝 Текст уведомления:")
                        for i, text in enumerate(text_elements):
                            text = text.strip()
                            if i == 0:
                                print(f"       🏷️  Приложение: \"{text}\"")
                            elif i == 1:
                                print(f"       📋 Заголовок: \"{text}\"")
                            else:
                                print(f"       📄 Строка {i+1}: \"{text}\"")
                        print(f"      Length: {len(payload_str)} chars")
                        print("-" * 50)
                    
                    # Проверяем, является ли уведомление о переводе
                    is_payment = any('Пополнение:' in text or 'Перевод на сумму' in text or '₸' in text for text in text_elements) if text_elements else False

                    if is_payment:
                        print(f"   🟢 ОБНАРУЖЕН ПЕРЕВОД! ID: {rowid}")
                        donation_info = parse_kaspi_notification(payload_str)
                        if donation_info and donation_info.get('amount'):
                            print(f"   ✅ Успешно распарсено: {donation_info['amount']}₸ от {donation_info['sender']}")
                            add_donation_from_parser(
                                donation_info['sender'], 
                                donation_info['amount'], 
                                donation_info.get('message', "Новый перевод!")
                            )
                        else:
                            print("   ❌ Не удалось распарсить уведомление о переводе")
                    
                except Exception as e:
                    print(f"❌ Не удалось обработать уведомление ID {rowid}: {e}")
                    import traceback
                    traceback.print_exc()
            
            con.close()
        except Exception as e:
            PHONE_STATUS.update({"connected": False, "message": f"Критическая ошибка: {e}", "last_check": time.time()})
            print(f"❌ Критическая ошибка в парсере: {e}")
            import traceback
            traceback.print_exc()
        
        time.sleep(2)

# --- МАРШРУТЫ FLASK ---

@app.route('/')
def dashboard(): return render_template('dashboard.html')

@app.route('/alert')
def alert(): return render_template('alert.html')

@app.route('/goal')
def goal(): return render_template('goal.html')

@app.route('/top_donators')
def top_donators(): return render_template('top_donators.html')

@app.route('/latest_donations')
def latest_donations(): return render_template('latest_donations.html')

@app.route('/latest_donations_popout')
def latest_donations_popout(): return render_template('latest_donations_popout.html')

# --- API МАРШРУТЫ ---
@app.route('/api/get_data', methods=['GET'])
def get_data(): return jsonify(donations_data)

@app.route('/api/get_phone_status', methods=['GET'])
def get_phone_status(): return jsonify(PHONE_STATUS)

@app.route('/api/add_donation', methods=['POST'])
def add_donation():
    data = request.json
    add_donation_from_parser(data.get('name'), data.get('amount'), data.get('message'))
    return jsonify({"status": "success"})

@app.route('/api/test_donation', methods=['POST'])
def test_donation():
    add_donation_from_parser('Тестер', 100, 'Это тестовый донат для проверки оповещений!')
    return jsonify({"status": "success"})

@app.route('/api/update_goal', methods=['POST'])
def update_goal():
    data = request.json
    donations_data['goal']['title'] = data.get('title')
    donations_data['goal']['target'] = float(data.get('target', 0))
    save_data()
    broadcast(get_full_update_message())
    return jsonify({"status": "success"})

@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    data = request.json
    donations_data['settings']['min_amount'] = float(data.get('min_amount', 100))
    donations_data['settings']['tts_enabled'] = data.get('tts_enabled', True)
    donations_data['settings']['tts_volume'] = float(data.get('tts_volume', 0.7))
    save_data()
    broadcast(get_full_update_message())
    return jsonify({"status": "success"})

@app.route('/api/reset_goal', methods=['POST'])
def reset_goal():
    donations_data['goal']['current'] = 0
    donations_data['donations'] = []
    save_data()
    broadcast(get_full_update_message())
    return jsonify({"status": "success"})

@app.route('/api/delete_donation/<int:donation_id>', methods=['POST'])
def delete_donation(donation_id):
    initial_len = len(donations_data['donations'])
    donations_data['donations'] = [d for d in donations_data['donations'] if d['id'] != donation_id]
    if len(donations_data['donations']) < initial_len:
        donations_data['goal']['current'] = sum(d['amount'] for d in donations_data['donations'])
        save_data()
        broadcast(get_full_update_message())
    return jsonify({"status": "success"})

@app.route('/api/replay_donation/<int:donation_id>', methods=['POST'])
def replay_donation(donation_id):
    donation = next((d for d in donations_data['donations'] if d['id'] == donation_id), None)
    if donation:
        broadcast({"type": "show_alert", "data": donation})
        if donations_data["settings"]["tts_enabled"]:
            tts_message = f"{donation['name']} отправил {int(donation['amount'])} тенге. Сообщение: {donation['message'] if donation['message'] else 'без сообщения'}"
            trigger_tts(tts_message)
    return jsonify({"status": "success" if donation else "not found"})

# --- РАЗДАЧА ФАЙЛОВ ---
@app.route('/static/<path:filename>')
def serve_static_files(filename):
    return send_from_directory('static', filename)

@app.route('/tts_cache/<path:filename>')
def serve_tts_cache(filename):
    return send_from_directory(TTS_CACHE_DIR, filename)

# WebSocket
@sock.route('/ws')
def ws(ws):
    app.clients.add(ws)
    try:
        ws.send(json.dumps(get_full_update_message()))
        while True:
            data = ws.receive()
            if data is None: 
                break
    except Exception:
        pass
    finally:
        app.clients.remove(ws)


if __name__ == '__main__':
    if not os.path.exists(os.path.join('static', 'media')):
        os.makedirs(os.path.join('static', 'media'))
        print(f"ℹ️  Создана папка 'static/media' для ваших звуков и GIF.")

    app.clients = set()
    load_data()
    
    parser_thread = threading.Thread(target=notification_parser_thread, daemon=True)
    parser_thread.start()
    
    threading.Timer(1, lambda: webbrowser.open('http://127.0.0.1:5000/')).start()

    app.run(host='0.0.0.0', port=5000, debug=False)