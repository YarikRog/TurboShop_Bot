import requests
import logging
from config import GAS_URL

def register_user(user_id, username, source="Direct"):
    """
    Реєстрація нового клієнта в листі USERS через Google Apps Script.
    """
    payload = {
        "action": "register_user",
        "user_id": user_id,
        "username": f"@{username}" if username else "Hidden",
        "source": source
    }
    try:
        response = requests.post(GAS_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"✅ Юзер {user_id} зареєстрований. Джерело: {source}")
            return True
        else:
            print(f"⚠️ GAS помилка: {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"❌ Помилка реєстрації юзера: {e}")
        return False

def get_admin_stats():
    """
    Отримання цифр аналітики для команди /stats.
    """
    payload = {"action": "get_stats"}
    try:
        response = requests.post(GAS_URL, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json()  # Очікуємо {"total": X, "insta": Y, "qr": Z, "tg": W}
        else:
            print(f"⚠️ Помилка статистики: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"❌ Помилка запиту статистики: {e}")
        return None