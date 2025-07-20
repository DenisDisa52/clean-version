import os
import json
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

'''
Скрипт принимает на вход дату, находит соответствующую сводку новостей,
с помощью AI объединяет дублирующиеся события и формирует итоговый,
чистый список уникальных новостей за день, сохраняя его в новый файл.
'''

# --- Константы ---
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

def get_input_filepath(date_str: str, scraper_config: dict) -> Path | None:
    """Формирует путь к входному файлу с дневной сводкой."""
    try:
        input_dir = Path(scraper_config['output_directory'])
        filename_template = scraper_config['output_filename_template']
        filename = filename_template.format(date_str=date_str)
        filepath = input_dir / filename
        if not filepath.exists():
            print(f"     [ERROR] Входной файл сводки не найден: {filepath}")
            return None
        return filepath
    except KeyError as e:
        print(f"     [ERROR] В файле scraper_config.json отсутствует ключ: {e}")
        return None

def parse_daily_summary(filepath: Path) -> str:
    """Извлекает и объединяет тексты новостей из файла сводки."""
    print(f"     Парсинг входного файла: {filepath.name}")
    full_text = filepath.read_text(encoding='utf-8')
    news_blocks = full_text.split('========================================')
    all_news_text = []
    for block in news_blocks:
        if '---' in block:
            content = block.split('---', 1)[1].strip()
            if content:
                all_news_text.append(content)
    if not all_news_text:
        print("     [WARNING] В файле не найдено новостных блоков для обработки.")
        return ""
    print(f"     Найдено и объединено {len(all_news_text)} блока(ов) новостей.")
    return "\n\n---\n\n".join(all_news_text)

def create_master_summary(news_text: str, config: dict) -> str | None:
    """Отправляет текст в Gemini для создания единой сводки."""
    print("     Генерация мастер-сводки с помощью Gemini...")
    try:
        prompt_path = Path(config['prompt_path'])
        model_name = config['gemini_model']
        api_key_name = config['gemini_api_key_name']
        prompt_template = prompt_path.read_text(encoding='utf-8')
        gemini_api_key = os.getenv(api_key_name)

        if not gemini_api_key:
            print(f"     [ERROR] API-ключ '{api_key_name}' не найден в .env файле.")
            return None

        final_prompt = prompt_template.format(news_text=news_text)
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(final_prompt)
        print("     Мастер-сводка успешно сгенерирована.")
        return response.text
    except KeyError as e:
        print(f"     [ERROR] В summarizer_config.json отсутствует ключ: {e}")
        return None
    except FileNotFoundError:
        print(f"     [ERROR] Файл с промптом {prompt_path} не найден.")
        return None
    except Exception as e:
        print(f"     [ERROR] при обращении к API Gemini: {e}")
        return None

def save_master_summary(summary_text: str, date_str: str, config: dict):
    """Сохраняет итоговую мастер-сводку в файл."""
    try:
        output_dir = Path(config['output_directory'])
        filename_template = config['output_filename_template']
        output_dir.mkdir(exist_ok=True)
        output_filename = filename_template.format(date_str=date_str)
        output_filepath = output_dir / output_filename
        output_filepath.write_text(summary_text, encoding='utf-8')
        print(f"     Результат сохранен в файл: {output_filepath}")
        return True
    except (KeyError, IOError) as e:
        print(f"     [ERROR] Ошибка при сохранении файла: {e}")
        return False

# --- Главная функция для вызова извне ---
def run_news_summarizer(target_date: str) -> bool:
    """
    Основная функция-оркестратор. Принимает дату, выполняет все шаги
    и возвращает True в случае успеха.
    """
    print("  -> Запуск news_summarizer.py...")
    load_dotenv(ENV_FILE)

    summarizer_config = load_config(SUMMARIZER_CONFIG_FILE)
    if not summarizer_config: return False

    scraper_config_path = summarizer_config.get('input_config_file')
    if not scraper_config_path:
        print(f"     [ERROR] В {SUMMARIZER_CONFIG_FILE} не указан 'input_config_file'.")
        return False

    scraper_config = load_config(scraper_config_path)
    if not scraper_config: return False

    input_file = get_input_filepath(target_date, scraper_config)
    if not input_file: return False

    combined_news = parse_daily_summary(input_file)
    if not combined_news:
        print("     Нет новостей для обработки. Пропускаем.")
        return True # Считаем успехом, т.к. ошибки не было

    master_summary = create_master_summary(combined_news, summarizer_config)
    if not master_summary: return False

    return save_master_summary(master_summary, target_date, summarizer_config)


if __name__ == '__main__':
    from datetime import date, timedelta
    test_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"--- Тестовый запуск news_summarizer для даты: {test_date} ---")
    run_news_summarizer(target_date=test_date)