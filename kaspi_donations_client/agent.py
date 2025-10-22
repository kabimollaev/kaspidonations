import os
import sqlite3
import re
import time
import json
import threading
import requests
import tkinter as tk
from tkinter import messagebox, simpledialog
import configparser
from PIL import Image
from pystray import MenuItem as item, Icon
import atexit
import sys
import logging
import traceback
import hashlib

# --- Настройка логирования ---
log_file_path = 'agent_log.txt'
if os.path.exists(log_file_path):
    os.remove(log_file_path)

# Уровень логирования - только ошибки и важные события
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# --- ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ ---
APP_NAME = "KaspiDonationsAgent"
SERVER_URL = "https://kaspidonations.onrender.com"
DB_PATHS = [
    os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Windows', 'Notifications', 'wpndatabase.db'),
    os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Windows', 'Notifications', 'notifications.db')
]
CONFIG_FILE = 'config.ini'
CONFIG_SECTION = 'Settings'
CONFIG_KEY = 'API_KEY'

# --- Глобальные переменные ---
API_KEY = None
stop_thread = threading.Event()
icon = None
root = None

def resource_path(relative_path):
    """ Gets the absolute path to a resource (works for .exe and .py) """
    try:
        base_path = sys._MEIPASS
        logging.debug(f"Running from PyInstaller temp folder: {base_path}")
    except Exception:
        base_path = os.path.abspath(".")
        logging.debug(f"Running from script folder: {base_path}")
    return os.path.join(base_path, relative_path)

def find_database_path():
    """Находит путь к базе данных уведомлений"""
    for db_path in DB_PATHS:
        if os.path.exists(db_path):
            return db_path
    return None

# --- Функции для работы с config.ini ---
def get_config_parser():
    """Возвращает объект ConfigParser"""
    return configparser.ConfigParser()

def load_api_key_from_config():
    """Загружает API ключ из config.ini"""
    config = get_config_parser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
        if CONFIG_SECTION in config and CONFIG_KEY in config[CONFIG_SECTION]:
            api_key = config[CONFIG_SECTION][CONFIG_KEY]
            if validate_api_key(api_key):
                logging.info("API key successfully loaded from config file.")
                return api_key
            else:
                logging.warning("API key from config file is invalid.")
                return None
    logging.info("Config file or API key not found.")
    return None

def save_api_key_to_config(api_key):
    """Сохраняет API ключ в config.ini"""
    config = get_config_parser()
    if not os.path.exists(CONFIG_FILE):
        config[CONFIG_SECTION] = {}
    else:
        config.read(CONFIG_FILE, encoding='utf-8')
        if CONFIG_SECTION not in config:
            config[CONFIG_SECTION] = {}

    config[CONFIG_SECTION][CONFIG_KEY] = api_key
    
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        logging.info("API key successfully saved to config file.")
        return True
    except Exception as e:
        logging.error(f"Error saving API key to config file: {e}")
        messagebox.showerror("Ошибка", f"Не удалось сохранить API ключ в файл конфигурации: {e}")
        return False

# --- Функции GUI ---
def validate_api_key(api_key):
    """Проверяет валидность API ключа"""
    if not api_key or len(api_key.strip()) < 10 or api_key.strip() == "CANCELLED":
        return False
    return True

def send_to_server(endpoint, payload, max_retries=3):
    if not API_KEY:
        logging.warning("API key is not set. Cannot send data to server.")
        return False

    headers = {'X-API-Key': API_KEY, 'Content-Type': 'application/json'}
    url = f"{SERVER_URL}{endpoint}"
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                logging.info(f"Successfully sent data to {url}")
                return True
            else:
                logging.warning(f"Failed to send data to {url}. Status code: {response.status_code}, Response: {response.text}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed for {url}: {e}")
        
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    
    logging.error(f"Failed to send data to {url} after {max_retries} attempts.")
    return False

def send_disconnect_status():
    disconnect_payload = {
        "connected": False,
        "message": "Agent disconnected",
        "last_check": time.time()
    }
    send_to_server("/api/update_phone_status", disconnect_payload)

def parse_kaspi_notification(xml_payload):
    """
    Улучшенная функция для разбора уведомлений Kaspi.
    Корректно обрабатывает случаи, когда сумма, отправитель и сообщение находятся в одной строке.
    """
    try:
        text_elements = re.findall(r'<text[^>]*>([^<]+)</text>', xml_payload)
        lines = [text.strip() for text in text_elements if text.strip()]
        
        for i, line in enumerate(lines):
            if "Пополнение:" in line and "₸" in line:
                
                amount_match = re.search(r'Пополнение:\s*([\d\s,]+)\s*₸', line)
                if not amount_match:
                    continue

                amount = None
                original_amount_str = amount_match.group(1)
                try:
                    # ИСПРАВЛЕНИЕ: Замена на re.sub для удаления ВСЕХ видов пробелов (включая неразрывные)
                    amount_str = re.sub(r'\s', '', original_amount_str).replace(',', '.')
                    amount = float(amount_str)
                except (ValueError, IndexError):
                    logging.warning(f"Could not convert amount from string: '{original_amount_str}'")
                    continue

                sender = "Неизвестно"
                message = "Новый перевод!"

                if '\n' in line:
                    parts = line.split('\n', 1)
                    if len(parts) > 1:
                        sender_line = parts[1].strip()
                        if ":" in sender_line:
                            sender_parts = sender_line.split(":", 1)
                            sender = sender_parts[0].strip()
                            if len(sender_parts) > 1 and sender_parts[1].strip():
                                message = sender_parts[1].strip()
                        else:
                            sender = sender_line
                elif i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if ":" in next_line:
                        sender_parts = next_line.split(":", 1)
                        sender = sender_parts[0].strip()
                        if len(sender_parts) > 1 and sender_parts[1].strip():
                            message = sender_parts[1].strip()
                    else:
                        sender = next_line

                logging.info(f"Parsed donation: Amount={amount}, Sender={sender}, Message={message}")
                return {"amount": amount, "sender": sender, "message": message}

        logging.warning("No donation information found in the notification payload.")
        return None

    except Exception as e:
        logging.error(f"Critical error in parse_kaspi_notification: {e}", exc_info=True)
        return None


def notification_parser_thread():
    last_processed_id = 0
    logging.info("Notification parser thread started.")

    initial_db_path = find_database_path()
    # Установим начальный ID для отслеживания
    if initial_db_path:
        try:
            # Увеличиваем таймаут для первичного подключения
            with sqlite3.connect(f'file:{initial_db_path}?mode=ro', uri=True, timeout=10) as con: 
                cur = con.cursor()
                cur.execute("SELECT MAX(ROWID) FROM Notification")
                res = cur.fetchone()
                last_processed_id = res[0] if res and res[0] else 0
                logging.info(f"Starting point set. Will look for notifications with ID > {last_processed_id}")
        except Exception as e:
            logging.error(f"Could not set initial last_processed_id. Will start from 0. Error: {e}")
    else:
        logging.warning("Database not found on startup. Will search for it.")

    while not stop_thread.is_set():
        try:
            db_path = find_database_path()
            phone_status = { "connected": False, "message": "Database not found", "last_check": time.time() }

            if db_path:
                logging.debug(f"Database found at: {db_path}")
                phone_status.update({"connected": True, "message": "Connected and tracking"})
                
                # --- Блок повторных попыток доступа к БД для устранения проблемы блокировки ---
                max_db_retries = 5
                db_access_successful = False
                
                for attempt in range(max_db_retries):
                    try:
                        # Увеличиваем таймаут подключения до 10 секунд
                        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=10) as con:
                            cur = con.cursor()
                            logging.debug(f"Querying for notifications with ROWID > {last_processed_id}. Attempt: {attempt + 1}")
                            cur.execute("SELECT ROWID, Payload FROM Notification WHERE ROWID > ?", (last_processed_id,))
                            rows = cur.fetchall()

                            if not rows:
                                logging.debug("No new notifications found in this cycle.")
                            else:
                                logging.info(f"Found {len(rows)} new notification(s). Processing...")
                                for rowid, payload_bytes in rows:
                                    last_processed_id = rowid 
                                    if payload_bytes:
                                        try:
                                            payload_str = payload_bytes.decode('utf-8', errors='ignore')
                                            logging.info(f"\n--- New Notification (ID: {rowid}) ---")
                                            logging.info(f"Full Payload: {payload_str}")

                                            is_kaspi_notification = any(kw in payload_str for kw in ['Пополнение:', 'Перевод на сумму', '₸', 'kaspi.kz'])
                                            if is_kaspi_notification:
                                                donation_info = parse_kaspi_notification(payload_str)
                                                if donation_info and donation_info.get('amount'):
                                                    send_to_server("/api/submit_donation", {
                                                        'name': donation_info.get('sender', 'Неизвестно'),
                                                        'amount': donation_info['amount'],
                                                        'message': donation_info.get('message', 'Новый перевод!')
                                                    })
                                                    logging.info("Kaspi-related notification parsed and sent.")
                                                else:
                                                    logging.warning("Kaspi-related notification was detected but could not be parsed.")
                                            else:
                                                logging.info("Non-Kaspi notification. Filtered out.")
                                        except Exception as e:
                                            logging.error(f"Error decoding or processing payload for ROWID {rowid}: {e}")
                            
                            db_access_successful = True
                            break # Выходим из цикла повторных попыток при успехе

                    except sqlite3.OperationalError as e:
                        # Эта ошибка чаще всего означает, что файл БД заблокирован (например, Windows)
                        logging.warning(f"Database operational error (lock?): {e}. Retrying in 1 second. Attempt {attempt + 1}/{max_db_retries}")
                        time.sleep(1) 
                        
                    except Exception as e:
                        # Другие ошибки (например, поврежденный файл или проблема с путем)
                        logging.error(f"Failed to access or query database: {e}")
                        db_access_successful = False
                        break # Считаем ошибку невосстановимой и выходим из цикла попыток

                # --- Конец блока повторных попыток ---
                
                if not db_access_successful:
                    # Обновляем статус, только если все попытки не удались
                    phone_status.update({"connected": False, "message": "Database access failed after retries"})
            else:
                logging.warning("Notification database not found in this cycle.")
                phone_status.update({"connected": False, "message": "Database not found"})


            send_to_server("/api/update_phone_status", phone_status)
            stop_thread.wait(5)
            
        except Exception as e:
            logging.critical(f"UNHANDLED EXCEPTION in parser thread loop: {e}", exc_info=True)
            stop_thread.wait(15)

def quit_app(icon, item):
    """Корректное завершение приложения"""
    logging.info("Quitting application...")
    stop_thread.set()
    if icon:
        icon.stop()
    if root and root.winfo_exists():
        root.after(100, root.destroy)

def change_api_key(icon, item):
    """Функция для изменения API ключа, вызываемая из pystray."""
    logging.info("Change API key menu item clicked. Scheduling GUI dialog.")
    root.after(0, show_api_key_dialog_and_handle_change)

def show_api_key_dialog_and_handle_change():
    """Показывает диалог и обрабатывает результат в главном потоке."""
    global API_KEY
    new_key = simpledialog.askstring("Изменить API ключ", "Введите новый API ключ:")
    
    if new_key and validate_api_key(new_key):
        if save_api_key_to_config(new_key):
            API_KEY = new_key
            messagebox.showinfo("Успех", "API ключ успешно обновлён.")
            logging.info("API key changed successfully.")
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить новый API ключ.")
    elif new_key and new_key != "CANCELLED":
        messagebox.showerror("Ошибка", "Неверный формат API ключа. Изменения не сохранены.")
    elif new_key is None or new_key == "CANCELLED":
        logging.info("Change API key cancelled by user.")
        

def setup_tray_icon():
    """Настраивает и запускает иконку в трее в отдельном потоке."""
    global icon
    try:
        icon_path = resource_path("app_icon.png")
        if os.path.exists(icon_path):
            image = Image.open(icon_path)
            logging.info(f"Loaded icon from: {icon_path}")
        else:
            logging.warning("Icon 'app_icon.png' not found. Creating a fallback image.")
            image = Image.new('RGB', (64, 64), 'black')
            
    except Exception as e:
        logging.error(f"Critical error loading icon: {e}")
        image = Image.new('RGB', (64, 64), 'black')
        
    menu = (item('Изменить API ключ', change_api_key),
            item('Выход', quit_app),)
    
    icon = Icon(APP_NAME, image, f"{APP_NAME} запущен", menu)
    icon.run()


def main():
    global root, API_KEY
    
    try:
        logging.info("Initializing Tkinter root.")
        root = tk.Tk()
        root.withdraw()
        
        atexit.register(send_disconnect_status)

        loaded_key = load_api_key_from_config()
        if loaded_key and validate_api_key(loaded_key):
            API_KEY = loaded_key
            logging.info("Using saved API key.")
        else:
            logging.info("API key not found or invalid. Prompting user for key.")
            api_key = simpledialog.askstring("Настройка API ключа", "Введите или вставьте ваш API ключ:")
            
            if api_key is None:
                messagebox.showwarning("Отмена", "API ключ не был введен. Приложение будет закрыто.")
                logging.info("API key input cancelled. Exiting.")
                sys.exit(0)
                
            if api_key and validate_api_key(api_key):
                if save_api_key_to_config(api_key):
                    API_KEY = api_key
                    logging.info("API key was successfully provided and saved.")
                else:
                    messagebox.showerror("Ошибка", "Не удалось сохранить API ключ")
                    logging.error("Failed to save new API key. Exiting.")
                    sys.exit(1)
            else:
                messagebox.showerror("Ошибка", "Неверный формат API ключа. Приложение будет закрыто.")
                logging.error("Invalid API key format. Exiting.")
                sys.exit(1)

        logging.info("Starting notification parser thread.")
        parser_thread = threading.Thread(target=notification_parser_thread)
        parser_thread.daemon = True
        parser_thread.start()
        
        logging.info("Starting tray icon thread.")
        icon_thread = threading.Thread(target=setup_tray_icon)
        icon_thread.daemon = True
        icon_thread.start()
        
        logging.info("Starting Tkinter main loop.")
        root.mainloop()
        logging.info("Tkinter main loop exited.")
        
    except Exception as e:
        logging.critical(f"Critical error in main function: {e}", exc_info=True)
        messagebox.showerror("Критическая ошибка", f"Произошла непредвиденная ошибка:\n{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
