import os
import logging
import aiohttp
import asyncio

GAS_URL = os.getenv("GAS_URL")
logger = logging.getLogger("TurboBot.Database")

async def get_all_items():
    """Асинхронне отримання бази товарів з Google Apps Script."""
    if not GAS_URL:
        logger.error("❌ GAS_URL is not defined in environment variables!")
        return None
        
    # Використовуємо ClientTimeout для захисту від зависань Google
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(GAS_URL) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                logger.error(f"⚠️ GAS API error: Status {response.status}")
                return None
    except asyncio.TimeoutError:
        logger.error("❌ GAS API Timeout after 15s")
    except Exception as e:
        logger.error(f"❌ Critical DB Error: {e}", exc_info=True)
    return None

def get_available_sizes(all_products, category, brand_name):
    """Швидка фільтрація розмірів без зайвих алокацій."""
    if not all_products: return []
    
    sizes = set()
    category = str(category).strip()
    brand_name = str(brand_name).strip()

    for item in all_products:
        if str(item.get('Категорія')).strip() == category and \
           str(item.get('Бренд')).strip() == brand_name:
            
            raw_val = str(item.get('Розміри', '')).replace(' ', '')
            if raw_val and raw_val.lower() != 'none':
                item_sizes = [s.strip() for s in raw_val.replace(';', ',').split(',') if s.strip()]
                sizes.update(item_sizes)

    try:
        # Розумне сортування: числа до чисел, рядки до рядків
        return sorted(list(sizes), key=lambda x: float(x.replace(',', '.')) if x.replace(',','',1).replace('.','',1).isdigit() else x)
    except:
        return sorted(list(sizes))
