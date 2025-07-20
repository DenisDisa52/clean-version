import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List

import google.generativeai as genai
from dotenv import load_dotenv
from google.generativeai.types import GenerationConfig

from database_manager import get_db_connection
from alerter import send_admin_alert

# --- Конфигурация ---
PROMPT_FILE = os.path.join('Prompts', 'token_matcher_prompt.txt')
TOKEN_LIST_FILE = 'base_currencies.txt'
API_KEY_NAME = "GEMINI_API_KEY_4"
MODEL_NAME = "gemini-2.5-pro"
ENV_FILE = '.env'

"""
Модуль для интеллектуального анализа контента.
Асинхронно обрабатывает сгенерированные статьи,
отправляя их Gemini для определения релевантных криптовалютных токенов.
Результат сохраняется в базе данных для каждой статьи.
"""
# --- Функции ---

def get_token_matching_tasks() -> List[Dict]:
    """Возвращает статьи, для которых нужно подобрать токены."""
    conn = get_db_connection()
    try:
        sql = "SELECT id, content FROM generated_articles WHERE matched_tokens IS NULL"
        cursor = conn.execute(sql)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if conn:
            conn.close()


def update_article_tokens(article_id: int, tokens: List[str]):
    """Обновляет список токенов для статьи."""
    conn = get_db_connection()
    try:
        # Сохраняем список как JSON-строку
        tokens_json = json.dumps(tokens)
        sql = "UPDATE generated_articles SET matched_tokens = ? WHERE id = ?"
        conn.execute(sql, (tokens_json, article_id))
        conn.commit()
    finally:
        if conn:
            conn.close()


async def match_tokens_for_article(task: Dict, prompt_template: str, token_list_str: str, api_key: str) -> List[str]:
    """Делает один запрос к AI для подбора токенов."""
    final_prompt = prompt_template.format(
        token_list=token_list_str,
        article_content=task['content']
    )
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        config = GenerationConfig(response_mime_type="application/json")
        response = await model.generate_content_async(contents=final_prompt, generation_config=config)

        matched_tokens = json.loads(response.text)
        if isinstance(matched_tokens, list):
            return matched_tokens
        return ["BTC"]  # Возвращаем BTC, если формат ответа некорректный
    except Exception as e:
        print(f"     [ERROR] Ошибка API при подборе токенов для статьи ID {task['id']}: {e}. Используем BTC.")
        return ["BTC"]  # Запасной вариант при любой ошибке


# --- Главная функция ---

async def async_run_matcher(tasks: List[Dict], prompt_template: str, token_list_str: str):
    load_dotenv(ENV_FILE)
    api_key = os.getenv(API_KEY_NAME)
    if not api_key:
        print(f"     [ERROR] API-ключ {API_KEY_NAME} не найден.")
        return

    # Асинхронно обрабатываем все задачи
    async_tasks = [match_tokens_for_article(task, prompt_template, token_list_str, api_key) for task in tasks]
    results = await asyncio.gather(*async_tasks)

    # Обновляем БД с результатами
    for task, tokens in zip(tasks, results):
        update_article_tokens(task['id'], tokens)
        print(f"     [SUCCESS] Для статьи ID {task['id']} подобраны токены: {tokens}")


def run_token_matcher() -> bool:
    print("  -> Запуск token_matcher.py...")

    try:
        prompt_template = Path(PROMPT_FILE).read_text(encoding='utf-8')
        token_list_str = Path(TOKEN_LIST_FILE).read_text(encoding='utf-8')
    except FileNotFoundError as e:
        print(f"     [ERROR] Не найден необходимый файл: {e}")
        return False

    tasks = get_token_matching_tasks()
    if not tasks:
        print("     [INFO] Нет статей для подбора токенов.")
        return True

    print(f"     Найдено {len(tasks)} статей для обработки. Запуск...")

    asyncio.run(async_run_matcher(tasks, prompt_template, token_list_str))

    print("     Подбор токенов завершен.")
    return True


if __name__ == '__main__':
    if run_token_matcher():
        print("\n--- Модуль Token Matcher успешно завершил работу ---")
    else:
        print("\n--- Работа модуля Token Matcher завершилась с ошибкой ---")