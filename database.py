import requests
import logging
import os

GAS_URL = os.getenv("GAS_URL")

# 1. Отримання всієї бази з Google Sheets (GAS)
def get_all_items():
    try:
        # Зменшив таймаут, щоб бот не висів довго, якщо Google лежить
        response = requests.get(GAS_URL, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logging.error(f"Помилка бази даних: {e}")
        return None

# 2. Отримуємо список унікальних розмірів (БЕРЕМО З КЕШУ)
def get_available_sizes(category, brand_name):
    # Імпортуємо ALL_PRODUCTS прямо тут, щоб брати вже завантажені дані
    from main import ALL_PRODUCTS
    
    if not ALL_PRODUCTS:
        return []

    sizes = set()
    for item in ALL_PRODUCTS:
        if str(item.get('Категорія')).strip() == category and \
           str(item.get('Бренд')).strip() == brand_name:
            raw_sizes = str(item.get('Розміри')).replace(' ', '').split(',')
            for s in raw_sizes:
                if s: sizes.add(s)

    return sorted(list(sizes))

# 3. Фільтр товарів (БЕРЕМО З КЕШУ)
def get_items_by_filter(category, brand_name, size):
    from main import ALL_PRODUCTS
    
    if not ALL_PRODUCTS:
        return []

    filtered_products = []
    for item in ALL_PRODUCTS:
        item_category = str(item.get('Категорія')).strip()
        item_brand = str(item.get('Бренд')).strip()
        item_sizes = str(item.get('Розміри')).replace(' ', '').split(',')

        if item_category == category and item_brand == brand_name and size in item_sizes:
            filtered_products.append(item)

    return filtered_products

# 4. Отримання фото за артикулом (БЕРЕМО З КЕШУ)
def get_product_photos(article):
    from main import ALL_PRODUCTS
    
    if not ALL_PRODUCTS:
        return []

    for item in ALL_PRODUCTS:
        if str(item.get('Артикул')).strip() == str(article).strip():
            photos_string = str(item.get('Фото', ''))
            if not photos_string or photos_string == 'None':
                return []
            return [p.strip() for p in photos_string.split(',') if p.strip()]

    return []
