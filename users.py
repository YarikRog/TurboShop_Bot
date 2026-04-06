import os
import logging
import asyncio
import aiohttp # Додай це в requirements.txt, якщо ще немає

# Налаштування логування (вже є в main, але хай буде і тут)
logger = logging.getLogger(__name__)

# URL-адреса Google Script з Railway
GAS_URL = os.getenv("GAS_URL")

async def register_user(user_id, username, source="Direct"):
    """
    Асинхронна реєстрація нового клієнта. 
    Бот не буде чекати відповіді від Google, а піде працювати далі.
    """
    if not GAS_URL:
        logger.error("❌ GAS_URL не знайдено в змінних оточення!")
        return False

    payload = {
        "action": "register_user",
        "user_id": user_id,
        "username": f"@{username}" if username else "Hidden",
        "source": source
    }

    # Використовуємо асинхронну сесію, щоб не блокувати бота
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GAS_URL, json=payload, timeout=15) as response:
                if response.status == 200:
                    logger.info(f"✅ Юзер {user_id} зареєстрований. Джерело: {source}")
                    return True
                else:
                    logger.warning(f"⚠️ GAS помилка: {response.status}")
                    return False
    except asyncio.TimeoutError:
        logger.error("⏳ Google Script Timeout (15s) - реєстрація затрималась.")
        return False
    except Exception as e:
        logger.error(f"❌ Помилка реєстрації юзера: {e}")
        return False

async def get_admin_stats():
    """
    Асинхронне отримання цифр аналітики.
    """
    if not GAS_URL:
        return None

    payload = {"action": "get_stats"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GAS_URL, json=payload, timeout=15) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"⚠️ Помилка статистики GAS: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"❌ Помилка запиту статистики: {e}")
        return None
