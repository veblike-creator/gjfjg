import os
import logging
import asyncio
import aiosqlite
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8217361037:AAEgJ6NugPqXDNXstIOL5g7R1ovBxsLAWM"
AITUNNEL_KEY = "sk-aitunnel-9ho4TkDH1Vxr0koqvpQtPS1mL2Yyv1v8"
GENAPI_KEY = "sk-dd7I7EH6Gtg0zBTDManlSPCLoBN8rQPAatfF57GFebec8vgBHVbnx15JTKMa"
ADMIN_ID = int(os.getenv("ADMIN_ID", "6387718314"))
DB_PATH = "/app/bot.db"

FREE_DAILY_LIMIT = 20
PREMIUM_DAILY_LIMIT = 1000

# Модели
FREE_MODELS = ["gpt-4.1-mini"]
VISION_MODELS = ["gemini-2.0-flash-thinking", "gemini-2.0-flash-exp", "claude-3.5-sonnet"]

MODEL_NAMES = {
    "gpt-4.1-mini": "🆓 GPT-4.1 Mini",
    "gpt-4o": "💎 GPT-4o",
    "gemini-2.0-flash-thinking": "💎 Gemini 2.0 Flash Thinking 👁",
    "gemini-2.0-flash-exp": "💎 Gemini 2.0 Flash Experimental 👁",
    "claude-3.5-sonnet": "💎 Claude 3.5 Sonnet 👁"
}

# FSM состояния
class ImageGen(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_photo = State()

# База данных SQLite
class Database:
    def __init__(self):
        self.db_path = DB_PATH

    async def connect(self):
        await self.init_db()

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    current_model TEXT DEFAULT 'gpt-4.1-mini',
                    is_premium INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    date DATE DEFAULT (date('now')),
                    count INTEGER DEFAULT 1,
                    UNIQUE(user_id, date)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    model TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admin_state (
                    admin_id INTEGER,
                    state_key TEXT,
                    state_value INTEGER DEFAULT 1,
                    PRIMARY KEY (admin_id, state_key)
                )
            """)
            await db.commit()

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await db.execute(
                        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                        (user_id,)
                    )
                    await db.commit()
                    return {"user_id": user_id, "username": None, "current_model": "gpt-4.1-mini", "is_premium": False}
                return dict(row)

    async def set_model(self, user_id, model):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET current_model = ? WHERE user_id = ?", (model, user_id))
            await db.commit()

    async def set_premium(self, user_id, status):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (1 if status else 0, user_id))
            await db.commit()

    async def update_username(self, user_id, username):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            await db.commit()

    async def get_user_by_username(self, username):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users WHERE username = ?", (username,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def check_limit(self, user_id):
        user = await self.get_user(user_id)
        limit = PREMIUM_DAILY_LIMIT if user['is_premium'] else FREE_DAILY_LIMIT
        used = await self.get_today_messages(user_id)
        return (used < limit, limit - used)

    async def get_today_messages(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT count FROM messages WHERE user_id = ? AND date = date('now')",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def increment_messages(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR IGNORE INTO messages (user_id, date, count)
                VALUES (?, date('now'), 0)
            """, (user_id,))
            await db.execute("""
                UPDATE messages SET count = count + 1
                WHERE user_id = ? AND date = date('now')
            """, (user_id,))
            await db.commit()

    async def add_message(self, user_id, model, role, content):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO conversations (user_id, model, role, content) VALUES (?, ?, ?, ?)",
                (user_id, model, role, content)
            )
            await db.commit()

    async def get_history(self, user_id, model, limit=10):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT role, content FROM conversations WHERE user_id = ? AND model = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, model, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [{"role": r['role'], "content": r['content']} for r in reversed(rows)]

    async def clear_history(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            await db.commit()

    async def set_admin_state(self, admin_id, state_key):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO admin_state (admin_id, state_key, state_value) VALUES (?, ?, 1)",
                (admin_id, state_key)
            )
            await db.commit()

    async def get_admin_state(self, admin_id, state_key):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT state_value FROM admin_state WHERE admin_id = ? AND state_key = ?",
                (admin_id, state_key)
            ) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else False

    async def clear_admin_state(self, admin_id, state_key):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM admin_state WHERE admin_id = ? AND state_key = ?",
                (admin_id, state_key)
            )
            await db.commit()

    async def get_all_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

# Telegraph загрузка
async def upload_to_telegraph(photo_bytes):
    """Загружает фото на Telegraph и возвращает URL"""
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            # Fix: add photo bytes as file with proper content type
            form.add_field('file', photo_bytes, filename='image.jpg', content_type='image/jpeg')

            async with session.post('https://telegra.ph/upload', data=form) as response:
                if response.status != 200:
                    logger.error(f"Telegraph HTTP error: {response.status}")
                    return None

                result = await response.json()
                logger.info(f"Telegraph response: {result}")

                # Проверяем формат ответа
                if isinstance(result, list) and len(result) > 0:
                    if isinstance(result[0], dict) and 'src' in result[0]:
                        return f"https://telegra.ph{result[0]['src']}"

                # Если ответ - ошибка
                if isinstance(result, dict) and 'error' in result:
                    logger.error(f"Telegraph error: {result['error']}")
                else:
                    logger.error(f"Telegraph unexpected response: {result}")

                return None
    except Exception as e:
        logger.error(f"Telegraph upload error: {e}")
        return None

# GenAPI функции
async def generate_seededit(prompt, photo_path):
    try:
        photo_file = await bot.download_file(photo_path)
        photo_bytes = photo_file.read()

        image_url = await upload_to_telegraph(photo_bytes)

        if not image_url:
            logger.error("Failed to upload image to Telegraph")
            return None

        logger.info(f"Uploaded to Telegraph: {image_url}")

        payload = {
            "callback_url": None,
            "prompt": prompt,
            "image": image_url
        }

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {GENAPI_KEY}'
        }

        async with aiohttp.ClientSession() as session:
            url_endpoint = "https://api.gen-api.ru/api/v1/networks/seededit"

            async with session.post(url_endpoint, json=payload, headers=headers) as response:
                response_text = await response.text()
                logger.info(f"SeedEdit response: {response.status} - {response_text}")

                if response.status != 200:
                    logger.error(f"SeedEdit error: {response.status} - {response_text}")
                    return None

                result = await response.json()

                if result.get('error'):
                    logger.error(f"SeedEdit API error: {result}")
                    return None

                task_id = result.get('task_id')

                # Проверяем статус задачи
                for _ in range(60):
                    await asyncio.sleep(5)

                    async with session.get(
                        f"https://api.gen-api.ru/api/v1/tasks/{task_id}",
                        headers={'Authorization': f'Bearer {GENAPI_KEY}'}
                    ) as check_response:
                        check_result = await check_response.json()
                        status = check_result.get('status')

                        if status == 'completed':
                            return check_result.get('result', {}).get('images', [None])[0]
                        elif status == 'failed':
                            logger.error(f"Task failed: {check_result}")
                            return None

        return None

    except Exception as e:
        logger.error(f"SeedEdit error: {e}")
        return None

async def get_ai_response(prompt, model, user_id):
    try:
        history = await db.get_history(user_id, model)

        headers = {
            "Authorization": f"Bearer {AITUNNEL_KEY}",
            "Content-Type": "application/json"
        }

        messages = history + [{"role": "user", "content": prompt}]

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 50000
        }

        logger.info(f"Sending to AITunnel: model={model}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.aitunnel.ru/v1/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                logger.info(f"AITunnel response: {response.status}")

                if response.status == 200:
                    result = await response.json()
                    ai_response = result["choices"][0]["message"]["content"]

                    # Сохраняем в историю
                    await db.add_message(user_id, model, "user", prompt)
                    await db.add_message(user_id, model, "assistant", ai_response)

                    return ai_response
                else:
                    error_text = await response.text()
                    logger.error(f"AITunnel error {response.status}: {error_text}")
                    return f"❌ Ошибка API: {response.status}"

    except Exception as e:
        logger.error(f"AI error: {e}")
        return "❌ Произошла ошибка при обработке запроса"

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# Клавиатуры
def get_main_keyboard(is_admin=False):
    keyboard = [
        [KeyboardButton(text="🤖 Выбрать модель"), KeyboardButton(text="📊 Мой статус")],
        [KeyboardButton(text="🎨 Генерация"), KeyboardButton(text="🗑 Очистить историю")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="👑 Админ панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="➕ Выдать Premium", callback_data="admin_grant")],
        [InlineKeyboardButton(text="➖ Отозвать Premium", callback_data="admin_revoke")]
    ])

def get_category_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Текстовые модели", callback_data="category_text")],
        [InlineKeyboardButton(text="👁 Мультимодальные", callback_data="category_vision")]
    ])

def get_generation_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 SeedEdit (редактирование фото)", callback_data="gen_seededit")]
    ])

async def is_premium(user_id):
    if user_id == ADMIN_ID:
        return True
    user = await db.get_user(user_id)
    return bool(user.get('is_premium', 0))

# Обработчики
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username

    await db.get_user(user_id)
    if username:
        await db.update_username(user_id, username)

    is_admin = (user_id == ADMIN_ID)

    welcome_text = f"""👋 Привет, {message.from_user.first_name}!

Я - AI бот с доступом к лучшим моделям:
• GPT-4.1 Mini (бесплатно)
• GPT-4o, Gemini, Claude (Premium)

Используй кнопки ниже для управления 👇"""

    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin))

@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    if await is_premium(message.from_user.id):
        await message.answer("✅ У вас уже есть Premium!")
        return

    user_id = message.from_user.id

    text = f"""💎 Premium подписка

Получите доступ ко всем моделям:
• GPT-4o
• Gemini 2.0 Flash Thinking 👁
• Gemini 2.0 Flash Experimental 👁
• Claude 3.5 Sonnet 👁

🎯 Для получения Premium:
1. Ваш ID: `{user_id}`
2. Нажмите кнопку ниже
3. Отправьте ID администратору"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать администратору", url="tg://user?id=6387718314")]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.message(Command("models"))
@dp.message(F.text == "🤖 Выбрать модель")
async def btn_models(message: Message):
    if await is_premium(message.from_user.id):
        await message.answer("⭐ Выберите категорию:\n👁 = анализ изображений", reply_markup=get_category_keyboard())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🆓 GPT-4.1 Mini", callback_data="model_gpt-4.1-mini")],
            [InlineKeyboardButton(text="💎 Купить Premium", callback_data="get_premium")]
        ])
        await message.answer("Выберите модель:", reply_markup=kb)

@dp.message(Command("status"))
@dp.message(F.text == "📊 Мой статус")
async def btn_status(message: Message):
    user = await db.get_user(message.from_user.id)
    model_name = MODEL_NAMES.get(user['current_model'], user['current_model'])
    vision = "✅" if user['current_model'] in VISION_MODELS else "❌"
    used = await db.get_today_messages(message.from_user.id)
    limit = PREMIUM_DAILY_LIMIT if user['is_premium'] else FREE_DAILY_LIMIT

    if message.from_user.id == ADMIN_ID:
        text = f"""👑 Статус: Администратор

🤖 Текущая модель: {model_name}
👁 Анализ изображений: {vision}
📊 Сообщений сегодня: {used} / ∞"""
    elif user['is_premium']:
        text = f"""💎 Статус: Premium

🤖 Текущая модель: {model_name}
👁 Анализ изображений: {vision}
📊 Сообщений сегодня: {used} / {limit}"""
    else:
        text = f"""🆓 Статус: Бесплатный

🤖 Текущая модель: {model_name}
👁 Анализ изображений: {vision}
📊 Сообщений сегодня: {used} / {limit}

💡 Получите Premium для доступа ко всем моделям!
/premium"""

    await message.answer(text)

@dp.message(F.text == "🗑 Очистить историю")
async def btn_clear(message: Message):
    await db.clear_history(message.from_user.id)
    await message.answer("✅ История диалогов очищена!")

@dp.message(F.text == "🎨 Генерация")
async def btn_generation(message: Message):
    if not await is_premium(message.from_user.id):
        await message.answer("❌ Генерация доступна только для Premium пользователей\n\nИспользуйте /premium")
        return

    await message.answer("🎨 Выберите тип генерации:", reply_markup=get_generation_keyboard())

@dp.message(F.text == "👑 Админ панель")
async def btn_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("👑 Админ панель", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "category_text")
async def category_text(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆓 GPT-4.1 Mini", callback_data="model_gpt-4.1-mini")],
        [InlineKeyboardButton(text="💎 GPT-4o", callback_data="model_gpt-4o")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_categories")]
    ])
    await callback.message.edit_text("💬 Текстовые модели:", reply_markup=kb)

@dp.callback_query(F.data == "category_vision")
async def category_vision(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Gemini 2.0 Flash Thinking 👁", callback_data="model_gemini-2.0-flash-thinking")],
        [InlineKeyboardButton(text="💎 Gemini 2.0 Flash Experimental 👁", callback_data="model_gemini-2.0-flash-exp")],
        [InlineKeyboardButton(text="💎 Claude 3.5 Sonnet 👁", callback_data="model_claude-3.5-sonnet")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_categories")]
    ])
    await callback.message.edit_text("👁 Мультимодальные модели:", reply_markup=kb)

@dp.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    await callback.message.edit_text("⭐ Выберите категорию:\n👁 = анализ изображений", reply_markup=get_category_keyboard())

@dp.callback_query(F.data.startswith("model_"))
async def select_model(callback: CallbackQuery):
    model = callback.data.replace("model_", "")
    user_id = callback.from_user.id

    if model not in FREE_MODELS and not await is_premium(user_id):
        await callback.answer("❌ Требуется Premium!", show_alert=True)
        return

    await db.set_model(user_id, model)
    model_name = MODEL_NAMES.get(model, model)
    await callback.message.edit_text(f"✅ Выбрана модель: {model_name}")
    await callback.answer()

@dp.callback_query(F.data == "get_premium")
async def get_premium_callback(callback: CallbackQuery):
    user_id = callback.from_user.id

    text = f"""💎 Premium подписка

Получите доступ ко всем моделям!

🎯 Для получения Premium:
1. Ваш ID: `{user_id}`
2. Нажмите кнопку ниже
3. Отправьте ID администратору"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать администратору", url="tg://user?id=6387718314")]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data == "gen_seededit")
async def gen_seededit_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Отправьте текстовый промпт для редактирования изображения:")
    await state.set_state(ImageGen.waiting_for_prompt)
    await callback.answer()

@dp.message(ImageGen.waiting_for_prompt)
async def seededit_prompt_received(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer("🖼 Теперь отправьте фото для редактирования:")
    await state.set_state(ImageGen.waiting_for_photo)

@dp.message(ImageGen.waiting_for_photo, F.photo)
async def seededit_photo_received(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = data.get('prompt')

    await message.answer("⏳ Генерирую изображение... Это может занять до 5 минут.")

    photo = message.photo[-1]
    photo_path = (await bot.get_file(photo.file_id)).file_path

    result_url = await generate_seededit(prompt, photo_path)

    if result_url:
        await message.answer_photo(result_url, caption=f"✅ Готово!\n\n📝 Промпт: {prompt}")
    else:
        await message.answer("❌ Ошибка генерации. Попробуйте еще раз.")

    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    users = await db.get_all_users()
    total = len(users)
    premium = sum(1 for u in users if u.get('is_premium'))
    free = total - premium

    text = f"""📊 Статистика бота

👥 Всего пользователей: {total}
💎 Premium: {premium}
🆓 Бесплатных: {free}"""

    await callback.message.edit_text(text, reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "admin_grant")
async def admin_grant(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    await db.set_admin_state(ADMIN_ID, "waiting_grant")
    await callback.message.edit_text(
        "➕ Выдать Premium\n\nОтправьте:\n• ID пользователя (например: 123456789)\n• Username (например: @username)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
        ])
    )

@dp.callback_query(F.data == "admin_revoke")
async def admin_revoke(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    await db.set_admin_state(ADMIN_ID, "waiting_revoke")
    await callback.message.edit_text(
        "➖ Отозвать Premium\n\nОтправьте:\n• ID пользователя (например: 123456789)\n• Username (например: @username)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
        ])
    )

@dp.callback_query(F.data == "admin_cancel")
async def admin_cancel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    await db.clear_admin_state(ADMIN_ID, "waiting_grant")
    await db.clear_admin_state(ADMIN_ID, "waiting_revoke")
    await callback.message.edit_text("👑 Админ панель", reply_markup=get_admin_keyboard())

@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    if user['current_model'] not in VISION_MODELS:
        await message.answer("❌ Текущая модель не поддерживает анализ изображений.\n\nВыберите мультимодальную модель (👁) через /models")
        return

    if not await is_premium(user_id):
        await message.answer("❌ Анализ изображений доступен только для Premium пользователей.")
        return

    can_send, remaining = await db.check_limit(user_id)
    if not can_send:
        await message.answer("❌ Лимит исчерпан. Попробуйте завтра!")
        return

    await message.answer("📸 Функция анализа изображений в разработке...")

@dp.message(F.text)
async def handle_text(message: Message):
    user_id = message.from_user.id

    waiting_grant = await db.get_admin_state(ADMIN_ID, "waiting_grant")
    if waiting_grant and user_id == ADMIN_ID:
        await db.clear_admin_state(ADMIN_ID, "waiting_grant")
        user_input = message.text.strip()

        if user_input.startswith('@'):
            username = user_input[1:]
            target_id = await db.get_user_by_username(username)
            if target_id:
                await db.set_premium(target_id, True)
                await message.answer(f"✅ Premium выдан пользователю @{username} (ID: `{target_id}`)", parse_mode="HTML", reply_markup=get_admin_keyboard())
            else:
                await message.answer(f"❌ Пользователь @{username} не найден в базе\n\nПользователь должен:\n1. Запустить бота командой /start\n2. После этого попробуйте снова", reply_markup=get_admin_keyboard())
        else:
            try:
                target_id = int(user_input)
                await db.set_premium(target_id, True)
                await message.answer(f"✅ Premium выдан пользователю: `{target_id}`", parse_mode="HTML", reply_markup=get_admin_keyboard())
            except ValueError:
                await message.answer("❌ Неверный формат!\n\nОтправьте:\n• ID (цифры): 123456789\n• Username: @username", reply_markup=get_admin_keyboard())
        return

    waiting_revoke = await db.get_admin_state(ADMIN_ID, "waiting_revoke")
    if waiting_revoke and user_id == ADMIN_ID:
        await db.clear_admin_state(ADMIN_ID, "waiting_revoke")
        user_input = message.text.strip()

        if user_input.startswith('@'):
            username = user_input[1:]
            target_id = await db.get_user_by_username(username)
            if target_id:
                await db.set_premium(target_id, False)
                await message.answer(f"✅ Premium отозван у пользователя @{username} (ID: `{target_id}`)", parse_mode="HTML", reply_markup=get_admin_keyboard())
            else:
                await message.answer(f"❌ Пользователь @{username} не найден в базе", reply_markup=get_admin_keyboard())
        else:
            try:
                target_id = int(user_input)
                await db.set_premium(target_id, False)
                await message.answer(f"✅ Premium отозван у пользователя: `{target_id}`", parse_mode="HTML", reply_markup=get_admin_keyboard())
            except ValueError:
                await message.answer("❌ Неверный формат!\n\nОтправьте:\n• ID (цифры): 123456789\n• Username: @username", reply_markup=get_admin_keyboard())
        return

    user = await db.get_user(user_id)

    if user['current_model'] not in FREE_MODELS and not await is_premium(user_id):
        await message.answer("❌ Нет доступа. Используйте /models")
        return

    can_send, remaining = await db.check_limit(user_id)
    if not can_send:
        await message.answer("❌ Лимит исчерпан. Попробуйте завтра!")
        return

    await bot.send_chat_action(message.chat.id, "typing")
    await db.increment_messages(user_id)

    response = await get_ai_response(message.text, user['current_model'], user_id)

    model_name = MODEL_NAMES.get(user['current_model'], user['current_model'])

    if len(response) > 4000:
        await message.answer(f"🤖 {model_name}\n\n{response[:4000]}...")
        await message.answer(response[4000:])
    else:
        await message.answer(f"🤖 {model_name}\n\n{response}")

async def main():
    await db.connect()
    logger.info("Database connected (SQLite)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
