import os
import requests
import logging

# Твоя URL-адреса Google Script з Railway
GAS_URL = os.getenv("GAS_URL")

def register_user(user_id, username, source="Direct"):
    """
    Реєстрація нового клієнта в листі USERS через Google Apps Script.
    """
    if not GAS_URL:
        logging.error("❌ GAS_URL не знайдено в змінних оточення!")
        return False

    payload = {
        "action": "register_user",
        "user_id": user_id,
        "username": f"@{username}" if username else "Hidden",
        "source": source
    }
    try:
        # Змінено на 15 секунд за твоїм запитом
        response = requests.post(GAS_URL, json=payload, timeout=15)
        if response.status_code == 200:
            print(f"✅ Юзер {user_id} зареєстрований. Джерело: {source}")
            return True
        else:
            print(f"⚠️ GAS помилка: {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        logging.error("⏳ Помилка: Google Script не відповів вчасно (Timeout).")
        return False
    except Exception as e:
        logging.error(f"❌ Помилка реєстрації юзера: {e}")
        return False

def get_admin_stats():
    """
    Отримання цифр аналітики для команди /stats.
    """
    if not GAS_URL:
        return None

    payload = {"action": "get_stats"}
    try:
        # Змінено на 15 секунд за твоїм запитом
        response = requests.post(GAS_URL, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Помилка статистики: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"❌ Помилка запиту статистики: {e}")
        return None
