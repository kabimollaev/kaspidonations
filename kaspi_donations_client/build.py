import os
import shutil
import subprocess
import pystray
import sys

# --- КОНФИГУРАЦИЯ ---
SCRIPT_NAME = 'agent.py'
EXE_NAME = 'KaspiDonationsAgent'
PNG_ICON_PATH = 'app_icon.png'
ICO_ICON_PATH = 'app_icon.ico'

def create_ico_from_png():
    """Проверяет наличие .ico и создает его из .png при необходимости."""
    if not os.path.exists(ICO_ICON_PATH):
        try:
            from PIL import Image
            if os.path.exists(PNG_ICON_PATH):
                print(f"Создание {ICO_ICON_PATH} из {PNG_ICON_PATH}...")
                img = Image.open(PNG_ICON_PATH)
                img.save(ICO_ICON_PATH, format='ICO', sizes=[(256, 256)])
                print("Иконка успешно создана.")
                return True
            else:
                print(f"ПРЕДУПРЕЖДЕНИЕ: {PNG_ICON_PATH} не найден. Приложение будет без иконки.")
                return False
        except ImportError:
            print("\nПРЕДУПРЕЖДЕНИЕ: Библиотека Pillow не установлена.")
            print("Для создания иконки выполните: pip install Pillow")
            return False
        except Exception as e:
            print(f"Ошибка при создании иконки: {e}")
            return False
    return True

def build_executable():
    """Собирает .exe файл с помощью PyInstaller."""
    # 1. Устанавливаем зависимости
    print("\nУстановка/обновление зависимостей...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'requests', 'pystray', 'pillow', 'pyinstaller'], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Ошибка при установке зависимостей: {e}")
        return

    # 2. Создаем иконку
    has_icon = create_ico_from_png()

    # 3. Формируем команду для PyInstaller
    command = [
        'pyinstaller',
        '--noconfirm',
        '--onefile',
        '--noconsole',
        f'--name={EXE_NAME}',
    ]

    # Встраиваем иконку PNG как ресурс
    if os.path.exists(PNG_ICON_PATH):
        command.extend(['--add-data', f'{PNG_ICON_PATH}{os.pathsep}.'])

    # Устанавливаем иконку для .exe файла
    if has_icon and os.path.exists(ICO_ICON_PATH):
        command.append(f'--icon={ICO_ICON_PATH}')

    command.append(SCRIPT_NAME)

    # 4. Запускаем сборку
    print("\n--- НАЧАЛО СБОРКИ ПРИЛОЖЕНИЯ ---")
    print(f"Команда: {' '.join(command)}")
    try:
        subprocess.run(command, check=True)
        print("\n--- СБОРКА УСПЕШНО ЗАВЕРШЕНА ---")
        
        # 5. Очистка временных файлов
        print("Очистка временных файлов...")
        final_exe_path = os.path.join('dist', f'{EXE_NAME}.exe')
        if os.path.exists(final_exe_path):
            if os.path.exists(f'{EXE_NAME}.exe'):
                os.remove(f'{EXE_NAME}.exe')
            shutil.move(final_exe_path, f'{EXE_NAME}.exe')
            
        for item in ['dist', 'build', f'{EXE_NAME}.spec', ICO_ICON_PATH]:
            if os.path.exists(item):
                if os.path.isdir(item):
                    shutil.rmtree(item)
                else:
                    os.remove(item)
        
        print(f"\n✅ Готово! Ваш файл '{EXE_NAME}.exe' находится в этой же папке.")

    except FileNotFoundError:
        print("\n--- ОШИБКА ---")
        print("PyInstaller не найден. Убедитесь, что Python и pip добавлены в PATH.")
    except subprocess.CalledProcessError as e:
        print(f"\n--- ОШИБКА СБОРКИ ---")
        print(f"Процесс сборки завершился с ошибкой: {e}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")

if __name__ == '__main__':
    build_executable()

