import os
import sqlite3
import re
import time
import json
import threading
import requests
import tkinter as tk
from tkinter import messagebox, simpledialog
import winreg
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
    level=logging.WARNING,
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

# --- Глобальные переменные ---
API_KEY = None
stop_thread = threading.Event()
icon = None
root = None

def resource_path(relative_path):
    """ Gets the absolute path to a resource (works for .exe and .py) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def find_database_path():
    """Находит путь к базе данных уведомлений"""
    for db_path in DB_PATHS:
        if os.path.exists(db_path):
            return db_path
    return None

# --- Функции ---
def show_api_key_dialog():
    """Открывает стандартный диалог для ввода API ключа."""
    logging.info("Opening API key dialog")
    
    # Создаем модальное окно
    dialog = tk.Toplevel(root)
    dialog.title("Настройка API ключа")
    dialog.geometry("400x150")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()
    dialog.focus_set()
    
    # Центрируем окно
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
    y = (dialog.winfo_screenheight() // 2) - (150 // 2)
    dialog.geometry(f"400x150+{x}+{y}")
    
    # Создаем элементы интерфейса
    label = tk.Label(dialog, text="Пожалуйста, вставьте ваш API ключ:", pady=10)
    label.pack()
    
    api_var = tk.StringVar()
    entry = tk.Entry(dialog, textvariable=api_var, width=40)
    entry.pack(pady=5, padx=20)
    entry.focus_set()
    
    result = [None]
    
    def on_ok():
        result[0] = api_var.get()
        dialog.destroy()
    
    def on_cancel():
        dialog.destroy()
    
    def on_close():
        dialog.destroy()
    
    # Кнопки
    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=10)
    
    ok_button = tk.Button(button_frame, text="OK", width=10, command=on_ok)
    ok_button.pack(side=tk.LEFT, padx=10)
    
    cancel_button = tk.Button(button_frame, text="Cancel", width=10, command=on_cancel)
    cancel_button.pack(side=tk.LEFT, padx=10)
    
    # Обработчики событий
    dialog.protocol("WM_DELETE_WINDOW", on_close)
    entry.bind('<Return>', lambda e: on_ok())
    entry.bind('<Escape>', lambda e: on_cancel())
    
    # Ждем закрытия окна
    dialog.wait_window()
    
    return result[0]

def validate_api_key(api_key):
    """Проверяет валидность API ключа"""
    if not api_key or len(api_key.strip()) < 10:
        return False
    return True

def send_to_server(endpoint, payload, max_retries=3):
    if not API_KEY:
        return False

    headers = {'X-API-Key': API_KEY, 'Content-Type': 'application/json'}
    url = f"{SERVER_URL}{endpoint}"
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    
    return False

def get_registry_key_path():
    return f"Software\\{APP_NAME}"

def save_api_key(api_key):
    if not validate_api_key(api_key):
        messagebox.showerror("Ошибка", "Неверный формат API ключа")
        return False
        
    try:
        key_path = get_registry_key_path()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "APIKey", 0, winreg.REG_SZ, api_key)
        return True
    except Exception as e:
        logging.error(f"Error saving API key: {e}")
        messagebox.showerror("Ошибка", f"Не удалось сохранить API ключ: {e}")
        return False

def load_api_key():
    try:
        key_path = get_registry_key_path()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            api_key, _ = winreg.QueryValueEx(key, "APIKey")
            if validate_api_key(api_key):
                return api_key
            else:
                return None
    except FileNotFoundError:
        return None
    except Exception as e:
        logging.error(f"Error loading API key: {e}")
        return None

def send_disconnect_status():
    disconnect_payload = {
        "connected": False,
        "message": "Agent disconnected",
        "last_check": time.time()
    }
    send_to_server("/api/update_phone_status", disconnect_payload)

def parse_kaspi_notification(xml_payload):
    try:
        text_elements = re.findall(r'<text[^>]*>([^<]+)</text>', xml_payload)
        lines = [text.strip() for text in text_elements if text.strip()]
        
        amount, sender, message = None, None, None
        
        for line in lines:
            if "₸" in line:
                amount_match = re.search(r'([\d\s,]+)₸', line)
                if amount_match:
                    amount_str = amount_match.group(1).replace(' ', '').replace(',', '.')
                    try:
                        amount = float(amount_str)
                        break
                    except ValueError:
                        continue
        
        if not amount:
            return None

        for i, line in enumerate(lines):
            if "Пополнение:" in line and i + 1 < len(lines):
                sender_line = lines[i + 1]
                if ":" in sender_line:
                    parts = sender_line.split(":", 1)
                    sender = parts[0].strip()
                    message = parts[1].strip() if len(parts) > 1 else "Новый перевод!"
                else:
                    sender = sender_line
                break
        
        sender = sender or "Аноним"
        message = message or "Новый перевод!"
        
        return {"amount": amount, "sender": sender, "message": message}
        
    except Exception as e:
        return None

def notification_parser_thread():
    last_processed_id = 0
    
    while not stop_thread.is_set():
        db_path = find_database_path()
        phone_status = {
            "connected": db_path is not None,
            "message": "Database not found" if db_path is None else "Connected and tracking",
            "last_check": time.time()
        }
        
        if db_path:
            try:
                with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=5) as con:
                    cur = con.cursor()
                    if last_processed_id == 0:
                        cur.execute("SELECT MAX(ROWID) FROM Notification")
                        res = cur.fetchone()
                        last_processed_id = (res[0] if res and res[0] else 0)

                    cur.execute("SELECT ROWID, Payload FROM Notification WHERE ROWID > ?", (last_processed_id,))
                    rows = cur.fetchall()
                    
                    for rowid, payload_bytes in rows:
                        last_processed_id = rowid
                        if payload_bytes:
                            try:
                                payload_str = payload_bytes.decode('utf-8', errors='replace')
                                if 'Пополнение:' in payload_str or 'Перевод на сумму' in payload_str:
                                    donation_info = parse_kaspi_notification(payload_str)
                                    if donation_info:
                                        send_to_server("/api/submit_donation", {
                                            'name': donation_info['sender'],
                                            'amount': donation_info['amount'],
                                            'message': donation_info['message']
                                        })
                            except Exception:
                                pass
            
            except Exception:
                phone_status.update({"message": "Database error", "connected": False})
        
        send_to_server("/api/update_phone_status", phone_status)
        stop_thread.wait(2)

def quit_app(icon, item):
    """Корректное завершение приложения"""
    stop_thread.set()
    if icon:
        icon.stop()
    # Планируем выход из главного потока
    if root:
        root.after(100, lambda: root.quit())

def setup_tray_icon():
    global icon
    try:
        image = Image.open(resource_path("app_icon.png"))
    except Exception:
        image = Image.new('RGB', (64, 64), 'black')
        
    menu = (item('Выход', quit_app),)
    icon = Icon(APP_NAME, image, f"{APP_NAME} запущен", menu)
    icon.run()

def main():
    global API_KEY, root
    
    try:
        # Инициализация GUI в главном потоке
        root = tk.Tk()
        root.withdraw()
        
        atexit.register(send_disconnect_status)

        API_KEY = load_api_key()
        
        if not API_KEY:
            api_key = show_api_key_dialog()
            if api_key and validate_api_key(api_key):
                if save_api_key(api_key):
                    API_KEY = api_key
                else:
                    messagebox.showerror("Ошибка", "Не удалось сохранить API ключ")
                    sys.exit(1)
            else:
                messagebox.showwarning("Отмена", "API ключ не был введен")
                sys.exit(0)

        # Запуск фонового потока
        parser = threading.Thread(target=notification_parser_thread)
        parser.daemon = True
        parser.start()
        
        # Запуск иконки в трее
        setup_tray_icon()

    except Exception as e:
        messagebox.showerror("Ошибка", f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()