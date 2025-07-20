import os
import subprocess
import time
import requests
import pyautogui
from dotenv import load_dotenv

from alerter import send_admin_alert

'''
Модуль для управления VPN-соединением через ProtonVPN.
Использует команды CLI для запуска/остановки и pyautogui для взаимодействия с GUI.
Включает проверку IP для подтверждения статуса соединения.
'''

# --- Конфигурация ---
load_dotenv()
PROTON_VPN_PATH = r"C:\Program Files\Proton\VPN\ProtonVPN.Launcher.exe"
CONNECT_BUTTON_IMG = 'connect_button.png'
DISCONNECT_BUTTON_IMG = 'disconnect_button.png'
HOME_IP = os.getenv("HOME_IP_ADDRESS")
IP_CHECK_SERVICES = [
    "https://api.ipify.org",
    "https://ipinfo.io/ip",
    "https://icanhazip.com"
]


# --- Вспомогательные функции ---

def get_current_ip() -> str | None:
    """Пытается получить текущий IP, перебирая несколько сервисов."""
    for service in IP_CHECK_SERVICES:
        try:
            response = requests.get(service, timeout=10)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException:
            continue  # Пробуем следующий сервис
    return None


# --- Основные функции ---

def connect_vpn() -> bool:
    print("  -> Запуск vpn_manager.py (подключение)...")

    # 1. Запуск приложения
    print("     Шаг 1/5: Запуск приложения ProtonVPN...")
    try:
        subprocess.Popen([PROTON_VPN_PATH])
    except FileNotFoundError:
        print(f"     [ERROR] Не найден исполняемый файл ProtonVPN по пути: {PROTON_VPN_PATH}")
        return False

    # 2. "Умное" ожидание кнопки "Подключить"
    print("     Шаг 2/5: Активное ожидание кнопки 'Подключить' (до 5 минут)...")
    start_time = time.time()
    button_found = False
    while time.time() - start_time < 300:  # 300 секунд = 5 минут
        try:
            connect_button_location = pyautogui.locateCenterOnScreen(CONNECT_BUTTON_IMG, confidence=0.8)
            if connect_button_location:
                print("     >>> Кнопка 'Подключить' найдена!")
                button_found = True
                break
        except pyautogui.ImageNotFoundException:
            print("     ...кнопка пока не найдена, жду 15 секунд...")
            time.sleep(15)
            continue

    if not button_found:
        print("     [ERROR] Кнопка 'Подключить' не найдена за 5 минут.")
        send_admin_alert("🔥 *Критический сбой VPN:*\nКнопка 'Подключить' не найдена за 5 минут.")
        return False

    # 3. Нажатие кнопки
    print("     Шаг 3/5: Нажатие кнопки 'Подключить'...")
    try:
        pyautogui.click(connect_button_location)
        print("     Кнопка 'Подключить' нажата.")
    except Exception as e:
        print(f"     [ERROR] Ошибка pyautogui при нажатии: {e}")
        return False

    # 4. Пауза на установку соединения
    print("     Шаг 4/5: Ожидание 3 минуты для установки соединения...")
    time.sleep(180)

    # 5. Проверка IP
    print("     Шаг 5/5: Проверка IP-адреса...")
    current_ip = get_current_ip()
    if not current_ip:
        message = "Не удалось проверить IP. Все сервисы проверки недоступны."
        print(f"     [ERROR] {message}")
        send_admin_alert(f"🔥 *Критический сбой VPN:*\n{message}")
        return False

    if current_ip == HOME_IP:
        message = f"VPN не подключился. Текущий IP ({current_ip}) совпадает с домашним."
        print(f"     [ERROR] {message}")
        send_admin_alert(f"🔥 *Критический сбой VPN:*\n{message}")
        return False

    print(f"     [SUCCESS] VPN успешно подключен. Новый IP: {current_ip}")
    return True


def disconnect_vpn():
    print("  -> Запуск vpn_manager.py (отключение)...")

    # --- Попытка №1: Отключение через GUI (pyautogui) ---
    print("     Шаг 1/4: Попытка отключения через GUI...")
    try:
        disconnect_button_location = pyautogui.locateCenterOnScreen(DISCONNECT_BUTTON_IMG, confidence=0.8)
        if disconnect_button_location:
            pyautogui.click(disconnect_button_location)
            print("     Кнопка 'Отключить' нажата. Ожидание 1 минута...")
            time.sleep(60)
        else:
            print("     [INFO] Кнопка 'Отключить' не найдена, возможно VPN уже отключен.")
    except Exception as e:
        print(f"     [WARNING] Ошибка pyautogui при поиске кнопки 'Отключить': {e}")

    # --- Шаг 2: Проверка IP после первой попытки ---
    print("     Шаг 2/4: Проверка IP-адреса...")
    current_ip = get_current_ip()
    if current_ip == HOME_IP:
        print(f"     [SUCCESS] VPN успешно отключен (метод GUI). Текущий IP: {current_ip}")
        # Принудительно закроем приложение для чистоты
        subprocess.run(["taskkill", "/F", "/IM", "ProtonVPN.exe"], check=False, capture_output=True)
        return

    # --- Попытка №2: Отключение через CLI (если GUI не помог) ---
    print(f"     [INFO] IP ({current_ip}) все еще не домашний. Пробую отключение через CLI...")
    try:
        print("     Шаг 3/4: Отправка команды на отключение и принудительное закрытие...")
        subprocess.run([PROTON_VPN_PATH, "--disconnect"], check=True, timeout=60)
        subprocess.run(["taskkill", "/F", "/IM", "ProtonVPN.exe"], check=False, capture_output=True)

        print("     Шаг 4/4: Ожидание 30 секунд и финальная проверка IP...")
        time.sleep(30)

        final_ip = get_current_ip()
        if final_ip == HOME_IP:
            print(f"     [SUCCESS] VPN успешно отключен (метод CLI). Текущий IP: {final_ip}")
        else:
            print(f"     [WARNING] VPN отключен, но IP ({final_ip}) все еще не совпадает с домашним.")

    except Exception as e:
        print(f"     [ERROR] Ошибка при отключении VPN через CLI: {e}")


if __name__ == '__main__':
    # --- Тестовый блок ТОЛЬКО для отключения ---
    print("--- Тестовый запуск ТОЛЬКО функции отключения VPN ---")
    if not HOME_IP:
        print("!!! ВНИМАНИЕ: Для теста необходимо добавить HOME_IP_ADDRESS в ваш .env файл !!!")
    else:
        disconnect_vpn()