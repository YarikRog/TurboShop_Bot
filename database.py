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

# 2. Отримуємо список унікальних розмірів
def get_available_sizes(all_products, category, brand_name):
    if not all_products:
        return []

    sizes = set()
    for item in all_products:
        if str(item.get('Категорія')).strip() == category and \
           str(item.get('Бренд')).strip() == brand_name:
            # Очищаємо пробіли та розбиваємо рядок розмірів
            raw_sizes = str(item.get('Розміри')).replace(' ', '').split(',')
            for s in raw_sizes:
                if s and s != 'None':
                    sizes.add(s.strip())

    return sorted(list(sizes), key=lambda x: float(x) if x.replace('.','',1).isdigit() else x)

# 3. Фільтр товарів
def get_items_by_filter(all_products, category, brand_name, size):
    if not all_products:
        return []

    filtered_products = []
    for item in all_products:
        item_category = str(item.get('Категорія')).strip()
        item_brand = str(item.get('Бренд')).strip()
        item_sizes = str(item.get('Розміри')).replace(' ', '').split(',')

        if item_category == category and item_brand == brand_name and size in item_sizes:
            filtered_products.append(item)

    return filtered_products

# 4. Отримання фото за артикулом
def get_product_photos(all_products, article):
    if not all_products:
        return []
    for item in all_products:
        if str(item.get('Артикул')).strip() == str(article).strip():
            photos_string = str(item.get('Фото', ''))
            if not photos_string or photos_string == 'None':
                return []
            return [p.strip() for p in photos_string.split(',') if p.strip() and p != 'None']
    return []
