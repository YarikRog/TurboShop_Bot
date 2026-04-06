#!/usr/bin/python3.10
# -*- coding: utf-8 -*-
import os, logging, asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import database as db
import keyboards as kb
import users  
import handlers_order as order  
import handlers_catalog as catalog

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot, storage=MemoryStorage())

ALL_PRODUCTS = []
user_products = {}

async def update_cache_task():
    global ALL_PRODUCTS
    while True:
        try:
            data = db.get_all_items()
            if data: ALL_PRODUCTS = data
        except: pass
        await asyncio.sleep(600)

# --- СТАРТ ТА МЕНЕДЖЕР ---
@dp.message_handler(commands=['start'], state="*")
async def send_welcome(m: types.Message, state: FSMContext):
    await state.finish()
    users.register_user(m.from_user.id, m.from_user.username, "Direct")
    await m.answer("Вітаємо у TurboShop! 👟", reply_markup=kb.main_menu())

@dp.message_handler(lambda m: m.text == "💬 Менеджер", state="*")
async def manager_h(m: types.Message):
    await m.answer("Питання? Пиши: @yarik721 👨‍💻")

@dp.message_handler(lambda m: m.text in ["🏠 Головне меню", "⬅️ Назад"], state="*")
async def home_h(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Головне меню:", reply_markup=kb.main_menu())

# --- КАТАЛОГ (ПІДКЛЮЧЕННЯ) ---
@dp.message_handler(lambda m: m.text == "🔥 Наші новинки", state="*")
async def novinki_h(m): await catalog.show_novinki(m, user_products, ALL_PRODUCTS, bot)

@dp.message_handler(lambda m: m.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def brands_h(m): await catalog.show_brands(m, user_products, ALL_PRODUCTS)

@dp.message_handler(lambda m: m.text.startswith("🔹 "))
async def size_h(m): await catalog.choose_size(m, user_products, ALL_PRODUCTS)

@dp.callback_query_handler(lambda c: c.data.startswith('size_'), state="*")
async def start_cat_h(c: types.CallbackQuery):
    size = c.data.replace("size_", "")
    u_id = c.from_user.id
    if u_id not in user_products: user_products[u_id] = {'last_album_ids': []}
    user_products[u_id]['size'] = size
    products = [i for i in ALL_PRODUCTS if i.get('Категорія') == user_products[u_id].get('category') 
                and i.get('Бренд') == user_products[u_id].get('brand') and size in str(i.get('Розміри'))]
    user_products[u_id]['products'] = products
    if not products:
        await bot.answer_callback_query(c.id, text="Немає в наявності.", show_alert=True)
        return
    await catalog.show_product(bot, u_id, 0, user_products, ALL_PRODUCTS)

# --- ПАГІНАЦІЯ ТА ЗАМОВЛЕННЯ ---
@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def pag_h(c: types.CallbackQuery):
    action, idx = c.data.split('_')
    new_idx = int(idx) + 1 if action == 'next' else int(idx) - 1
    await catalog.show_product(bot, c.from_user.id, new_idx, user_products, ALL_PRODUCTS, c.message.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def buy_h(c, state): await order.process_buy(c, state, user_products)

# (Додай сюди решту хендлерів для контактів, ПІБ та доставки, як у попередньому кроці)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(update_cache_task())
    executor.start_polling(dp, skip_updates=True)
