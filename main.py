#!/usr/bin/python3.10
# -*- coding: utf-8 -*-
import os, logging, asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
            if data: 
                ALL_PRODUCTS = data
        except: pass
        await asyncio.sleep(60)

# --- НОВИЙ ОБРОБНИК ОПИСУ ---
@dp.callback_query_handler(lambda c: c.data.startswith('descr_'), state="*")
async def descr_h(c: types.CallbackQuery):
    article = c.data.replace("descr_", "")
    product = next((i for i in ALL_PRODUCTS if str(i.get('Артикул')) == article), None)
    if product:
        text = product.get('Опис')
        if not text or str(text).strip() == "None": text = "Опис скоро з'явиться... 😉"
        await bot.answer_callback_query(c.id, text=text, show_alert=True)
    else:
        await bot.answer_callback_query(c.id, text="Інформація не знайдена.")

# --- СЛУЖБОВІ ТА СТАРТ ---
@dp.message_handler(commands=['start'], state="*")
async def send_welcome(m: types.Message, state: FSMContext):
    await state.finish()
    users.register_user(m.from_user.id, m.from_user.username, "Direct")
    await m.answer("Вітаємо у TurboShop! 👟", reply_markup=kb.main_menu())

# --- ОНОВЛЕНИЙ МЕНЕДЖЕР (ТЕПЕР ЧЕРЕЗ MANAGERS) ---
@dp.message_handler(lambda m: m.text == "💬 Менеджер", state="*")
async def manager_h(m: types.Message):
    # Тепер беремо ID саме зі змінної MANAGERS
    manager_ids = os.getenv("MANAGERS", "").split(',')
    
    text = (
        "<b>Маєш запитання чи потрібна допомога з підбором?</b> 🤔\n\n"
        "Наші менеджери вже на низькому старті, щоб знайти твою ідеальну пару! "
        "Тисни на кнопку нижче, щоб розпочати чат: 👇"
    )
    
    markup = InlineKeyboardMarkup(row_width=1)
    
    for m_id in manager_ids:
        m_id = m_id.strip()
        if not m_id: continue
        
        try:
            chat = await bot.get_chat(m_id)
            name = chat.first_name if chat.first_name else "Менеджер"
            user_nick = chat.username
            
            if user_nick:
                markup.add(InlineKeyboardButton(
                    text=f"👨‍💻 Написати {name}", 
                    url=f"https://t.me/{user_nick}")
                )
        except Exception as e:
            continue
            
    await m.answer(text, reply_markup=markup, parse_mode="HTML")

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
    cat = user_products[u_id].get('category')
    brd = user_products[u_id].get('brand')
    products = [i for i in ALL_PRODUCTS if i.get('Категорія') == cat and i.get('Бренд') == brd and size in str(i.get('Розміри'))]
    user_products[u_id]['products'] = products
    if not products:
        await bot.answer_callback_query(c.id, text="Немає в наявності.", show_alert=True)
        return
    await catalog.show_product(bot, u_id, 0, user_products, ALL_PRODUCTS)

@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def pag_h(c: types.CallbackQuery):
    action, idx = c.data.split('_')
    new_idx = int(idx) + 1 if action == 'next' else int(idx) - 1
    await catalog.show_product(bot, c.from_user.id, new_idx, user_products, ALL_PRODUCTS, c.message.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('more_photos_'), state="*")
async def photos_h(c: types.CallbackQuery):
    await catalog.show_more_photos(c, user_products, ALL_PRODUCTS, bot)

# --- ЗАМОВЛЕННЯ ---
@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def buy_h(c, state): 
    await order.process_buy(c, state, user_products, ALL_PRODUCTS)

@dp.message_handler(content_types=['contact'], state=order.OrderState.waiting_for_phone)
async def phone_h(m, state): 
    await order.get_phone(m, state)

@dp.message_handler(state=order.OrderState.waiting_for_fio)
async def fio_h(m, state): 
    await order.get_fio(m, state)

@dp.message_handler(state=order.OrderState.waiting_for_delivery)
async def deliv_h(m, state): 
    await order.get_delivery(m, state, bot)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(update_cache_task())
    executor.start_polling(dp, skip_updates=True)
