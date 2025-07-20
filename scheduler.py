import time
from apscheduler.schedulers.blocking import BlockingScheduler

# Импортируем ОБЕ наши главные функции
from daily_pipeline import run_daily_tasks
from strategic_planner import run_strategic_planner

'''
Этот скрипт - "сердце" проекта, работающее 24/7.
Он запускает ежедневные и еженедельные задачи по расписанию.
'''

def main_scheduler():
    scheduler = BlockingScheduler(timezone="Europe/Moscow")

    # --- РАСПИСАНИЕ №1: Ежедневный запуск основного конвейера ---
    scheduler.add_job(
        run_daily_tasks,
        'cron',
        hour=9,
        minute=30,
        id='daily_tasks_job',
        replace_existing=True
    )

    # --- РАСПИСАНИЕ №2: Еженедельный запуск стратегического планировщика ---
    scheduler.add_job(
        run_strategic_planner,
        'cron',
        day_of_week='mon',
        hour=1,
        minute=0,
        id='weekly_planning_job',
        replace_existing=True
    )

    print("="*50)
    print("✅ Планировщик запущен в боевом режиме.")
    print("   - Ежедневный запуск запланирован на 07:00 (Europe/Moscow).")
    print("   - Еженедельное планирование запланировано на 01:00 каждого понедельника.")
    print("   - Ожидание запланированного времени...")
    print("="*50)
    print("Чтобы остановить планировщик, нажмите Ctrl+C")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nПланировщик остановлен.")
        scheduler.shutdown()

if __name__ == '__main__':
    main_scheduler()