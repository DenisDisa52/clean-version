from pybit.unified_trading import HTTP

'''
Модуль для получения актуального списка спотовых токенов с Bybit.
'''

TOKEN_LIST_FILE = 'base_currencies.txt'


def update_token_list() -> bool:
    """
    Обращается к Bybit, получает список спотовых токенов
    и сохраняет их в файл base_currencies.txt.
    Возвращает True в случае успеха.
    """
    print("  -> Запуск tokens.py (обновление списка валют)...")
    try:
        session = HTTP()
        response = session.get_instruments_info(category="spot")

        if response.get("retCode") != 0:
            print(f"     [ERROR] API Bybit вернул ошибку: {response.get('retMsg')}")
            return False

        instruments = response.get("result", {}).get("list", [])

        usdt_pairs = [
            inst["symbol"].replace("USDT", "")
            for inst in instruments
            if inst.get("symbol", "").endswith("USDT")
        ]

        with open(TOKEN_LIST_FILE, "w", encoding='utf-8') as file:
            file.write("\n".join(usdt_pairs))

        print(f"     [SUCCESS] Список из {len(usdt_pairs)} токенов успешно сохранен в {TOKEN_LIST_FILE}.")
        return True

    except Exception as e:
        print(f"     [ERROR] Не удалось обновить список токенов: {e}")
        return False


if __name__ == '__main__':
    # Тестовый запуск
    if update_token_list():
        print("\n--- Модуль Tokens успешно завершил работу ---")
    else:
        print("\n--- Работа модуля Tokens завершилась с ошибкой ---")