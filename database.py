import requests
import logging
from config import GAS_URL

# 1. Отримання всієї бази з Google Sheets (GAS)
def get_all_items():
    try:
        response = requests.get(GAS_URL, timeout=30)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logging.error(f"Помилка бази даних: {e}")
        return None

# 2. Отримуємо список унікальних розмірів для бренду (для вибору в кнопках)
def get_available_sizes(category, brand_name):
    all_data = get_all_items()
    if not all_data:
        return []

    sizes = set()
    for item in all_data:
        if str(item.get('Категорія')).strip() == category and \
           str(item.get('Бренд')).strip() == brand_name:
            # Розбиваємо рядок "41, 42, 43" на окремі елементи, видаляючи пробіли
            raw_sizes = str(item.get('Розміри')).replace(' ', '').split(',')
            for s in raw_sizes:
                if s: sizes.add(s)

    return sorted(list(sizes))

# 3. Отримуємо конкретні товари за категорією, брендом та обраним розміром
def get_items_by_filter(category, brand_name, size):
    all_data = get_all_items()
    if not all_data:
        return []

    filtered_products = []
    for item in all_data:
        item_category = str(item.get('Категорія')).strip()
        item_brand = str(item.get('Бренд')).strip()
        # Створюємо список розмірів з рядка в таблиці
        item_sizes = str(item.get('Розміри')).replace(' ', '').split(',')

        if item_category == category and item_brand == brand_name and size in item_sizes:
            filtered_products.append(item)

    return filtered_products

# 4. Отримуємо всі ID фото для альбому (MediaGroup) за артикулом
def get_product_photos(article):
    all_data = get_all_items()
    if not all_data:
        return []

    for item in all_data:
        # Порівнюємо артикули, прибираючи зайві пробіли (щоб не було помилок)
        if str(item.get('Артикул')).strip() == str(article).strip():
            photos_string = str(item.get('Фото'))
            # Розбиваємо рядок ID по комі і чистимо від пробілів
            photos_list = [p.strip() for p in photos_string.split(',') if p.strip()]
            return photos_list

    return []