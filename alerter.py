import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

"""
Модуль для отправки экстренных уведомлений администратору проекта в Telegram.
"""

def send_admin_alert(message: str):
    """Отправляет уведомление об ошибке администратору."""
    if not BOT_TOKEN or not ADMIN_ID:
        print("ПРЕДУПРЕЖДЕНИЕ: Не могу отправить алерт. BOT_TOKEN или ADMIN_ID не найдены в .env")
        return

    # Формируем URL для запроса к Telegram Bot API
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # Формируем данные для отправки
    payload = {
        'chat_id': ADMIN_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }

    try:
        # Отправляем POST-запрос. Мы используем requests, чтобы не смешивать с логикой telegram_bot.py
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"✅ Уведомление администратору успешно отправлено.")
        else:
            print(f"❌ Ошибка при отправке уведомления: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        print(f"❌ Критическая ошибка сети при отправке уведомления: {e}")


if __name__ == '__main__':
    # Тест для проверки работы функции
    print("Тестирование отправки уведомления администратору...")
    send_admin_alert("🤖 *Тестовое сообщение* от `alerter.py`.\nЕсли вы это видите, система оповещений работает.")