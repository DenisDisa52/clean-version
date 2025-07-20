import os
import json
from pathlib import Path
from typing import List, Dict, Any

import google.generativeai as genai
import numpy as np
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity

'''
Модуль анализирует мастер-сводку новостей. Используя векторные представления (эмбеддинги), 
он определяет и присваивает каждой новости наиболее подходящую техническую категорию, 
сохраняя результат в JSON-файл для дальнейшей редакционной перебалансировки.
'''

# --- КОНФИГУРАЦИЯ ---
CATEGORIZER_CONFIG_FILE = 'topic_categorizer_config.json'
SUMMARIZER_CONFIG_FILE = 'summarizer_config.json'
ENV_FILE = '.env'


# --- Вспомогательные функции ---

def load_config(config_path: str) -> dict | None:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"     [ERROR] Ошибка загрузки конфига {config_path}: {e}")
        return None


def get_input_filepath(date_str: str, summarizer_config: dict) -> Path | None:
    try:
        input_dir = Path(summarizer_config['output_directory'])
        filename_template = summarizer_config['output_filename_template']
        filename = filename_template.format(date_str=date_str)
        filepath = input_dir / filename
        if not filepath.exists():
            print(f"     [ERROR] Входной файл мастер-сводки не найден: {filepath}")
            return None
        return filepath
    except KeyError as e:
        print(f"     [ERROR] В файле {SUMMARIZER_CONFIG_FILE} отсутствует ключ: {e}")
        return None


def parse_master_summary(filepath: Path) -> List[str]:
    print(f"     Парсинг мастер-сводки: {filepath.name}")
    full_text = filepath.read_text(encoding='utf-8').strip()
    if not full_text:
        print("     [WARNING] Файл мастер-сводки пуст.")
        return []
    news_items = full_text.split('\n\n')
    cleaned_news = [item.strip() for item in news_items if item.strip()]
    print(f"     Найдено {len(cleaned_news)} новостей для категоризации.")
    return cleaned_news


def get_embeddings(texts: List[str], model_name: str, api_key: str) -> np.ndarray | None:
    print(f"     Получение эмбеддингов для {len(texts)} текстов ({model_name})...")
    try:
        genai.configure(api_key=api_key)
        result = genai.embed_content(model=model_name, content=texts, task_type="CLUSTERING")
        print("     Эмбеддинги успешно получены.")
        return np.array(result['embedding'])
    except Exception as e:
        print(f"     [ERROR] при получении эмбеддингов: {e}")
        return None


def categorize_news(news_items: List[str], config: Dict[str, Any]) -> List[Dict[str, str]] | None:
    try:
        categories = config['categories']
        model_name = config['gemini_embedding_model']
        api_key_name = config['gemini_api_key_name']
        gemini_api_key = os.getenv(api_key_name)
    except KeyError as e:
        print(f"     [ERROR] В {CATEGORIZER_CONFIG_FILE} отсутствует ключ: {e}")
        return None

    if not gemini_api_key:
        print(f"     [ERROR] API-ключ '{api_key_name}' не найден в .env файле.")
        return None

    news_embeddings = get_embeddings(news_items, model_name, gemini_api_key)
    category_embeddings = get_embeddings(categories, model_name, gemini_api_key)

    if news_embeddings is None or category_embeddings is None:
        return None

    print("     Расчет сходства и присвоение категорий...")
    similarity_matrix = cosine_similarity(news_embeddings, category_embeddings)
    best_category_indices = np.argmax(similarity_matrix, axis=1)

    categorized_results = [
        {'news_text': news_text, 'initial_category': categories[best_category_indices[i]]}
        for i, news_text in enumerate(news_items)
    ]
    print("     Категоризация успешно завершена.")
    return categorized_results


# ---  ФУНКЦИЯ для сохранения результата ---
def save_results_to_json(data: List[Dict[str, str]], date_str: str, config: dict) -> bool:
    """Сохраняет категоризированные новости в JSON-файл."""
    try:
        output_dir = Path(config['output_directory'])
        filename_template = config['output_filename_template']
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = filename_template.format(date_str=date_str)
        output_filepath = output_dir / filename

        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"     Результат сохранен в файл: {output_filepath}")
        return True
    except (KeyError, IOError) as e:
        print(f"     [ERROR] Ошибка при сохранении JSON-файла: {e}")
        return False


# --- Главная функция для вызова извне ---
def run_topic_categorizer(target_date: str) -> bool:
    """
    Основная функция-оркестратор.
    Принимает дату, выполняет все шаги
    и возвращает True в случае успеха.
    """
    print("  -> Запуск topic_categorizer.py...")
    load_dotenv(ENV_FILE)

    categorizer_config = load_config(CATEGORIZER_CONFIG_FILE)
    summarizer_config = load_config(SUMMARIZER_CONFIG_FILE)
    if not categorizer_config or not summarizer_config: return False

    input_file = get_input_filepath(target_date, summarizer_config)
    if not input_file: return False

    news_list = parse_master_summary(input_file)
    if not news_list:
        print("     Нет новостей для категоризации. Пропускаем.")
        return True

    categorized_news = categorize_news(news_list, categorizer_config)
    if categorized_news is None: return False

    return save_results_to_json(categorized_news, target_date, categorizer_config)


if __name__ == '__main__':
    # Пример для ручного запуска и теста
    from datetime import date, timedelta

    test_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"--- Тестовый запуск topic_categorizer для даты: {test_date} ---")
    if run_topic_categorizer(target_date=test_date):
        print("--- Модуль Topic Categorizer успешно завершил работу ---")
    else:
        print("--- Работа модуля Topic Categorizer завершилась с ошибкой ---")