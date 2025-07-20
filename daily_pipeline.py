import os
import asyncio
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# --- Импорты всех наших модулей в порядке их вызова ---
from tokens import update_token_list
from vpn_manager import connect_vpn, disconnect_vpn
from bybit_parser import parse_bybit_articles
from telegram_channel_scraper import main as run_telegram_scraper
from news_summarizer import run_news_summarizer
from topic_categorizer import run_topic_categorizer
from topic_rebalancer import run_topic_rebalancer
from title_formatter import run_title_formatter
from daily_planner import run_daily_planner
from image_prompt_generator import run_image_prompt_generator
from article_writter import run_article_writer
from picture_generator import run_picture_generator
from token_matcher import run_token_matcher
from doc_zipper import run_doc_zipper
from alerter import send_admin_alert
from telegram.ext import Application
from telegram_bot import send_digest_to_user

'''
Главный скрипт-оркестратор (дирижер) всего ежедневного цикла.
'''


async def deliver_zips(application: Application, zips_to_deliver: dict):
    tasks = [send_digest_to_user(application, user_id, zip_path) for user_id, zip_path in zips_to_deliver.items()]
    await asyncio.gather(*tasks)


def run_daily_tasks():
    print("=" * 50)
    print(f"🚀 ЗАПУСК ЕЖЕДНЕВНОГО ЦИКЛА: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    target_date_str = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"🎯 Целевая дата для обработки: {target_date_str}")

    # --- ЭТАП 0: ПОДГОТОВКА ---
    print("\n[0/5] 🔧 Подготовка окружения...")
    if not update_token_list():
        send_admin_alert("⚠️ *Сбой в tokens.py:*\nНе удалось обновить список токенов.")

    if not connect_vpn():
        send_admin_alert("🔥 *Критический сбой VPN:*\nНе удалось подключиться. Пайплайн ОСТАНОВЛЕН.")
        return

    # --- ЭТАП 1: СБОР И ОБРАБОТКА НОВОСТЕЙ ---
    print("\n[1/5] 📰 Сбор и обработка новостей...")
    try:
        success, message = parse_bybit_articles()
        if not success: send_admin_alert(f"⚠️ *Сбой в bybit_parser:*\n`{message}`")
    except Exception as e:
        send_admin_alert(f"🔥 *Критический сбой в bybit_parser:*\n`{e}`")

    try:
        asyncio.run(run_telegram_scraper())
    except Exception as e:
        send_admin_alert(f"🔥 *Критический сбой в telegram_scraper:*\n`{e}`\n_Пайплайн ОСТАНОВЛЕН._")
        disconnect_vpn()
        return

    if not run_news_summarizer(target_date=target_date_str): disconnect_vpn(); return
    if not run_topic_categorizer(target_date=target_date_str): disconnect_vpn(); return
    if not run_topic_rebalancer(target_date=target_date_str): disconnect_vpn(); return
    if not run_title_formatter(): disconnect_vpn(); return

    # --- ЭТАП 2: ПЛАНИРОВАНИЕ И ГЕНЕРАЦИЯ ---
    print("\n[2/5] 📅 Стратегия и планирование...")
    if not run_image_prompt_generator(): print("     [WARNING] Не удалось обновить стили изображений.")
    if not run_daily_planner(): disconnect_vpn(); return

    # --- ЭТАП 3: ФАБРИКА КОНТЕНТА ---
    print("\n[3/5] 🏭 Фабрика контента...")
    if not run_article_writer(): disconnect_vpn(); return
    if not run_picture_generator(): disconnect_vpn(); return
    if not run_token_matcher(): print("     [WARNING] Не удалось подобрать токены.")

    # --- ЭТАП 4: СБОРКА ---
    print("\n[4/5] 📦 Сборка...")
    zips_to_deliver = run_doc_zipper()

    # --- ЭТАП 5: ДОСТАВКА И ЗАВЕРШЕНИЕ ---
    print("\n[5/5] 🚚 Доставка и завершение...")
    if not zips_to_deliver:
        print("     [INFO] Нет готовых дайджестов для доставки.")
    else:
        print("     Инициализация Telegram-бота для отправки...")
        load_dotenv()
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            print("     [ERROR] TELEGRAM_BOT_TOKEN не найден.")
        else:
            application = Application.builder().token(bot_token).build()
            asyncio.run(deliver_zips(application, zips_to_deliver))

    disconnect_vpn()

    print("\n" + "=" * 50)
    print(f"🏁 ЕЖЕДНЕВНЫЙ ЦИКЛ УСПЕШНО ЗАВЕРШЕН: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)


if __name__ == '__main__':
    run_daily_tasks()