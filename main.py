import os, logging, asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.redis import RedisStorage2

import database as db
import keyboards as kb
import handlers_order as order
import handlers_catalog as catalog

# ================= SETUP =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TurboBot.Main")

TOKEN = os.getenv("BOT_TOKEN")

# Налаштування Redis з обмеженням пулу з'єднань
# Railway Redis зазвичай потребує пароль та специфічний хост
storage = RedisStorage2(
    host=os.getenv("REDIS_HOST", "ballast.proxy.rlwy.net"),
    port=int(os.getenv("REDIS_PORT", 28367)),
    password=os.getenv("REDIS_PASSWORD"),
    db=5,
    pool_size=5,             # ОБМЕЖУЄМО ПУЛ: бот триматиме максимум 5 конектів
    wait_for_connection=True # Чекати на вільний конект, а не кидати помилку
)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)

class ProductCache:
    def __init__(self):
        self._products = []
        self._lock = asyncio.Lock()

    async def update(self):
        data = await db.get_all_items()
        if data:
            async with self._lock:
                self._products = data
            logger.info(f"Cache updated: {len(data)} items")

    def get_all(self):
        return self._products

    def get_by_id(self, article):
        return next((i for i in self._products if str(i.get('Артикул', '')).strip() == str(article).strip()), None)

cache = ProductCache()

# ================= BACKGROUND TASKS =================
async def on_startup(_):
    await cache.update()
    asyncio.create_task(cache_refresher())

async def cache_refresher():
    while True:
        await asyncio.sleep(60)
        await cache.update()

# ================= HANDLERS =================
@dp.message_handler(commands=['start'], state="*")
async def start_cmd(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Вітаємо у TurboShop! 👟", reply_markup=kb.main_menu())

@dp.message_handler(lambda m: m.text in ["🏠 Головне меню", "⬅️ Назад"], state="*")
async def back_to_menu(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Головне меню:", reply_markup=kb.main_menu())

@dp.message_handler(lambda m: m.text == "🔥 Наші новинки", state="*")
async def novinki_h(m: types.Message, state: FSMContext):
    await catalog.show_novinki(m, state, cache.get_all(), bot)

@dp.message_handler(lambda m: m.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def category_h(m: types.Message, state: FSMContext):
    cat = m.text.replace("👟", "").replace("👠", "").strip()
    await state.update_data(category=cat)
    await catalog.show_brands(m, state, cache.get_all())

@dp.message_handler(lambda m: m.text.startswith("🔹 "))
async def brand_h(m: types.Message, state: FSMContext):
    await catalog.choose_size(m, state, cache.get_all())

@dp.callback_query_handler(lambda c: c.data.startswith('size_'), state="*")
async def size_select_h(c: types.CallbackQuery, state: FSMContext):
    size = c.data.replace("size_", "")
    data = await state.get_data()
    
    all_items = cache.get_all()
    products = [i for i in all_items if 
                str(i.get('Категорія')).strip() == data.get('category') and 
                str(i.get('Бренд')).strip() == data.get('brand') and 
                size in [s.strip() for s in str(i.get('Розміри', '')).replace(';', ',').split(',')]]
    
    if not products:
        return await c.answer("❌ Товарів цього розміру немає.", show_alert=True)

    ids = [str(i.get('Артикул')) for i in products if i.get('Артикул')]
    await state.update_data(product_ids=ids, size=size)
    await catalog.show_product(bot, c.from_user.id, 0, state, all_products=all_items)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def nav_h(c: types.CallbackQuery, state: FSMContext):
    action, idx = c.data.split('_')
    new_idx = int(idx) + 1 if action == 'next' else int(idx) - 1
    await catalog.show_product(bot, c.from_user.id, new_idx, state, c.message.message_id, cache.get_all())
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def buy_h(c: types.CallbackQuery, state: FSMContext):
    await order.process_buy(c, state, cache.get_all())

@dp.callback_query_handler(lambda c: c.data.startswith('more_photos_'), state="*")
async def more_photos_h(c: types.CallbackQuery, state: FSMContext):
    await catalog.show_more_photos(c, state, cache.get_all(), bot)

@dp.callback_query_handler(lambda c: c.data.startswith('descr_'), state="*")
async def descr_h(c: types.CallbackQuery):
    art = c.data.replace("descr_", "")
    item = cache.get_by_id(art)
    txt = item.get('Опис', "Опис скоро буде 😉") if item else "Не знайдено"
    await c.answer(txt, show_alert=True)

# Обробики станів замовлення
@dp.message_handler(content_types=['contact', 'text'], state=order.OrderState.waiting_for_phone)
async def phone_h(m, state): await order.get_phone(m, state)

@dp.message_handler(state=order.OrderState.waiting_for_fio)
async def fio_h(m, state): await order.get_fio(m, state)

@dp.message_handler(state=order.OrderState.waiting_for_delivery)
async def deliv_h(m, state): await order.get_delivery(m, state, bot)

if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
