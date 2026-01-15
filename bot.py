import os
import 
API_KEY_GEN = "sk-dd7I7EH6Gtg0zBTDManlSPCLoBN8rQPAatfF57GFebec8vgBHVbnx15JTKMa"
GEN_API_URL = "https://api.gen-api.ru/api/v1/networks/seededit"
asyncio
import logging
import base64
import tempfile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp
import aiosqlite
import json
import requests  # Для gen-api
from datetime import date

TELEGRAM_TOKEN = "8217361037:AAEgJ6NugPqXDNX_stIOL5g7R1ovBxsLAWM"
ADMIN_ID = 6387718314
API_KEY = "sk-aitunnel-9ho4TkDH1Vxr0koqvpQtPS1mL2Yyv1v8"
API_URL = "https://api.aitunnel.ru/v1/chat/completions"
SYSTEM_PROMPT = "Ты - AI ассистент. ВСЕГДА отвечай ТОЛЬКО на русском языке, независимо от языка вопроса пользователя. Если пользователь пишет на другом языке - всё равно отвечай по-русски. Исключение: только если пользователь явно просит ответить на английском языке."

DB_FILE = "bot_data.db"
FREE_DAILY_LIMIT = 20
PREMIUM_DAILY_LIMIT = 200

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

FREE_MODELS = ["gpt-4.1-mini"]
VISION_MODELS = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4.5", "claude-opus-4.5", "gemini-2.5-pro", "gemini-2.5-flash"]

# FSM состояния для работы с фото
class ImageGenState(StatesGroup):
    waiting_for_prompt = State()

MODEL_NAMES = {
    "gpt-4.1-mini": "GPT-4.1 Mini", "gpt-4.1": "GPT-4.1", "gpt-4": "GPT-4", "gpt-4o": "GPT-4o", "gpt-4o-mini": "GPT-4o Mini",
    "gpt-5": "GPT-5", "gpt-5.2": "GPT-5.2", "gpt-5.2-pro": "GPT-5.2 Pro", "gpt-5.1": "GPT-5.1", "gpt-5-nano": "GPT-5 Nano",
    "gpt-5-mini": "GPT-5 Mini", "claude-haiku-4.5": "Claude Haiku", "claude-sonnet-4.5": "Claude Sonnet", "claude-opus-4.5": "Claude Opus",
    "gemini-2.5-flash-lite": "Gemini Flash Lite", "gemini-2.5-flash": "Gemini Flash", "gemini-2.5-pro": "Gemini Pro",
    "gemini-3-flash-preview": "Gemini 3 Flash", "gemini-3-pro-preview": "Gemini 3 Pro", "qwen3-coder": "Qwen Coder",
    "qwen3-coder-30b-a3b": "Qwen Coder 30B", "qwen3-30b-a3b-instruct": "Qwen 30B", "qwen3-235b-a22b-2507": "Qwen 235B",
    "qwen3-max": "Qwen Max", "mistral-large-2512": "Mistral Large", "mistral-small-3.2-24b": "Mistral Small",
    "mistral-medium-3.1": "Mistral Medium", "mistral-nemo": "Mistral Nemo", "deepseek-v3.2": "DeepSeek v3.2",
    "deepseek-v3.2-speciale": "DeepSeek Special", "deepseek-r1-0528": "DeepSeek R1", "deepseek-chat-v3.1": "DeepSeek Chat",
    "llama-4-scout": "Llama Scout", "llama-4-maverick": "Llama Maverick", "llama-3.3-70b-instruct": "Llama 70B",
    "grok-4.1-fast": "Grok Fast", "grok-4": "Grok 4", "grok-code-fast-1": "Grok Code", "codestral-2508": "Codestral",
    "devstral-small": "Devstral", "sonar": "Sonar", "sonar-pro": "Sonar Pro", "sonar-pro-search": "Sonar Search",
    "sonar-deep-research": "Sonar Research", "kimi-k2-thinking": "Kimi Thinking", "kimi-k2-0905": "Kimi K2"
}

PREMIUM_MODELS = {
    "GPT Models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4", "gpt-4o", "gpt-4o-mini", "gpt-5", "gpt-5.2", "gpt-5.2-pro", "gpt-5.1", "gpt-5-nano", "gpt-5-mini"],
    "Claude Models": ["claude-haiku-4.5", "claude-sonnet-4.5", "claude-opus-4.5"],
    "Gemini Models": ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview", "gemini-3-pro-preview"],
    "Qwen Models": ["qwen3-coder", "qwen3-coder-30b-a3b", "qwen3-30b-a3b-instruct", "qwen3-235b-a22b-2507", "qwen3-max"],
    "Mistral Models": ["mistral-large-2512", "mistral-small-3.2-24b", "mistral-medium-3.1", "mistral-nemo"],
    "DeepSeek Models": ["deepseek-v3.2", "deepseek-v3.2-speciale", "deepseek-r1-0528", "deepseek-chat-v3.1"],
    "Llama Models": ["llama-4-scout", "llama-4-maverick", "llama-3.3-70b-instruct"],
    "Grok Models": ["grok-4.1-fast", "grok-4", "grok-code-fast-1"],
    "Other Models": ["codestral-2508", "devstral-small", "sonar", "sonar-pro", "sonar-pro-search", "sonar-deep-research", "kimi-k2-thinking", "kimi-k2-0905"]
}


class ImageGenState(StatesGroup):
    waiting_for_prompt = State()
class BotDatabase:
    def __init__(self):
        self.db_path = DB_FILE
        self._db = None
        self._lock = asyncio.Lock()

    async def connect(self):
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path, check_same_thread=False)
            self._db.row_factory = aiosqlite.Row
        return self._db

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def init_db(self):
        db = await self.connect()
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_premium BOOLEAN DEFAULT 0,
            current_model TEXT DEFAULT 'gpt-4.1-mini',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS daily_limits (
            user_id INTEGER,
            message_date DATE,
            messages_used INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, message_date)
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS chat_context (
            user_id INTEGER PRIMARY KEY,
            context_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS admin_states (
            admin_id INTEGER,
            state_key TEXT,
            state_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (admin_id, state_key)
        )''')
        await db.commit()
        print(f"База данных инициализирована: {self.db_path}")

    async def get_user(self, user_id: int, username: str = None):
        async with self._lock:
            db = await self.connect()
            async with db.execute("SELECT user_id, is_premium, current_model, username FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    if username and username != row[3]:
                        await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
                        await db.commit()
                    return {'user_id': row[0], 'is_premium': bool(row[1]), 'current_model': row[2] or 'gpt-4.1-mini', 'username': row[3]}
                await db.execute("INSERT OR IGNORE INTO users (user_id, username, is_premium, current_model) VALUES (?, ?, 0, 'gpt-4.1-mini')", (user_id, username))
                await db.commit()
                return {'user_id': user_id, 'is_premium': False, 'current_model': 'gpt-4.1-mini', 'username': username}

    async def get_user_by_username(self, username: str):
        async with self._lock:
            db = await self.connect()
            async with db.execute("SELECT user_id FROM users WHERE username = ? COLLATE NOCASE", (username,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_premium(self, user_id: int, is_premium: bool):
        async with self._lock:
            db = await self.connect()
            await db.execute("INSERT OR IGNORE INTO users (user_id, is_premium) VALUES (?, ?)", (user_id, int(is_premium)))
            await db.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (int(is_premium), user_id))
            await db.commit()

    async def set_model(self, user_id: int, model: str):
        async with self._lock:
            db = await self.connect()
            await db.execute("UPDATE users SET current_model = ? WHERE user_id = ?", (model, user_id))
            await db.commit()

    async def get_today_messages(self, user_id: int):
        async with self._lock:
            today = date.today().isoformat()
            db = await self.connect()
            async with db.execute("SELECT messages_used FROM daily_limits WHERE user_id = ? AND message_date = ?", (user_id, today)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def increment_messages(self, user_id: int):
        async with self._lock:
            today = date.today().isoformat()
            db = await self.connect()
            await db.execute("INSERT INTO daily_limits (user_id, message_date, messages_used) VALUES (?, ?, 1) ON CONFLICT(user_id, message_date) DO UPDATE SET messages_used = messages_used + 1", (user_id, today))
            await db.commit()

    async def check_limit(self, user_id: int):
        user = await self.get_user(user_id)
        limit = PREMIUM_DAILY_LIMIT if user['is_premium'] else FREE_DAILY_LIMIT
        used = await self.get_today_messages(user_id)
        return used < limit, limit - used

    async def save_context(self, user_id: int, context: list):
        async with self._lock:
            context_json = json.dumps(context, ensure_ascii=False)
            db = await self.connect()
            await db.execute("INSERT OR REPLACE INTO chat_context (user_id, context_json) VALUES (?, ?)", (user_id, context_json))
            await db.commit()

    async def get_context(self, user_id: int):
        async with self._lock:
            db = await self.connect()
            async with db.execute("SELECT context_json FROM chat_context WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
        return []

    async def clear_context(self, user_id: int):
        async with self._lock:
            db = await self.connect()
            await db.execute("DELETE FROM chat_context WHERE user_id = ?", (user_id,))
            await db.commit()

    async def get_stats(self):
        async with self._lock:
            db = await self.connect()
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM users") as cursor:
                total = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM users WHERE is_premium = 1") as cursor:
                premium = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM users WHERE is_premium = 0") as cursor:
                free = (await cursor.fetchone())[0]
            return {'total': total, 'premium': premium, 'free': free}

    async def set_admin_state(self, admin_id: int, key: str, value: str):
        async with self._lock:
            db = await self.connect()
            await db.execute("INSERT OR REPLACE INTO admin_states (admin_id, state_key, state_value) VALUES (?, ?, ?)", (admin_id, key, value))
            await db.commit()

    async def get_admin_state(self, admin_id: int, key: str):
        async with self._lock:
            db = await self.connect()
            async with db.execute("SELECT state_value FROM admin_states WHERE admin_id = ? AND state_key = ?", (admin_id, key)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def clear_admin_state(self, admin_id: int, key: str):
        async with self._lock:
            db = await self.connect()
            await db.execute("DELETE FROM admin_states WHERE admin_id = ? AND state_key = ?", (admin_id, key))
            await db.commit()

db = BotDatabase()

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="models", description="Выбрать модель"),
        BotCommand(command="status", description="Проверить статус"),
        BotCommand(command="clear", description="Очистить историю"),
        BotCommand(command="help", description="Справка"),
        BotCommand(command="price", description="Тарифы")
    ]
    await bot.set_my_commands(commands)
    print("Меню команд установлено!")

def get_user_keyboard(is_admin=False):
    keyboard = [
        [KeyboardButton(text="🤖 Выбрать модель"), KeyboardButton(text="📊 Мой статус")],
        [KeyboardButton(text="🗑 Очистить историю"), KeyboardButton(text="💎 Тарифы")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="👑 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Выдать Premium"), KeyboardButton(text="➖ Отозвать Premium")],
        [KeyboardButton(text="📈 Статистика пользователей")],
        [KeyboardButton(text="◀️ Назад в меню")]
    ], resize_keyboard=True)

async def download_image(file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
        async with session.get(url) as response:
            return await response.read()

def encode_image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode('utf-8')

async def generate_image_from_photo(prompt: str, image_base64: str = None) -> bytes:
    """Генерация/редактирование изображения через AITunnel API"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Если есть референсное фото - используем /images/edit
    if image_base64:
        endpoint = "https://api.aitunnel.ru/v1/images/edit"
        payload = {
            "model": "gpt-image-1",
            "prompt": prompt,
            "quality": "medium",
            "size": "1024x1024",
            "moderation": "low",
            "output_format": "png",
            "image": [f"data:image/png;base64,{image_base64}"]
        }
    else:
        # Без фото - просто генерация
        endpoint = "https://api.aitunnel.ru/v1/images/generate"
        payload = {
            "model": "gpt-image-1",
            "prompt": prompt,
            "quality": "medium",
            "size": "1024x1024",
            "moderation": "low",
            "output_format": "png"
        }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    # AITunnel возвращает b64_json в data[0]
                    if 'data' in data and len(data['data']) > 0:
                        b64_json = data['data'][0].get('b64_json')
                        if b64_json:
                            return base64.b64decode(b64_json)

                    logging.error(f"No b64_json in response: {data}")
                    return None
                else:
                    error_text = await response.text()
                    logging.error(f"Image generation failed: {response.status} - {error_text}")
                    return None
    except asyncio.TimeoutError:
        logging.error("Image generation timeout")
        return None
    except Exception as e:
        logging.error(f"Image generation error: {e}")
        return None

async def get_ai_response(user_message: str, model: str, user_id: int, image_base64: str = None) -> str:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    context = await db.get_context(user_id)
    if not context:
        context = [{"role": "system", "content": SYSTEM_PROMPT}]

    if image_base64 and model in VISION_MODELS:
        content = [{"type": "text", "text": user_message}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}]
        context.append({"role": "user", "content": content})
    else:
        context.append({"role": "user", "content": user_message})

    if len(context) > 11:
        context = [context[0]] + context[-10:]

    payload = {"model": model, "messages": context}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=headers, json=payload, timeout=60) as response:
                if response.status == 200:
                    data = await response.json()
                    ai_response = data['choices'][0]['message']['content']
                    context.append({"role": "assistant", "content": ai_response})
                    await db.save_context(user_id, context)
                    return ai_response
                else:
                    return f"Ошибка API ({response.status})"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def get_category_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 GPT", callback_data="cat_GPT Models")],
        [InlineKeyboardButton(text="🎭 Claude", callback_data="cat_Claude Models")],
        [InlineKeyboardButton(text="💎 Gemini", callback_data="cat_Gemini Models")],
        [InlineKeyboardButton(text="🔮 Qwen", callback_data="cat_Qwen Models")],
        [InlineKeyboardButton(text="🌟 Mistral", callback_data="cat_Mistral Models")],
        [InlineKeyboardButton(text="🧠 DeepSeek", callback_data="cat_DeepSeek Models")],
        [InlineKeyboardButton(text="🦙 Llama", callback_data="cat_Llama Models")],
        [InlineKeyboardButton(text="⚡ Grok", callback_data="cat_Grok Models")],
        [InlineKeyboardButton(text="🔧 Другие", callback_data="cat_Other Models")]
    ])

def get_models_keyboard(category: str):
    models = PREMIUM_MODELS.get(category, [])
    buttons = []
    for model in models:
        icon = "🆓" if model in FREE_MODELS else "⭐"
        if model in VISION_MODELS:
            icon += "👁"
        model_name = MODEL_NAMES.get(model, model)
        buttons.append([InlineKeyboardButton(text=f"{icon} {model_name}", callback_data=f"model_{model}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def is_premium(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    user = await db.get_user(user_id)
    return user['is_premium']

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    await db.get_user(user_id, username)
    text = f"👋 Привет, {message.from_user.first_name}!\n\n🤖 AI бот с 50+ моделями и анализом изображений\n\n🆓 <b>FREE:</b>\n   • {FREE_DAILY_LIMIT} сообщений/день\n   • Только GPT-4.1 Mini\n\n💎 <b>PREMIUM (199₽/месяц):</b>\n   • {PREMIUM_DAILY_LIMIT} сообщений/день\n   • ВСЕ 50+ моделей\n   • Vision (анализ фото)\n\n💬 Используйте меню ниже!"
    await message.answer(text, parse_mode="HTML", reply_markup=get_user_keyboard(user_id == ADMIN_ID))

@dp.message(Command("price"))
@dp.message(F.text == "💎 Тарифы")
async def cmd_price(message: Message):
    user_id = message.from_user.id
    text = f"💎 <b>ТАРИФЫ</b>\n\n🆓 <b>FREE:</b> {FREE_DAILY_LIMIT} сообщений/день, только GPT-4.1 Mini\n\n💎 <b>PREMIUM (199₽/мес):</b> {PREMIUM_DAILY_LIMIT} сообщений/день, ВСЕ 50+ моделей, Vision\n\n📞 <b>Купить Premium:</b>\n1. Скопируйте ваш ID: <code>{user_id}</code>\n2. Нажмите кнопку ниже\n3. Отправьте ID администратору"

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
        text = f"👑 Статус: <b>Администратор</b>\n🤖 Модель: <b>{model_name}</b>\n👁 Vision: {vision}\n📊 Сегодня: {used}"
    elif user['is_premium']:
        text = f"⭐ Статус: <b>Premium</b>\n🤖 Модель: <b>{model_name}</b>\n👁 Vision: {vision}\n📊 Осталось: <b>{limit-used}/{limit}</b>"
    else:
        text = f"🆓 Статус: <b>Free</b>\n🤖 Модель: <b>{model_name}</b>\n👁 Vision: ❌\n📊 Осталось: <b>{limit-used}/{limit}</b>"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("clear"))
@dp.message(F.text == "🗑 Очистить историю")
async def btn_clear(message: Message):
    await db.clear_context(message.from_user.id)
    await message.answer("✅ История очищена!")

@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь")
async def btn_help(message: Message):
    text = "📖 <b>ИНСТРУКЦИЯ</b>\n\n🤖 Выбрать модель - сменить AI\n📊 Мой статус - инфо\n🗑 Очистить историю - сброс\n💎 Тарифы - цены\n\n📸 Отправьте фото для анализа (Premium)\n\n💬 <b>Просто пишите!</b>"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "👑 Админ-панель")
async def btn_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👑 Админ-панель", reply_markup=get_admin_keyboard())

@dp.message(F.text == "➕ Выдать Premium")
async def btn_grant(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("➕ Отправьте ID или @username пользователя:\n\nПример:\n• 123456789\n• @username")
    await db.set_admin_state(ADMIN_ID, "waiting_grant", "1")

@dp.message(F.text == "➖ Отозвать Premium")
async def btn_revoke(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("➖ Отправьте ID или @username пользователя:\n\nПример:\n• 123456789\n• @username")
    await db.set_admin_state(ADMIN_ID, "waiting_revoke", "1")

@dp.message(F.text == "📈 Статистика пользователей")
async def btn_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    stats = await db.get_stats()
    await message.answer(f"📊 <b>СТАТИСТИКА</b>\n\n👥 Всего пользователей: <b>{stats['total']}</b>\n⭐ Premium: <b>{stats['premium']}</b>\n🆓 Free: <b>{stats['free']}</b>", parse_mode="HTML")

@dp.message(F.text == "◀️ Назад в меню")
async def btn_back(message: Message):
    await message.answer("◀️ Главное меню", reply_markup=get_user_keyboard(message.from_user.id == ADMIN_ID))

@dp.callback_query(F.data.startswith("cat_"))
async def process_category(callback: types.CallbackQuery):
    category = callback.data.replace("cat_", "")
    await callback.message.edit_text(f"Выберите модель:\n👁 = анализ изображений", reply_markup=get_models_keyboard(category))
    await callback.answer()

@dp.callback_query(F.data == "back_to_categories")
async def back_to_cat(callback: types.CallbackQuery):
    await callback.message.edit_text("⭐ Выберите категорию:", reply_markup=get_category_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "get_premium")
async def get_prem(callback: types.CallbackQuery):
    await callback.answer(f"💎 Ваш ID: {callback.from_user.id}\n\nСкопируйте и отправьте администратору", show_alert=True)

@dp.callback_query(F.data.startswith("model_"))
async def process_model(callback: types.CallbackQuery):
    model = callback.data.replace("model_", "")
    if model not in FREE_MODELS and not await is_premium(callback.from_user.id):
        await callback.answer("❌ Только Premium", show_alert=True)
        return

    await db.set_model(callback.from_user.id, model)
    await db.clear_context(callback.from_user.id)
    model_name = MODEL_NAMES.get(model, model)
    vision = " (Vision)" if model in VISION_MODELS else ""
    await callback.answer(f"✅ {model_name}")
    await callback.message.edit_text(f"✅ Выбрана: <b>{model_name}</b>{vision}", parse_mode="HTML")

@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    # Сохраняем фото
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    photo_bytes = await bot.download_file(file.file_path)
    photo_base64 = base64.b64encode(photo_bytes.read()).decode('utf-8')

    await state.update_data(photo_base64=photo_base64, user_id=message.from_user.id)

    # Если есть caption - быстрая генерация
    if message.caption:
        if not await is_premium(message.from_user.id):
            await message.answer("❌ Генерация изображений только для Premium")
            await state.clear()
            return

        can_send, remaining = await db.check_limit(message.from_user.id)
        if not can_send:
            await message.answer("❌ Лимит исчерпан. Попробуйте завтра!")
            await state.clear()
            return

        await message.answer("🎨 Генерирую изображение...")
        await bot.send_chat_action(message.chat.id, "upload_photo")
        await db.increment_messages(message.from_user.id)

        image_data = await generate_image_from_photo(message.caption, photo_base64)

        if image_data:
            photo_file = BufferedInputFile(image_data, filename="generated.png")
            await message.answer_photo(photo_file, caption=f"✨ Готово!\n\n📝 {message.caption}")
        else:
            await message.answer("❌ Ошибка генерации. Проверьте логи.")

        await state.clear()
    else:
        # Меню выбора
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Анализировать (Vision)", callback_data="photo_analyze")],
            [InlineKeyboardButton(text="🎨 Генерация по фото", callback_data="photo_generate")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="photo_cancel")]
        ])
        await message.answer("Что сделать с фото?", reply_markup=kb)

@dp.callback_query(F.data == "photo_analyze")
async def callback_photo_analyze(callback: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)

    if user['current_model'] not in VISION_MODELS:
        await callback.message.edit_text("❌ Эта модель не поддерживает Vision. Выберите модель с 👁")
        await state.clear()
        return

    if not await is_premium(callback.from_user.id):
        await callback.message.edit_text("❌ Vision только для Premium")
        await state.clear()
        return

    can_send, remaining = await db.check_limit(callback.from_user.id)
    if not can_send:
        await callback.message.edit_text("❌ Лимит исчерпан!")
        await state.clear()
        return

    await callback.message.edit_text("📝 Отправьте вопрос для анализа фото:")
    await state.update_data(action="analyze")
    await state.set_state(ImageGenState.waiting_for_prompt)
    await callback.answer()

@dp.callback_query(F.data == "photo_generate")
async def callback_photo_generate(callback: types.CallbackQuery, state: FSMContext):
    if not await is_premium(callback.from_user.id):
        await callback.message.edit_text("❌ Генерация только для Premium")
        await state.clear()
        return

    can_send, remaining = await db.check_limit(callback.from_user.id)
    if not can_send:
        await callback.message.edit_text("❌ Лимит исчерпан!")
        await state.clear()
        return

    await callback.message.edit_text("📝 Промт для генерации:\n\n💡 Примеры:\n• сделай в стиле аниме\n• преврати в 3D рендер\n• добавь неоновое освещение")
    await state.update_data(action="generate")
    await state.set_state(ImageGenState.waiting_for_prompt)
    await callback.answer()

@dp.callback_query(F.data == "photo_cancel")
async def callback_photo_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Отменено")
    await state.clear()
    await callback.answer()

@dp.message(ImageGenState.waiting_for_prompt)
async def process_photo_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get('action')
    photo_base64 = data.get('photo_base64')

    if action == "analyze":
        user = await db.get_user(message.from_user.id)
        await bot.send_chat_action(message.chat.id, "typing")
        await db.increment_messages(message.from_user.id)

        response = await get_ai_response(message.text, user['current_model'], message.from_user.id, photo_base64)
        model_name = MODEL_NAMES[user['current_model']]

        if len(response) > 4000:
            await message.answer(f"🤖 {model_name}:\n\n{response[:4000]}...")
            await message.answer(response[4000:])
        else:
            await message.answer(f"🤖 {model_name}:\n\n{response}")

    elif action == "generate":
        await message.answer("🎨 Генерирую...")
        await bot.send_chat_action(message.chat.id, "upload_photo")
        await db.increment_messages(message.from_user.id)

        image_data = await generate_image_from_photo(message.text, photo_base64)

        if image_data:
            photo_file = BufferedInputFile(image_data, filename="generated.png")
            await message.answer_photo(photo_file, caption=f"✨ Готово!\n\n📝 {message.text}")
        else:
            await message.answer("❌ Ошибка генерации. Проверьте логи.")

    await state.clear()


@dp.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        waiting_grant = await db.get_admin_state(ADMIN_ID, "waiting_grant")
        if waiting_grant:
            await db.clear_admin_state(ADMIN_ID, "waiting_grant")

            user_input = message.text.strip()

            if user_input.startswith('@'):
                username = user_input[1:]
                target_id = await db.get_user_by_username(username)

                if target_id:
                    await db.set_premium(target_id, True)
                    await message.answer(f"✅ Premium выдан пользователю @{username} (ID: <code>{target_id}</code>)", parse_mode="HTML", reply_markup=get_admin_keyboard())
                else:
                    await message.answer(f"❌ Пользователь @{username} не найден в базе\n\nПользователь должен:\n1. Запустить бота командой /start\n2. После этого попробуйте снова", reply_markup=get_admin_keyboard())
            else:
                try:
                    target_id = int(user_input)
                    await db.set_premium(target_id, True)
                    await message.answer(f"✅ Premium выдан пользователю: <code>{target_id}</code>", parse_mode="HTML", reply_markup=get_admin_keyboard())
                except ValueError:
                    await message.answer("❌ Неверный формат!\n\nОтправьте:\n• ID (цифры): 123456789\n• Username: @username", reply_markup=get_admin_keyboard())
            return

        waiting_revoke = await db.get_admin_state(ADMIN_ID, "waiting_revoke")
        if waiting_revoke:
            await db.clear_admin_state(ADMIN_ID, "waiting_revoke")

            user_input = message.text.strip()

            if user_input.startswith('@'):
                username = user_input[1:]
                target_id = await db.get_user_by_username(username)

                if target_id:
                    await db.set_premium(target_id, False)
                    await message.answer(f"✅ Premium отозван у пользователя @{username} (ID: <code>{target_id}</code>)", parse_mode="HTML", reply_markup=get_admin_keyboard())
                else:
                    await message.answer(f"❌ Пользователь @{username} не найден в базе", reply_markup=get_admin_keyboard())
            else:
                try:
                    target_id = int(user_input)
                    await db.set_premium(target_id, False)
                    await message.answer(f"✅ Premium отозван у пользователя: <code>{target_id}</code>", parse_mode="HTML", reply_markup=get_admin_keyboard())
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

    model_name = MODEL_NAMES[user['current_model']]
    if len(response) > 4000:
        await message.answer(f"🤖 <b>{model_name}</b> | Осталось: {remaining}", parse_mode="HTML")
        for i in range(0, len(response), 4000):
            await message.answer(response[i:i+4000])
    else:
        await message.answer(f"🤖 <b>{model_name}</b> | Осталось: {remaining}\n\n{response}", parse_mode="HTML")


async def generate_or_edit_image(prompt: str, image_b64: str = None) -> bytes:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {API_KEY_GEN}"
    }
    input_data = {"callback_url": None, "prompt": prompt}
    if image_b64:
        input_data["image"] = image_b64
    try:
        response = requests.post(GEN_API_URL, json=input_data, headers=headers, timeout=30)
        data = response.json()
        request_id = data["request_id"]
        for _ in range(24):
            await asyncio.sleep(5)
            poll_url = f"https://api.gen-api.ru/api/v1/requests/{request_id}"
            poll_resp = requests.get(poll_url, headers=headers, timeout=10)
            poll_data = poll_resp.json()
            if poll_data["status"] == "success":
                output_url = poll_data["output"].get("url")
                if output_url:
                    img_resp = requests.get(output_url)
                    return img_resp.content
            elif poll_data["status"] != "starting":
                break
        return None
    except:
        return None

@dp.message(Command("genimg"))
async def cmd_genimg(message: Message):
    if message.from_user.id != ADMIN_ID and not user["is_premium"]:  # Замени на твою логику premium
        await message.answer("Premium only!")
        return
    await message.answer("Промпт для генерации:")
    await ImageGenState.waiting_for_prompt.set()

@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    # Твоя логика premium и лимитов
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    photo_bytes = await bot.download_file(file.file_path)
    photo_b64 = base64.b64encode(photo_bytes.getvalue()).decode()
    await state.update_data(photo_b64=photo_b64)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Редактировать фото", callback_data="photo_edit")]
    ])
    await message.answer("Выбери:", reply_markup=kb)

@dp.message(ImageGenState.waiting_for_prompt)
async def gen_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_b64 = data.get("photo_b64")
    img_data = await generate_or_edit_image(message.text, photo_b64)
    if img_data:
        await message.answer_photo(BufferedInputFile(img_data))
    await state.clear()

async def main():
    await db.init_db()
    await set_bot_commands()
    print("Бот запущен!")
    print(f"Админ: {ADMIN_ID}")
    print(f"Free: {FREE_DAILY_LIMIT} сообщ/день")
    print(f"Premium: {PREMIUM_DAILY_LIMIT} сообщ/день")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
