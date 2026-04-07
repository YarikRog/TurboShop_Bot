import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
import keyboards as kb
import users
import handlers_order as order
import handlers_catalog as catalog

# ================= CONFIG & LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("TurboBot.Main")

TOKEN = os.getenv("BOT_TOKEN")
MANAGERS = os.getenv("MANAGERS", "").split(',')
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

if not TOKEN:
    raise ValueError("CRITICAL: BOT_TOKEN is missing!")

# ================= BOT INITIALIZATION =================
bot = Bot(token=TOKEN, parse_mode="HTML")
storage = RedisStorage2(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=5)
dp = Dispatcher(bot=bot, storage=storage)

# ================= ENTERPRISE CACHE SERVICE =================
class ProductCache:
    def __init__(self):
        self._products = []
        self._map = {}
        self._lock = asyncio.Lock() # Захист від одночасного доступу

    async def update(self, data):
        async with self._lock:
            self._products = list(data)
            self._map = {
                str(item.get('Артикул', '')).strip().lower(): item
                for item in data if item.get('Артикул')
            }
            logger.info(f"🚀 Cache globally updated: {len(self._products)} items")

    def get_all(self):
        return self._products

    def get_by_id(self, article):
        if not article: return None
        return self._map.get(str(article).strip().lower())

# Глобальний екземпляр кешу
product_cache = ProductCache()

async def cache_refresher():
    """Фоновий таск, який ніколи не вмирає"""
    while True:
        try:
            # db.get_all_items тепер асинхронний (див. файл database.py)
            data = await db.get_all_items()
            if data:
                await product_cache.update(data)
            else:
                logger.warning("Empty data from DB, keeping old cache.")
        except Exception as e:
            logger.error(f"Cache loop error: {e}", exc_info=True)
        
        await asyncio.sleep(60) # Оновлення щохвилини

# ================= HANDLERS (CLEAN & SAFE) =================

@dp.message_handler(commands=['start'], state="*")
async def start_h(m: types.Message, state: FSMContext):
    await state.finish()
    await users.register_user(m.from_user.id, m.from_user.username, "Direct")
    await m.answer("Вітаємо у TurboShop 👟", reply_markup=kb.main_menu())

@dp.message_handler(lambda m: m.text in ["🏠 Головне меню", "⬅️ Назад"], state="*")
async def home_h(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Головне меню:", reply_markup=kb.main_menu())

@dp.message_handler(lambda m: m.text == "🔥 Наші новинки", state="*")
async def novinki_h(m: types.Message, state: FSMContext):
    await catalog.show_novinki(m, state, product_cache.get_all(), bot)

@dp.message_handler(lambda m: m.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def brands_h(m: types.Message, state: FSMContext):
    category = m.text.replace("👟", "").replace("👠", "").strip()
    await state.update_data(category=category)
    await catalog.show_brands(m, state, product_cache.get_all())

@dp.message_handler(lambda m: m.text.startswith("🔹 "))
async def size_h(m: types.Message, state: FSMContext):
    brand = m.text.replace("🔹 ", "").strip()
    await state.update_data(brand=brand)
    await catalog.choose_size(m, state, product_cache.get_all())

@dp.callback_query_handler(lambda c: c.data.startswith('size_'), state="*")
async def size_select_h(c: types.CallbackQuery, state: FSMContext):
    chosen_size = c.data.replace("size_", "").strip()
    data = await state.get_data()
    
    user_cat = str(data.get('category', '')).strip()
    user_brand = str(data.get('brand', '')).strip()
    
    # Фільтрація через Enterprise Cache
    products = [
        i for i in product_cache.get_all()
        if str(i.get('Категорія', '')).strip() == user_cat and
        str(i.get('Бренд', '')).strip() == user_brand and
        chosen_size in [s.strip() for s in str(i.get('Розміри', '')).replace(';', ',').split(',') if s.strip()]
    ]

    if not products:
        return await c.answer("❌ На жаль, ця позиція вже не доступна.", show_alert=True)

    ids = [str(i.get('Артикул')) for i in products if i.get('Артикул')]
    await state.update_data(product_ids=ids, index=0, size=chosen_size)
    
    await catalog.show_product(bot, c.from_user.id, 0, state, all_products=product_cache.get_all())
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def pag_h(c: types.CallbackQuery, state: FSMContext):
    action, idx = c.data.split('_')
    new_idx = int(idx) + 1 if action == 'next' else int(idx) - 1
    await catalog.show_product(bot, c.from_user.id, new_idx, state, c.message.message_id, all_products=product_cache.get_all())
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def buy_h(c: types.CallbackQuery, state: FSMContext):
    # Тепер ми НЕ передаємо кеш, бо order.py сам його візьме або отримає артикул
    await order.process_buy(c, state, product_cache.get_all())

@dp.callback_query_handler(lambda c: c.data.startswith('descr_'), state="*")
async def descr_h(c: types.CallbackQuery):
    article = c.data.replace("descr_", "")
    product = product_cache.get_by_id(article)
    text = product.get('Опис') if product else "Опис тимчасово відсутній."
    await bot.answer_callback_query(c.id, text=str(text)[:200], show_alert=True)

# Обробиники замовлення (Order Flow)
@dp.message_handler(content_types=['contact'], state=order.OrderState.waiting_for_phone)
async def phone_h(m, state): await order.get_phone(m, state)

@dp.message_handler(state=order.OrderState.waiting_for_fio)
async def fio_h(m, state): await order.get_fio(m, state)

@dp.message_handler(state=order.OrderState.waiting_for_delivery)
async def deliv_h(m, state): await order.get_delivery(m, state, bot)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(cache_refresher())
    executor.start_polling(dp, skip_updates=True)
