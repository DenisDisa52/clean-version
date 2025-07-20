import os
import json
import sqlite3
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
import google.generativeai as genai
from dotenv import load_dotenv
from google.generativeai.types import GenerationConfig

from alerter import send_admin_alert
from database_manager import get_db_connection

'''
Модуль еженедельного стратегического планирования.
Запускает "Content Strategist" промпт, получает от Gemini детальный план
на неделю для каждой персоны и записывает его в базу данных.
Также обновляет rebalancer_config.json.
'''

# --- Конфигурация ---
REBALANCER_CONFIG_FILE = 'rebalancer_config.json'
STRATEGIC_PROMPT_FILE = os.path.join('Prompts', 'strategic_planner_prompt_en.txt')
ENV_FILE = '.env'


# --- Вспомогательные функции ---
def load_config(config_path: str) -> dict | None:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"     [ERROR] Ошибка загрузки конфига {config_path}: {e}")
        return None


def save_json_file(data: dict, filepath: str) -> bool:
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        print(f"     [ERROR] Ошибка при сохранении файла {filepath}: {e}")
        return False


def get_strategic_plan(prompt: str, config: dict) -> dict | None:
    api_key_names = config.get('api_key_names', [])
    api_keys = [os.getenv(key) for key in api_key_names if os.getenv(key)]
    if not api_keys:
        print("     [ERROR] API-ключи для стратега не найдены в .env")
        return None

    model_name = config.get('gemini_model', 'gemini-2.5-pro')
    generation_config = GenerationConfig(
        response_mime_type="application/json",
        temperature=0.9
    )

    for i, api_key in enumerate(api_keys):
        print(f"     Попытка {i + 1}/{len(api_keys)} с ключом ...{api_key[-4:]}")
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(contents=prompt, generation_config=generation_config)
            parsed_response = json.loads(response.text)
            print("     Успешный ответ и парсинг JSON получен.")
            return parsed_response
        except Exception as e:
            print(f"     [ERROR] Ошибка с ключом ...{api_key[-4:]}: {e}")
            continue

    print("     [CRITICAL] Ни один из API-ключей не сработал.")
    return None


def save_plan_to_db(plan_json: dict, personas_map: dict) -> bool:
    """Парсит JSON от Gemini и сохраняет детальный план по дням в таблицу weekly_plan."""
    try:
        author_plan_by_day = plan_json['author_plan_by_day']
        category_dist = plan_json['category_distribution_by_author']

        today = date.today()
        # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
        week_start_date = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')

        to_insert = []

        for persona_code, daily_counts in author_plan_by_day.items():
            if persona_code not in personas_map:
                print(f"     [WARNING] Персона '{persona_code}' из плана не найдена в БД. Пропускаем.")
                continue

            persona_id = personas_map[persona_code]
            persona_categories = category_dist.get(persona_code, {})

            category_pool = []
            for category, count in persona_categories.items():
                category_pool.extend([category] * count)

            # Распределяем категории по дням
            day_keys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for day in day_keys:
                num_articles = daily_counts.get(day, 0)
                categories_for_day = category_pool[:num_articles]
                category_pool = category_pool[num_articles:]

                day_category_counts = defaultdict(int)
                for cat in categories_for_day:
                    day_category_counts[cat] += 1

                for category, count in day_category_counts.items():
                    to_insert.append((week_start_date, day, persona_id, category, count))

        if not to_insert:
            print("     [ERROR] Не удалось сформировать данные для записи в БД.")
            return False

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM weekly_plan WHERE week_start_date = ?", (week_start_date,))
        print(f"     Удален старый план на неделю, начинающуюся с {week_start_date}.")

        sql = "INSERT INTO weekly_plan (week_start_date, day_of_week, persona_id, category, target_count) VALUES (?, ?, ?, ?, ?)"
        cursor.executemany(sql, to_insert)
        conn.commit()
        print(f"     Успешно сохранено {cursor.rowcount} записей о плане в БД.")
        return True

    except (KeyError, sqlite3.Error) as e:
        print(f"     [ERROR] Ошибка при обработке плана или записи в БД: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_personas_map() -> dict:
    """Возвращает словарь {persona_code: id} из БД."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("SELECT id, persona_code FROM personas")
        return {row['persona_code']: row['id'] for row in cursor.fetchall()}
    finally:
        if conn:
            conn.close()


def run_strategic_planner() -> bool:
    print("\n--- Запуск модуля Strategic Planner ---")
    load_dotenv(ENV_FILE)

    rebalancer_config = load_config(REBALANCER_CONFIG_FILE)
    if not rebalancer_config:
        send_admin_alert(f"🔥 *Критический сбой в Strategic Planner:*\nНе удалось загрузить `{REBALANCER_CONFIG_FILE}`")
        return False

    try:
        prompt_text = Path(STRATEGIC_PROMPT_FILE).read_text(encoding='utf-8')
    except FileNotFoundError:
        send_admin_alert(f"🔥 *Критический сбой в Strategic Planner:*\nНе найден файл `{STRATEGIC_PROMPT_FILE}`")
        return False

    plan_json = get_strategic_plan(prompt_text, rebalancer_config)

    if plan_json and 'target_topic_ratio' in plan_json and 'category_distribution_by_author' in plan_json:
        rebalancer_config['target_topic_ratio'] = plan_json['target_topic_ratio']
        save_json_file(rebalancer_config, REBALANCER_CONFIG_FILE)
        print(f"     Конфигурация {REBALANCER_CONFIG_FILE} успешно обновлена.")

        personas_map = get_personas_map()
        if not save_plan_to_db(plan_json, personas_map):
            send_admin_alert("⚠️ *Сбой в Strategic Planner:*\nНе удалось сохранить детальный план в БД.")
            return True

        return True
    else:
        error_message = "Не удалось получить или распарсить стратегический план от Gemini. Используется план с прошлой недели."
        print(f"     [WARNING] {error_message}")
        send_admin_alert(f"⚠️ *Сбой в Strategic Planner:*\n{error_message}")
        return True


if __name__ == '__main__':
    if run_strategic_planner():
        print("--- Модуль Strategic Planner успешно завершил работу ---")
    else:
        print("--- Работа модуля Strategic Planner завершилась с критической ошибкой ---")