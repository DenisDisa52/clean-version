import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List

import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from dotenv import load_dotenv

from database_manager import (
    get_topics_by_status,
    get_last_published_titles,
    update_topic_with_title,
    update_topic_status
)

'''
Модуль-редактор, который асинхронно генерирует заголовки для тем.
Он находит в БД темы со статусом 'needs_title', использует Gemini 
и few-shot примеры, а затем обновляет записи в базе данных.
'''

# --- Конфигурация ---
CONFIG_FILENAME = 'title_formatter_config.json'
ENV_FILE = '.env'


# --- Вспомогательные функции ---

def load_config(filename: str) -> Dict[str, Any] | None:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"     [ERROR] Ошибка загрузки конфига {filename}: {e}")
        return None


def load_prompt(filename: str) -> str | None:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"     [ERROR] Файл с промптом '{filename}' не найден.")
        return None


def format_titles_for_prompt(titles: list) -> str:
    if not titles:
        return "Примеров для этой категории пока нет."
    return "\n".join([f"{i + 1}. {title}" for i, title in enumerate(titles)])


# --- Асинхронная логика ---

async def generate_single_title(topic: Dict, config: Dict, prompt_template: str, api_key: str) -> None:
    """Асинхронно генерирует и обновляет заголовок для одной темы."""
    topic_id = topic['id']

    try:
        # 1. Получаем примеры для промпта
        few_shot_examples = get_last_published_titles(
            topic['category'],
            limit=config.get('few_shot_limit', 10)
        )
        formatted_examples = format_titles_for_prompt(few_shot_examples)

        # 2. Формируем промпт
        final_prompt = prompt_template.format(
            news_text=topic['source_news_text'],
            category=topic['category'],
            example_titles=formatted_examples
        )

        # 3. Вызов Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(config['gemini_model'])
        generation_config = GenerationConfig(response_mime_type="application/json")

        response = await model.generate_content_async(contents=final_prompt, generation_config=generation_config)

        # 4. Обработка и обновление в БД
        response_data = json.loads(response.text)
        new_title = response_data.get('title')

        if new_title and isinstance(new_title, str):
            update_topic_with_title(topic_id, new_title)
            print(f"     [SUCCESS] Тема ID {topic_id}: сгенерирован заголовок.")
        else:
            raise ValueError("Ответ API не содержит валидного ключа 'title'.")

    except Exception as e:
        print(f"     [ERROR] Тема ID {topic_id}: {e}")
        update_topic_status(topic_id, 'title_generation_failed')


# --- Главная функция для вызова извне ---
async def async_run_formatter(tasks: List[Dict], config: Dict, prompt_template: str):
    """Управляет асинхронным выполнением задач."""
    api_key_names = config.get('api_key_names', [])
    api_keys = [os.getenv(key) for key in api_key_names if os.getenv(key)]
    if not api_keys:
        print("     [ERROR] API-ключи не найдены в .env")
        return

    task_queue = asyncio.Queue()
    for task in tasks:
        await task_queue.put(task)

    async def worker(worker_id: int, api_key: str):
        while not task_queue.empty():
            try:
                topic_task = task_queue.get_nowait()
                print(f"     [Worker {worker_id}] Взял в работу тему ID: {topic_task['id']}...")
                await generate_single_title(topic_task, config, prompt_template, api_key)
                print(f"     [Worker {worker_id}] Завершил тему ID: {topic_task['id']}. Пауза 2 сек.")
                await asyncio.sleep(2)  # Пауза для соблюдения лимитов
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                print(f"     [CRITICAL_WORKER_ERROR] Worker {worker_id} упал: {e}")

    workers = [worker(i + 1, api_key) for i, api_key in enumerate(api_keys)]
    await asyncio.gather(*workers)


def run_title_formatter() -> bool:
    """Основная синхронная обертка для запуска модуля."""
    print("  -> Запуск title_formatter.py...")
    load_dotenv(ENV_FILE)

    config = load_config(CONFIG_FILENAME)
    if not config: return False

    prompt_template = load_prompt(config['prompt_path'])
    if not prompt_template: return False

    tasks_to_process = get_topics_by_status('needs_title')
    if not tasks_to_process:
        print("     Нет новых тем для генерации заголовков. Пропускаем.")
        return True

    print(f"     Найдено {len(tasks_to_process)} тем для обработки. Запуск асинхронной генерации...")

    asyncio.run(async_run_formatter(tasks_to_process, config, prompt_template))

    print("     Генерация заголовков завершена.")
    return True


if __name__ == '__main__':
    print(f"--- Тестовый запуск title_formatter ---")
    if run_title_formatter():
        print("--- Модуль Title Formatter успешно завершил работу ---")
    else:
        print("--- Работа модуля Title Formatter завершилась с ошибкой ---")