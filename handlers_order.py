import os
import logging
import requests
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
GAS_URL = os.getenv("GAS_URL")

class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

async def process_buy(callback_query: types.CallbackQuery, state: FSMContext, user_products):
    index = int(callback_query.data.split('_')[1])
    user_id = callback_query.from_user.id
    product = user_products[user_id]['products'][index]
    
    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель')}", 
        article=product.get('Артикул'), 
        price=product.get('Ціна')
    )
    await OrderState.waiting_for_phone.set()
    await callback_query.message.answer("🚀 Поділіться номером телефону:", reply_markup=kb.get_contact_keyboard())

async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Тепер ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

async def get_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("📦 Місто та № відділення Нової Пошти:")

async def get_delivery(message: types.Message, state: FSMContext, bot):
    await state.update_data(delivery=message.text)
    user_data = await state.get_data()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "Приховано"
    
    try:
        requests.post(GAS_URL, json=user_data, timeout=5)
    except:
        pass
    
    # БЕЗПЕЧНЕ ФОРМАТУВАННЯ НОМЕРА
    raw_phone = str(user_data.get('phone', ''))
    clean_phone = "".join(filter(str.isdigit, raw_phone))
    if not clean_phone.startswith('38'):
        clean_phone = f"38{clean_phone}"
    phone_formatted = f"+{clean_phone}"

    admin_msg = (f"🛍 <b>НОВЕ ЗАМОВЛЕННЯ!</b>\n"
                 f"⠀👟 <b>{user_data.get('item')}</b>\n"
                 f"⠀🆔 Артикул: <code>{user_data.get('article')}</code>\n"
                 f"⠀👤 Клієнт: {user_data.get('fio')}\n"
                 f"⠀📱 Тел: <code>{phone_formatted}</code>\n"
                 f"⠀✈️ НП: {user_data.get('delivery')}\n"
                 f"⠀🔗 Юзернейм: {username}")

    admin_kb = types.InlineKeyboardMarkup()
    chat_url = f"https://t.me/{message.from_user.username}" if message.from_user.username else f"tg://user?id={user_id}"
    admin_kb.add(types.InlineKeyboardButton("💬 Відкрити чат з клієнтом", url=chat_url))

    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, admin_msg, parse_mode="HTML", reply_markup=admin_kb)
        except Exception as e:
            logging.error(f"Admin notify error: {e}")
        
    client_msg = (
        f"✅ <b>ВАШЕ ЗАМОВЛЕННЯ ПРИЙНЯТО!</b>\n\n"
        f"⠀👟 Товар: <b>{user_data['item']}</b>\n"
        f"⠀💰 Ціна: <b>{user_data['price']} грн</b>\n"
        f"⠀📱 Телефон: {phone_formatted}\n\n"
        f"🚀 Менеджер зв'яжеться з тобою найближчим часом!"
    )
    
    await message.answer(client_msg, parse_mode="HTML", reply_markup=kb.main_menu())
    await state.finish()
