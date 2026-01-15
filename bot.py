import os
import asyncio
import logging
import base64
import aiohttp
import aiosqlite
from io import BytesIO
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ======================= КОНФИГУРАЦИЯ =======================
BOT_TOKEN = "8217361037:AAEgJ6NugPqXDNX_stIOL5g7R1ovBxsLAWM"
GENAPI_KEY = "sk-dd7I7EH6Gtg0zBTDManlSPCLoBN8rQPAatfF57GFebec8vgBHVbnx15JTKMa"
AITUNNEL_KEY = "sk-aitunnel-9ho4TkDH1Vxr0koqvpQtPS1mL2Yyv1v8"
ADMIN_ID = 6387718314

FREE_DAILY_LIMIT = 10
PREMIUM_DAILY_LIMIT = float('inf')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = None

# ======================= FSM СОСТОЯНИЯ =======================
class ImageEditStates(StatesGroup):
    waiting_photo = State()
    waiting_prompt = State()

# ======================= БАЗА ДАННЫХ =======================
async def init_db():
    global db
    db = await aiosqlite.connect('bot.db')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            messages_today INTEGER DEFAULT 0,
            last_reset DATE,
            is_premium BOOLEAN DEFAULT 0
        )
    ''')
    await db.commit()
    logger.info("✅ Database connected (SQLite)")

async def get_user_messages(user_id: int) -> int:
    cursor = await db.execute(
        'SELECT messages_today, last_reset, is_premium FROM users WHERE user_id = ?', 
        (user_id,)
    )
    result = await cursor.fetchone()
    if not result:
        await db.execute(
            'INSERT INTO users (user_id, messages_today, last_reset, is_premium) VALUES (?, 0, ?, 0)',
            (user_id, datetime.now().date().isoformat())
        )
        await db.commit()
        return 0
    
    messages, last_reset, is_premium = result
    today = datetime.now().date().isoformat()
    
    if last_reset != today:
        await db.execute(
            'UPDATE users SET messages_today = 0, last_reset = ? WHERE user_id = ?',
            (today, user_id)
        )
        await db.commit()
        return 0
    
    return messages, is_premium

async def increment_messages(user_id: int):
    await db.execute(
        'UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?',
        (user_id,)
    )
    await db.commit()

# ======================= TELEGRAPH =======================
async def upload_to_telegraph(image_bytes: bytes) -> str:
    """Загрузка изображения в Telegraph с проверкой ошибок"""
    url = "https://telegra.ph/upload"
    
    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field('file', BytesIO(image_bytes), filename='image.jpg', content_type='image/jpeg')
        
        async with session.post(url, data=form) as resp:
            if resp.status != 200:
                logger.error(f"Telegraph error: {resp.status}")
                return None
            
            data = await resp.json()
            if 'error':
                logger.error(f"Telegraph JSON error: {data}")
                return None
            
            return f"https://telegra.ph{data[0]['src']}"

# ======================= SEEDIT API =======================
SEEDEDIT_URL = "https://api.gen-api.ru/api/v1/networks/seededit"

async def edit_image_with_seededit(prompt: str, image_bytes: bytes) -> bytes:
    """Редактирование изображения через SeedEdit API (6₽)"""
    # Конвертируем bytes в base64 data URL
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    image_data_url = f"image/jpeg;base64,{image_b64}"
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {GENAPI_KEY}'
    }
    
    payload = {
        "prompt": prompt,
        "image": image_data_url,
        "model": "seededit",
        "translate_input": True
    }
    
    timeout = 120  # 2 минуты максимум
    start_time = asyncio.get_event_loop().time()
    
    async with aiohttp.ClientSession() as session:
        # Создаём задачу
        async with session.post(SEEDEDIT_URL, json=payload, headers=headers) as resp:
            if resp.status != 200:
                logger.error(f"SeedEdit create error: {resp.status}")
                raise Exception(f"API error: {resp.status}")
            
            data = await resp.json()
            request_id = data.get("request_id")
            if not request_id:
                raise Exception("No request_id received")
        
        logger.info(f"SeedEdit request created: {request_id}")
        
        # Long polling результата
        while asyncio.get_event_loop().time() - start_time < timeout:
            await asyncio.sleep(5)
            
            async with session.get(
                f"{SEEDEDIT_URL}/{request_id}", 
                headers={'Authorization': f'Bearer {GENAPI_KEY}'}
            ) as status_resp:
                if status_resp.status != 200:
                    continue
                
                status_data = await status_resp.json()
                status = status_data.get("status")
                
                if status == "success":
                    output = status_data.get("output")
                    if isinstance(output, str):
                        # Если output - base64
                        return base64.b64decode(output)
                    elif isinstance(output, dict) and 'url' in output:
                        # Скачиваем по URL
                        async with session.get(output['url']) as img_resp:
                            return await img_resp.read()
                    else:
                        raise Exception("Invalid output format")
                
                elif status == "error":
                    raise Exception(f"SeedEdit error: {status_data}")
        
        raise Exception("Timeout: generation took too long")

# ======================= КЛАВИАТУРЫ =======================
def main_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 Чат с GPT"), KeyboardButton(text="👁 Vision")],
            [KeyboardButton(text="🎨 Редактировать фото"), KeyboardButton(text="⭐ Статус")],
            [KeyboardButton(text="/help")]
        ],
        resize_keyboard=True
    )
    return kb

def admin_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔄 Статистика", callback_data="admin_stats")]
    ])
    return kb

# ======================= ОБРАБОТЧИКИ =======================
@dp.message(Command("start"))
async def cmd_start(message: message):
    await message.answer(
        "🤖 Привет! Я AI-бот с генерацией изображений.\n\n"
        "• 💬 Чат с GPT-4o\n"
        "• 👁 Vision анализ фото\n"
        "• 🎨 Редактировать фото (SeedEdit 6₽)\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=main_keyboard()
    )

@dp.message(F.photo, ImageEditStates.waiting_photo)
async def process_edit_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    image_bytes = await bot.download_file(file.file_path)
    
    await state.update_data(image_bytes=image_bytes)
    await state.set_state(ImageEditStates.waiting_prompt)
    
    await message.answer(
        "📸 Фото получено!\n\n"
        "📝 Отправь промпт для редактирования "
        "(например: 'добавь радугу', 'сделай ночь')",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

@dp.message(ImageEditStates.waiting_prompt)
async def process_edit_prompt(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_keyboard())
        return
    
    user_id = message.from_user.id
    messages, is_premium = await get_user_messages(user_id)
    limit = PREMIUM_DAILY_LIMIT if is_premium else FREE_DAILY_LIMIT
    
    if messages >= limit:
        await message.answer(f"⚠️ Лимит: {messages}/{limit} сообщений сегодня")
        return
    
    await message.answer("🎨 Генерирую изображение...")
    await increment_messages(user_id)
    
    try:
        data = await state.get_data()
        image_bytes = data['image_bytes']
        
        edited_bytes = await edit_image_with_seededit(message.text, image_bytes)
        
        telegraph_url = await upload_to_telegraph(edited_bytes)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💾 Сохранить", callback_data="save_image")],
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="repeat_edit")]
        ])
        
        await message.answer_photo(
            photo=BufferedInputFile(edited_bytes, filename="edited.jpg"),
            caption=f"✅ Готово! SeedEdit (6₽)\n{telegraph_url}",
            reply_markup=kb
        )
        
    except Exception as e:
        logger.error(f"Edit error: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@dp.message(F.text == "🎨 Редактировать фото")
async def start_edit_photo(message: Message, state: FSMContext):
    await state.set_state(ImageEditStates.waiting_photo)
    await message.answer(
        "📤 Отправь фото для редактирования",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👨‍💼 Admin панель", reply_markup=admin_keyboard())

@dp.message(F.text == "/help")
async def cmd_help(message: Message):
    await message.answer(
        "📚 Помощь:\n\n"
        "💬 Чат - обычный текст\n"
        "👁 Vision - анализ фото\n"
        "🎨 Редактировать фото:\n"
        "  1. Нажми кнопку\n"
        "  2. Отправь фото\n"
        "  3. Напиши промпт\n\n"
        "💰 Цена: 6₽ за редактирование\n"
        "⚙️ Лимиты: Free 10/день, Premium ∞",
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "⭐ Статус")
async def status(message: Message):
    messages, is_premium = await get_user_messages(message.from_user.id)
    limit = "∞" if is_premium else FREE_DAILY_LIMIT
    await message.answer(f"📊 Статус:\nСообщений сегодня: {messages}/{limit}")

# ======================= ЗАПУСК =======================
async def main():
    await init_db()
    logger.info(f"✅ Bot starting... Token: {BOT_TOKEN[:20]}...")
    logger.info(f"Free: {FREE_DAILY_LIMIT} сообщ/день")
    logger.info(f"Premium: {PREMIUM_DAILY_LIMIT} сообщ/день")
    
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
