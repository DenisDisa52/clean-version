import asyncio
import json
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

"""
Утилита для первоначальной настройки.
Создает файл сессии Telethon (.session) для аутентификации аккаунта в Telegram.
"""

# --- Константы ---
SESSION_NAME = 'my_minimal_session'
APP_CONFIG_FILENAME = 'telegram_config.json'


def load_app_config():
    """Загружает api_id и api_hash из файла конфигурации."""
    if not os.path.exists(APP_CONFIG_FILENAME):
        print(f"Ошибка: Файл конфигурации '{APP_CONFIG_FILENAME}' не найден.")
        print("Пожалуйста, создайте его с вашими api_id и api_hash.")
        return None, None
    try:
        with open(APP_CONFIG_FILENAME, 'r', encoding='utf-8') as f:
            config = json.load(f)
            api_id = config.get('api_id')
            api_hash = config.get('api_hash')
            if not api_id or not api_hash:
                print(f"Ошибка: 'api_id' или 'api_hash' отсутствуют в файле '{APP_CONFIG_FILENAME}'.")
                return None, None
            return api_id, api_hash
    except json.JSONDecodeError:
        print(f"Ошибка: Неверный формат JSON в файле '{APP_CONFIG_FILENAME}'.")
        return None, None
    except Exception as e:
        print(f"Произошла непредвиденная ошибка при чтении конфига: {e}")
        return None, None


async def main():
    """
    Основная функция для интерактивного создания сессии Telethon.
    """
    session_file = SESSION_NAME + '.session'
    if os.path.exists(session_file):
        print(f"Файл сессии '{session_file}' уже существует. Настройка не требуется.")
        return

    print("--- Создание новой сессии Telegram ---")
    api_id, api_hash = load_app_config()
    if not api_id or not api_hash:
        return

    # Инициализируем клиент
    client = TelegramClient(SESSION_NAME, api_id, api_hash)

    try:
        await client.connect()

        # Если клиент не авторизован, запускаем процесс входа
        if not await client.is_user_authorized():
            phone_number = input("Введите ваш номер телефона (в международном формате, например, +12345678900): ")
            await client.send_code_request(phone_number)
            try:
                code = input('Введите код, который вы получили от Telegram: ')
                await client.sign_in(phone_number, code)
            except SessionPasswordNeededError:
                password = input('У вас включена двухфакторная аутентификация. Введите ваш пароль: ')
                await client.sign_in(password=password)

        # Проверяем результат
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"\nУспешно! Сессия для пользователя '{me.first_name}' (ID: {me.id}) создана.")
            print(f"Файл сессии сохранен как '{session_file}'.")
        else:
            print("\nНе удалось авторизоваться. Пожалуйста, проверьте введенные данные и попробуйте снова.")

    except Exception as e:
        print(f"\nПроизошла критическая ошибка: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
        print("Работа скрипта завершена.")


if __name__ == '__main__':
    asyncio.run(main())