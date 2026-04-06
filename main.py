#!/usr/bin/python3.10
# -*- coding: utf-8 -*-

import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
import keyboards as kb
import users
import handlers_order as order
import handlers_catalog as catalog

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ================= ENV =================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

# Дані для підключення до Redis (змінні з Railway)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") # Твій пароль від Redis

# ================= BOT =================
bot = Bot(token=TOKEN)

# Налаштовуємо RedisStorage з паролем
storage = RedisStorage2(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=5,
    state_ttl=3600
)

dp = Dispatcher(bot=bot, storage=storage)

# ================= CACHE SERVICE =================
class ProductCache:
    def __init__(self):
        self.products = []
        self.map = {}

    def update(self, data):
        self.products = list(data)
        self.map = {
            str(item.get('Артикул')): item
            for item in data if item.get('Артикул')
        }

    def get_all(self):
        return self.products

    def get_by_id(self, article):
        return self.map.get(str(article))

cache = ProductCache()

async def update_cache_task():
    while True:
        try:
            # Викликаємо асинхронно через await
            data = await db.get_all_items() 
            if data:
                cache.update(data)
                logger.info(f"Cache updated: {len(data)} products")
            else:
                logger.warning("Empty DB response")
        except Exception:
            logger.exception("CACHE UPDATE ERROR")

        await asyncio.sleep(60)

# ================= SAFE CALL =================
async def safe_call(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except Exception:
        logger.exception("HANDLER ERROR")
        return None

# ================= MANAGER =================
@dp.message_handler(lambda m: m.text == "💬 Менеджер", state="*")
async def manager_h(m: types.Message):
    manager_ids = os.getenv("MANAGERS", "").split(',')
    text = (
        "<b>Маєш запитання чи потрібна допомога?</b> 🤔\n\n"
        "Наші менеджери на зв'язку! Обери 👇"
    )
    markup = InlineKeyboardMarkup(row_width=1)

    tasks = [
        bot.get_chat(m_id.strip())
        for m_id in manager_ids if m_id.strip().isdigit()
    ]

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, types.Chat) and res.username:
                markup.add(
                    InlineKeyboardButton(
                        text=f"👨‍💻 {res.first_name}",
                        url=f"https://t.me/{res.username}"
                    )
                )

    if not markup.inline_keyboard:
        markup.add(InlineKeyboardButton(text="👨‍💻 Менеджер", url="https://t.me/yarik721"))

    await m.answer(text, reply_markup=markup, parse_mode="HTML")

# ================= DESCRIPTION =================
@dp.callback_query_handler(lambda c: c.data.startswith('descr_'), state="*")
async def descr_h(c: types.CallbackQuery):
    product = cache.get_by_id(c.data.replace("descr_", ""))
    text = product.get('Опис') or "Опис скоро з'явиться 😉" if product else "Товар не знайдено"
    await bot.answer_callback_query(c.id, text=text, show_alert=True)

# ================= START =================
@dp.message_handler(commands=['start'], state="*")
async def start_h(m: types.Message, state: FSMContext):
    await state.finish()
    # Асинхронна реєстрація
    await users.register_user(m.from_user.id, m.from_user.username, "Direct")
    await m.answer("Вітаємо у TurboShop 👟", reply_markup=kb.main_menu())

# ================= MENU =================
@dp.message_handler(lambda m: m.text in ["🏠 Головне меню", "⬅️ Назад"], state="*")
async def home_h(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Головне меню:", reply_markup=kb.main_menu())

# ================= CATALOG =================
@dp.message_handler(lambda m: m.text == "🔥 Наші новинки", state="*")
async def novinki_h(m: types.Message, state: FSMContext):
    products = cache.get_all()
    if not products:
        return await m.answer("Каталог оновлюється 🙏")
    await safe_call(catalog.show_novinki, m, state, products, bot)

@dp.message_handler(lambda m: m.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def brands_h(m: types.Message, state: FSMContext):
    await state.update_data(category=m.text)
    await safe_call(catalog.show_brands, m, state, cache.get_all())

@dp.message_handler(lambda m: m.text.startswith("🔹 "))
async def size_h(m: types.Message, state: FSMContext):
    await state.update_data(brand=m.text.replace("🔹 ", ""))
    await safe_call(catalog.choose_size, m, state, cache.get_all())

@dp.callback_query_handler(lambda c: c.data.startswith('size_'), state="*")
async def size_select_h(c: types.CallbackQuery, state: FSMContext):
    size = c.data.replace("size_", "")
    data = await state.get_data()
    products = [
        i for i in cache.get_all()
        if i.get('Категорія') == data.get('category')
        and i.get('Бренд') == data.get('brand')
        and size in str(i.get('Розміри', ''))
    ]
    if not products:
        return await c.answer("Немає в наявності 😔", show_alert=True)

    ids = [str(i.get('Артикул')) for i in products if i.get('Артикул')]
    await state.update_data(product_ids=ids, index=0, size=size)
    await safe_call(catalog.show_product, bot, c.from_user.id, 0, state)

@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def pag_h(c: types.CallbackQuery, state: FSMContext):
    action, idx = c.data.split('_')
    new_idx = int(idx) + 1 if action == 'next' else int(idx) - 1
    await safe_call(catalog.show_product, bot, c.from_user.id, new_idx, state, c.message.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('more_photos_'), state="*")
async def photos_h(c: types.CallbackQuery, state: FSMContext):
    await safe_call(catalog.show_more_photos, c, state, cache.get_all(), bot)

# ================= ORDER =================
@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def buy_h(c: types.CallbackQuery, state: FSMContext):
    await safe_call(order.process_buy, c, state, cache.get_all())

@dp.message_handler(content_types=['contact'], state=order.OrderState.waiting_for_phone)
async def phone_h(m, state): await safe_call(order.get_phone, m, state)

@dp.message_handler(state=order.OrderState.waiting_for_fio)
async def fio_h(m, state): await safe_call(order.get_fio, m, state)

@dp.message_handler(state=order.OrderState.waiting_for_delivery)
async def deliv_h(m, state): await safe_call(order.get_delivery, m, state, bot)

# ================= RUN =================
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(update_cache_task())
    executor.start_polling(dp, skip_updates=True)
