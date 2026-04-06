import os
import logging
import aiohttp
import asyncio

# Отримуємо URL з налаштувань Railway
GAS_URL = os.getenv("GAS_URL")
logger = logging.getLogger(__name__)

# 1. АСИНХРОННЕ отримання всієї бази (GAS)
async def get_all_items():
    if not GAS_URL:
        logger.error("❌ GAS_URL не налаштовано!")
        return None
        
    try:
        # Використовуємо асинхронну сесію
        async with aiohttp.ClientSession() as session:
            async with session.get(GAS_URL, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"⚠️ Помилка GAS API: Статус {response.status}")
                    return None
    except Exception as e:
        logger.error(f"❌ Критична помилка отримання бази: {e}")
        return None

# 2. Отримуємо список унікальних розмірів (Оптимізовано)
def get_available_sizes(all_products, category, brand_name):
    if not all_products:
        return []

    sizes = set()
    category = str(category).strip()
    brand_name = str(brand_name).strip()

    for item in all_products:
        if str(item.get('Категорія')).strip() == category and \
           str(item.get('Бренд')).strip() == brand_name:
            
            # Чистимо рядок від зайвого
            raw_val = str(item.get('Розміри', '')).replace(' ', '')
            if raw_val and raw_val != 'None':
                item_sizes = [s.strip() for s in raw_val.split(',') if s.strip()]
                sizes.update(item_sizes)

    # Сортування: спочатку цифри (якщо є), потім текст
    try:
        return sorted(list(sizes), key=lambda x: float(x.replace(',', '.')) if x.replace('.','',1).replace(',','',1).isdigit() else x)
    except:
        return sorted(list(sizes))

# 3. Отримання фото за артикулом (Тепер ми просто дістаємо їх з об'єкта)
def get_product_photos(all_products, article):
    """
    Ця функція тепер майже не потрібна, бо ми маємо PRODUCTS_MAP у main.py,
    але залишимо її для сумісності з іншими модулями.
    """
    if not all_products:
        return []
    
    target_article = str(article).strip()
    for item in all_products:
        if str(item.get('Артикул')).strip() == target_article:
            photos_string = str(item.get('Фото', ''))
            if not photos_string or photos_string == 'None':
                return []
            return [p.strip() for p in photos_string.split(',') if p.strip() and p != 'None']
    return []
