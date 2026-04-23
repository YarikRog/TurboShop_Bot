import os, logging, asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.redis import RedisStorage2

import database as db
import keyboards as kb
import handlers_order as order
import handlers_catalog as catalog
import handlers_admin as admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TurboBot.Main")

TOKEN = os.getenv("BOT_TOKEN")

storage = RedisStorage2(
    host=os.getenv("REDIS_HOST", "ballast.proxy.rlwy.net"),
    port=int(os.getenv("REDIS_PORT", 28367)),
    password=os.getenv("REDIS_PASSWORD"),
    db=5,
    pool_size=10
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


async def on_startup(_):
    await cache.update()
    asyncio.create_task(cache_refresher())


async def cache_refresher():
    while True:
        await asyncio.sleep(60)
        await cache.update()


@dp.message_handler(commands=['start'], state="*")
async def start_cmd(m: types.Message, state: FSMContext):
    await state.finish()
    args = m.get_args().strip()
    source = "direct"

    if args.startswith("buy_"):
        raw_payload = args.replace("buy_", "", 1)
        article, _, source_suffix = raw_payload.partition("_")
        source = source_suffix or "deep_link"

        product = await db.get_product_by_article(article)
        if product:
            all_products = cache.get_all()
            if not any(str(item.get("Артикул", "")).strip() == article for item in all_products):
                all_products = [*all_products, product]

            await state.update_data(product_ids=[article], size="Оберіть розмір", source=source, last_album_ids=[])
            await m.answer("Вітаємо у TurboShop! 👟", reply_markup=kb.main_menu(admin.is_admin(m.from_user.id)))
            await catalog.show_product(bot, m.from_user.id, 0, state, all_products=all_products)
        else:
            await m.answer("Товар за посиланням не знайдено.", reply_markup=kb.main_menu(admin.is_admin(m.from_user.id)))
    else:
        await m.answer("Вітаємо у TurboShop! 👟", reply_markup=kb.main_menu(admin.is_admin(m.from_user.id)))

    asyncio.create_task(
        db.register_user(
            {
                "telegram_id": m.from_user.id,
                "username": m.from_user.username or "",
                "source": source,
            }
        )
    )


@dp.message_handler(lambda m: m.text in ["🏠 Головне меню", "⬅️ Назад"], state="*")
async def back_to_menu(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Головне меню:", reply_markup=kb.main_menu(admin.is_admin(m.from_user.id)))


@dp.message_handler(lambda m: m.text == "❌ Скасувати", state="*")
async def cancel_flow(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Дію скасовано.", reply_markup=kb.main_menu(admin.is_admin(m.from_user.id)))


@dp.message_handler(lambda m: m.text == "🔥 Наші новинки", state="*")
async def novinki_h(m: types.Message, state: FSMContext):
    await catalog.show_novinki(m, state, cache.get_all(), bot)


@dp.message_handler(lambda m: m.text in ["👟 Чоловічі", "
