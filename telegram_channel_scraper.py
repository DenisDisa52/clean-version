import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta, date
import pytz
from telethon import TelegramClient
from dotenv import load_dotenv
import google.generativeai as genai

"""
Автоматически собирает новостные сводки из заданных Telegram-каналов.
Если готовая сводка не найдена, скрипт самостоятельно собирает посты за день
и генерирует сводку с помощью Gemini API.
"""

# --- Константы и Конфигурация ---
SESSION_NAME = 'my_minimal_session'
APP_CONFIG_FILENAME = 'telegram_config.json'
SCRAPER_CONFIG_FILENAME = 'scraper_config.json'
PROMPT_FILENAME = os.path.join('Prompts', 'summarize_raw_posts_prompt.txt')
GEMINI_API_KEYS = ['GEMINI_API_KEY_13', 'GEMINI_API_KEY_12']
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


# --- Вспомогательные функции ---

def load_config(filename):
    if not os.path.exists(filename):
        print(f"Ошибка: Файл конфигурации '{filename}' не найден.")
        return None
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Ошибка: Неверный формат JSON в файле '{filename}'.")
        return None


def load_prompt(filename):
    if not os.path.exists(filename):
        print(f"Ошибка: Файл с промптом '{filename}' не найден.")
        return None
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()


def get_target_date() -> date:
    now_msk = datetime.now(MOSCOW_TZ)
    return (now_msk - timedelta(days=1)).date()


# --- Логика фильтров для поиска готовых сводок ---

def is_decenter_summary(text: str, post_date_msk: datetime, target_date: date) -> bool:
    first_line = text.split('\n', 1)[0].lower()
    if "итоги дня" in first_line and post_date_msk.hour >= 18:
        day_pattern = r'\b0?' + re.escape(str(target_date.day)) + r'\b'
        if re.search(day_pattern, first_line):
            months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня",
                         "июля", "августа", "сентября", "октября", "ноября", "декабря"]
            target_month_ru = months_ru[target_date.month - 1]
            if target_month_ru[:-1] in first_line:
                return True
    return False


def is_forklog_summary(text: str, post_date_msk: datetime, target_date: date) -> bool:
    start_time = MOSCOW_TZ.localize(
        datetime.combine(target_date, datetime.min.time()) + timedelta(hours=19, minutes=30))
    end_time = start_time + timedelta(hours=5, minutes=30)
    link_count = text.count('https://')
    if link_count > 5 and start_time <= post_date_msk < end_time:
        return True
    return False


def is_cointelegraph_summary(text: str, post_date_msk: datetime, target_date: date) -> bool:
    if "catch up on the news" in text.lower():
        if post_date_msk.date() == target_date + timedelta(days=1):
            return True
    return False


FILTER_MAPPING = {
    'decenter': is_decenter_summary,
    'forklog': is_forklog_summary,
    'cointelegraph': is_cointelegraph_summary,
}


# --- Основная логика парсера ---

def _blocking_gemini_call(api_key: str, prompt: str) -> str:
    genai.configure(api_key=api_key)
    generation_config = genai.types.GenerationConfig(
        temperature=0.3,
    )
    model = genai.GenerativeModel("gemini-2.5-pro", # PRO
        generation_config=generation_config)
    response = model.generate_content(contents=prompt)
    return response.text


async def generate_summary_with_gemini(raw_text: str, prompt_template: str) -> str:
    print(f"Собрано {len(raw_text)} символов. Отправка запроса в Gemini...")
    load_dotenv()

    last_error = None
    for key_name in GEMINI_API_KEYS:
        api_key = os.getenv(key_name)
        if not api_key:
            print(f"Предупреждение: API-ключ '{key_name}' не найден в .env файле.")
            continue

        try:
            print(f"Попытка с ключом: ...{key_name[-4:]}")
            full_prompt = prompt_template.format(raw_posts_text=raw_text)
            loop = asyncio.get_running_loop()
            response_text = await loop.run_in_executor(
                None, _blocking_gemini_call, api_key, full_prompt
            )
            print("Сводка от Gemini успешно получена.")
            return response_text
        except Exception as e:
            print(f"Ошибка с ключом ...{key_name[-4:]}: {e}")
            last_error = e
            continue  # Пробуем следующий ключ

    print("Все API-ключи Gemini не сработали.")
    return f"Ошибка генерации сводки: {last_error}"


async def process_channel(client: TelegramClient, channel_config: dict, target_date: date, prompt_template: str):
    channel_username = channel_config['username']
    channel_name = channel_config['name']
    filter_function = FILTER_MAPPING.get(channel_config.get('custom_filter_type'))

    print(f"\n--- Обработка канала: {channel_name} ---")

    start_of_day = MOSCOW_TZ.localize(datetime.combine(target_date, datetime.min.time()))

    if filter_function:
        print("Этап 1: Поиск готовой сводки...")
        async for message in client.iter_messages(channel_username):
            if not message.text or not message.date:
                continue

            post_date_msk = message.date.astimezone(MOSCOW_TZ)

            if post_date_msk < start_of_day:
                print("Достигнута дата старше целевой, сводка не найдена.")
                break

            if filter_function(message.text, post_date_msk, target_date):
                print(f"Найдена готовая сводка в '{channel_name}'.")
                return {'channel_name': channel_name, 'text': message.text, 'source': 'native'}

    print(f"Этап 2: Запускаю точный сбор постов за {target_date}...")
    posts_text = []
    end_of_day = start_of_day + timedelta(days=1)

    async for message in client.iter_messages(channel_username):
        if not message.text or not message.date:
            continue

        post_date_msk = message.date.astimezone(MOSCOW_TZ)

        if post_date_msk < start_of_day:
            break

        if start_of_day <= post_date_msk < end_of_day:
            posts_text.append(message.text)

    if not posts_text:
        print(f"Не найдено ни одного поста в канале '{channel_name}' за {target_date}.")
        return {'channel_name': channel_name, 'text': f"Не найдено постов для анализа за {target_date}.",
                'source': 'error'}

    posts_text.reverse()
    raw_text_for_ai = "\n\n---\n\n".join(posts_text)

    generated_summary = await generate_summary_with_gemini(raw_text_for_ai, prompt_template)
    print("\n--- Ответ от Gemini: ---", generated_summary, "--- Конец ответа Gemini ---\n", sep='\n')
    return {'channel_name': channel_name, 'text': generated_summary, 'source': 'generated'}


async def main():
    if not os.path.exists(SESSION_NAME + '.session'):
        print(f"Ошибка: Файл сессии '{SESSION_NAME}.session' не найден.")
        return

    app_config = load_config(APP_CONFIG_FILENAME)
    scraper_config = load_config(SCRAPER_CONFIG_FILENAME)
    prompt_template = load_prompt(PROMPT_FILENAME)

    if not all([app_config, scraper_config, prompt_template]):
        print("Один из необходимых файлов конфигурации отсутствует или поврежден.")
        return

    client = TelegramClient(SESSION_NAME, app_config['api_id'], app_config['api_hash'])
    all_summaries = []

    try:
        await client.start()
        print("Успешно подключено к Telegram.")

        target_date_for_summaries = get_target_date()
        print(f"Целевая дата для поиска сводок: {target_date_for_summaries.strftime('%Y-%m-%d')}")

        channels = scraper_config['channels']
        pause_duration = scraper_config.get('pause_between_channels', 120)

        for i, channel_conf in enumerate(channels):
            start_time = time.monotonic()

            try:
                summary_data = await process_channel(client, channel_conf, target_date_for_summaries, prompt_template)
                all_summaries.append(summary_data)
            except Exception as e:
                print(f"Критическая ошибка при обработке канала {channel_conf['name']}: {e}")
                all_summaries.append({'channel_name': channel_conf['name'], 'text': f"Ошибка обработки: {e}",
                                      'source': 'critical_error'})

            if i < len(channels) - 1:
                elapsed_time = time.monotonic() - start_time
                wait_time = max(0, pause_duration - elapsed_time)
                if wait_time > 0:
                    print(f"\n--- Пауза на {wait_time:.1f} секунд ---")
                    await asyncio.sleep(wait_time)

        output_dir = scraper_config['output_directory']
        os.makedirs(output_dir, exist_ok=True)
        filename = scraper_config['output_filename_template'].format(
            date_str=target_date_for_summaries.strftime('%Y-%m-%d'))
        output_filepath = os.path.join(output_dir, filename)

        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(f"Итоговая сводка новостей за {target_date_for_summaries.strftime('%d.%m.%Y')}\n")
            f.write("=" * 40 + "\n\n")
            for summary in all_summaries:
                f.write(f"Канал: {summary['channel_name']} (Источник: {summary['source']})\n")
                f.write("---\n")
                f.write(summary['text'].strip() + "\n\n")
                f.write("=" * 40 + "\n\n")

        print(f"\nВсе каналы обработаны. Результат сохранен в файл: {output_filepath}")

    except Exception as e:
        print(f"\nПроизошла глобальная ошибка: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
        print("Работа скрипта завершена.")


if __name__ == '__main__':
    asyncio.run(main())