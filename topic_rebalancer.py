import os
import json
import time
import itertools
import asyncio
from pathlib import Path
from typing import List, Dict, Any
import sqlite3

import google.generativeai as genai
from dotenv import load_dotenv
from google.generativeai.types import GenerationConfig

from database_manager import get_db_connection

'''
Модуль выполняет финальную, редакционную категоризацию новостей.
Использует асинхронный подход для параллельной обработки с помощью 
нескольких API-ключей Gemini.
'''

# --- КОНФИГУРАЦИЯ ---
REBALANCER_CONFIG_FILE = 'rebalancer_config.json'
CATEGORIZER_CONFIG_FILE = 'topic_categorizer_config.json'
ENV_FILE = '.env'


# --- Вспомогательные функции (без изменений) ---
def load_config(config_path: str) -> dict | None:
    # ... (код без изменений)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"     [ERROR] Ошибка загрузки конфига {config_path}: {e}")
        return None


def get_input_data(date_str: str, categorizer_config: dict) -> List[Dict[str, str]] | None:
    # ... (код без изменений)
    try:
        input_dir = Path(categorizer_config['output_directory'])
        filename_template = categorizer_config['output_filename_template']
        filename = filename_template.format(date_str=date_str)
        filepath = input_dir / filename

        if not filepath.exists():
            print(f"     [ERROR] Входной файл не найден: {filepath}")
            return None

        print(f"     Чтение данных из: {filepath.name}")
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except (KeyError, IOError, json.JSONDecodeError) as e:
        print(f"     [ERROR] Ошибка при чтении входного файла: {e}")
        return None


def format_stats_to_string(stats_dict: dict) -> str:
    # ... (код без изменений)
    return "\n".join([f"- {key}: {value}" for key, value in stats_dict.items()])


# --- НОВАЯ АСИНХРОННАЯ ЛОГИКА РЕБАЛАНСИРОВКИ ---
async def rebalance_topics(initial_data: List[Dict[str, str]], config: Dict[str, Any]) -> List[Dict[str, str]] | None:
    try:
        prompt_path = Path(config['prompt_path'])
        model_name = config['gemini_model']
        api_key_names = config['api_key_names']
        target_ratio = config['target_topic_ratio']
    except KeyError as e:
        print(f"     [ERROR] В {REBALANCER_CONFIG_FILE} отсутствует ключ: {e}")
        return None

    prompt_template = prompt_path.read_text(encoding='utf-8')
    api_keys = [os.getenv(key_name) for key_name in api_key_names if os.getenv(key_name)]
    if not api_keys:
        print(f"     [ERROR] API-ключи не найдены в .env")
        return None
    print(f"     Найдено {len(api_keys)} API-ключей. Запуск асинхронной перебалансировки...")

    total_news = len(initial_data)
    total_ratio_points = sum(target_ratio.values())
    daily_target_dist = {k: round((v / total_ratio_points) * total_news) for k, v in target_ratio.items()}
    print("     Рассчитана дневная цель по темам:", daily_target_dist)

    results = []
    task_queue = asyncio.Queue()
    for index, item in enumerate(initial_data):
        await task_queue.put((index, item))

    async def worker(worker_id: int, api_key: str):
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        generation_config = GenerationConfig(response_mime_type="application/json")

        session_tally = {key: 0 for key in target_ratio.keys()}
        target_dist_str = format_stats_to_string(daily_target_dist)
        category_list_str = str(list(target_ratio.keys()))

        while not task_queue.empty():
            try:
                index, news_item = task_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            print(f"     [Worker {worker_id}] Взял в работу новость #{index + 1}...")

            session_tally_str = format_stats_to_string(session_tally)
            format_args = {
                'target_dist_string': target_dist_str, 'session_tally_string': session_tally_str,
                'overall_stats_string': "N/A", 'news_text': news_item['news_text'],
                'initial_category': news_item['initial_category'], 'category_list': category_list_str
            }
            final_prompt = prompt_template.format(**format_args)
            final_category = news_item['initial_category']

            try:
                response = await model.generate_content_async(contents=final_prompt,
                                                              generation_config=generation_config)
                parsed_json = json.loads(response.text)
                candidate_category = parsed_json.get("final_category")
                if candidate_category in target_ratio:
                    final_category = candidate_category
            except Exception as e:
                print(
                    f"       [Worker {worker_id}] Ошибка API/JSON для новости #{index + 1}: {e}. Используем исходную категорию.")

            results.append({'news_text': news_item['news_text'], 'category': final_category, 'original_index': index})
            session_tally[final_category] += 1

            print(f"     [Worker {worker_id}] Завершил новость #{index + 1}. Пауза 2 сек...")
            await asyncio.sleep(2)  # <--- НАШ ПРЕДОХРАНИТЕЛЬ

    workers = [worker(i + 1, api_key) for i, api_key in enumerate(api_keys)]
    await asyncio.gather(*workers)

    # Сортируем результаты, чтобы они были в исходном порядке
    results.sort(key=lambda x: x['original_index'])
    print("     Асинхронная перебалансировка завершена.")
    return results


# --- Функция сохранения в БД  ---
def save_topics_to_db(rebalanced_data: List[Dict[str, str]]) -> bool:

    if not rebalanced_data:
        print("     Нет данных для сохранения в БД.")
        return True
    to_insert = [
        (item['category'], 'needs_title', item['news_text'])
        for item in rebalanced_data
    ]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO topics (category, status, source_news_text) VALUES (?, ?, ?)"
        cursor.executemany(sql, to_insert)
        conn.commit()
        print(f"     Успешно добавлено {cursor.rowcount} тем в базу данных со статусом 'needs_title'.")
        return True
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при сохранении тем в БД: {e}")
        return False
    finally:
        if conn:
            conn.close()


# --- Главная функция, адаптированная для вызова async ---
def run_topic_rebalancer(target_date: str) -> bool:
    print("  -> Запуск topic_rebalancer.py...")
    load_dotenv(ENV_FILE)

    rebalancer_config = load_config(REBALANCER_CONFIG_FILE)
    categorizer_config = load_config(CATEGORIZER_CONFIG_FILE)
    if not rebalancer_config or not categorizer_config: return False

    initial_news_data = get_input_data(target_date, categorizer_config)
    if initial_news_data is None: return False
    if not initial_news_data:
        print("     Нет данных для ребалансировки. Пропускаем.")
        return True

    # Запускаем асинхронную функцию
    rebalanced_news = asyncio.run(rebalance_topics(initial_news_data, rebalancer_config))

    if rebalanced_news is None: return False

    return save_topics_to_db(rebalanced_news)


if __name__ == '__main__':
    from datetime import date, timedelta

    test_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"--- Тестовый запуск topic_rebalancer для даты: {test_date} ---")

    start_time = time.time()
    if run_topic_rebalancer(target_date=test_date):
        print("--- Модуль Topic Rebalancer успешно завершил работу ---")
    else:
        print("--- Работа модуля Topic Rebalancer завершилась с ошибкой ---")
    end_time = time.time()
    print(f"Общее время выполнения: {end_time - start_time:.2f} секунд.")