import os
import requests
import time
import sqlite3
from datetime import datetime, date
from dotenv import load_dotenv

from database_manager import get_db_connection

"""
Модуль для парсинга статей с образовательного портала Bybit.
Автоматически извлекает новые материалы, сверяется с базой данных для исключения дубликатов и сохраняет уникальные статьи.
"""

load_dotenv()
# --- Константы ---
BASE_URL = "https://api2.bybit.com/fht/kratu-api/community/usercontent/get-article-list"
FIXED_PARAMS = {"sceneType": "SCENE_LEARN", "pageSize": 10, "language": "en"}
REQUEST_DELAY_SECONDS = 1
REQUEST_TIMEOUT_SECONDS = 15


# --- Функции для работы с БД ---

def get_existing_article_ids() -> set:
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT bybit_article_id FROM source_articles")
        return {row['bybit_article_id'] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при получении существующих ID: {e}")
        return set()
    finally:
        if conn:
            conn.close()


def save_articles_to_db(articles: list) -> int:
    """
    Сохраняет список новых статей в базу данных,
    записывая текущую дату как дату парсинга.
    """
    if not articles:
        return 0

    # Получаем текущую дату ОДИН РАЗ для всех статей в этой пачке
    parsing_date = date.today().strftime('%Y-%m-%d')

    to_insert = [
        (
            item.get("id"),
            item.get("title"),
            item.get("category", {}).get("id"),
            parsing_date
        )
        for item in articles
    ]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT OR IGNORE INTO source_articles (bybit_article_id, title, bybit_category_id, publication_date) VALUES (?, ?, ?, ?)"
        cursor.executemany(sql, to_insert)
        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при сохранении статей: {e}")
        return 0
    finally:
        if conn:
            conn.close()


# --- Логика запросов с прокси ---
def get_proxy_list() -> list:
    proxy_str = os.getenv("PROXY_LIST")
    if not proxy_str:
        return []
    proxies = []
    for p in proxy_str.split(','):
        try:
            ip, port, user, password = p.strip().split(':')
            proxies.append(f"http://{user}:{password}@{ip}:{port}")
        except ValueError:
            print(f"     [CONFIG_WARNING] Неверный формат прокси в .env: {p}")
    return proxies


def make_request(session, url, params, proxy=None):
    try:
        proxies_dict = {"http": proxy, "https": proxy} if proxy else None
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS, proxies=proxies_dict)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"     [NETWORK_ERROR] {e.__class__.__name__} при запросе (прокси: {'Да' if proxy else 'Нет'}).")
        return None


# --- Основная функция парсера ---
def parse_bybit_articles() -> tuple[bool, str]:
    print("  -> Запуск bybit_parser.py...")
    session = requests.Session()
    proxies = get_proxy_list()
    existing_ids = get_existing_article_ids()
    print(f"     В базе данных найдено {len(existing_ids)} существующих ID статей.")
    new_articles_to_add = []
    page_num = 1
    while True:
        print(f"\n     Запрос страницы {page_num}...")
        params = FIXED_PARAMS.copy()
        params["pageNum"] = page_num
        data = make_request(session, BASE_URL, params)
        if data is None:
            print("     Прямой запрос не удался. Пробую через прокси...")
            if not proxies: return False, "Сетевая ошибка, и нет прокси для повторной попытки."
            for i, proxy in enumerate(proxies):
                print(f"       - Прокси {i + 1}/{len(proxies)}...")
                data = make_request(session, BASE_URL, params, proxy=proxy)
                if data is not None:
                    print("     Успешный запрос через прокси!")
                    break
            if data is None: return False, "Сетевая ошибка: не удалось подключиться к Bybit ни напрямую, ни через прокси."
        if data.get("ret_code") != 0: return False, f"Ошибка API Bybit: {data.get('ret_msg')}"
        articles_on_page = data.get("result", {}).get("data", [])
        if not articles_on_page:
            print("     [INFO] На странице нет статей, или достигнут конец списка. Завершение.")
            break
        print(f"     [INFO] Страница {page_num} успешно получена. Найдено {len(articles_on_page)} статей.")
        new_articles_on_this_page_count = 0
        for article in articles_on_page:
            article_id = article.get("id")
            if article_id not in existing_ids:
                new_articles_to_add.append(article)
                existing_ids.add(article_id)
                new_articles_on_this_page_count += 1
                print(f"       + Найдена новая статья (ID: {article_id}): {article.get('title')[:70]}...")
        if new_articles_on_this_page_count == 0:
            print("     [INFO] На этой странице все статьи уже известны. Завершение сбора.")
            break
        page_num += 1
        time.sleep(REQUEST_DELAY_SECONDS)
    if not new_articles_to_add:
        return True, "Новых статей для добавления не найдено."
    message = f"Всего найдено {len(new_articles_to_add)} новых статей. Сохранение в БД..."
    print(f"\n     {message}")
    added_count = save_articles_to_db(new_articles_to_add)
    final_message = f"Успешно добавлено {added_count} новых записей в таблицу source_articles."
    return True, final_message


if __name__ == '__main__':
    success, message = parse_bybit_articles()
    print("\n--- РЕЗУЛЬТАТ ТЕСТОВОГО ЗАПУСКА ---")
    print(f"Успех: {success}")
    print(f"Сообщение: {message}")
    print("---------------------------------")