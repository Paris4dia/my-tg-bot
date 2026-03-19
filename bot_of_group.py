import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# --- НАСТРОЙКИ ---
TOKEN = "8721873898:AAG-fhdiyMHKuanHcsLPEGpp65eFNXliNZM"
ADMIN_ID = 701893103 

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ SQLite ---
def init_db():
    try:
        conn = sqlite3.connect('bot_data.db', timeout=10)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (user_id INTEGER PRIMARY KEY, is_anon INTEGER DEFAULT 1)''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка инициализации БД: {e}")

def get_anon(user_id):
    try:
        conn = sqlite3.connect('bot_data.db', timeout=10)
        cursor = conn.cursor()
        cursor.execute('SELECT is_anon FROM users WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 1
    except Exception as e:
        logging.error(f"Ошибка чтения БД: {e}")
        return 1

def toggle_anon_db(user_id):
    try:
        current = get_anon(user_id)
        new_val = 0 if current == 1 else 1
        conn = sqlite3.connect('bot_data.db', timeout=10)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO users (user_id, is_anon) VALUES (?, ?)', (user_id, new_val))
        conn.commit()
        conn.close()
        return new_val
    except Exception as e:
        logging.error(f"Ошибка записи в БД: {e}")
        return 1

# --- СОСТОЯНИЯ ---
class Feedback(StatesGroup):
    waiting_for_text = State()
    waiting_for_reply = State()

# --- КЛАВИАТУРЫ ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    # Текст кнопок теперь совпадает с логикой обработки
    builder.row(types.KeyboardButton(text="📥 Оставить жалобу"), types.KeyboardButton(text="💡 Оставить предложение"))
    builder.row(types.KeyboardButton(text="⚙️ Настройки анонимности"))
    return builder.as_markup(resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать, дорогой друг! Выберите действие ниже и не переживайте (наши админы не голодны):", reply_markup=main_menu())

@dp.message(F.text == "⚙️ Настройки анонимности")
async def settings(message: types.Message):
    is_anon = get_anon(message.from_user.id)
    status = "✅ ВКЛ (Анонимно)" if is_anon else "❌ ВЫКЛ (Видно ник)"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Переключить статус", callback_data="toggle_anon"))
    await message.answer(f"Твой статус: {status}\n\nЕсли статус долго не меняется, подожди пару секунд — сервер прогревается.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "toggle_anon")
async def toggle_callback(callback: types.CallbackQuery):
    new_status_val = toggle_anon_db(callback.from_user.id)
    status_text = "✅ ВКЛ (Анонимно)" if new_status_val else "❌ ВЫКЛ (Видно ник)"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Переключить статус", callback_data="toggle_anon"))
    
    try:
        await callback.message.edit_text(f"Твой статус изменен!\nТеперь: {status_text}", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Ошибка обновления сообщения: {e}")
    await callback.answer()

# Универсальный обработчик для жалоб и предложений (игнорирует регистр букв)
@dp.message(lambda message: message.text and ("жалоб" in message.text.lower() or "предложен" in message.text.lower()))
async def start_fb(message: types.Message, state: FSMContext):
    type_fb = "жалобу" if "жалоб" in message.text.lower() else "предложение"
    await state.update_data(fb_type=type_fb)
    await state.set_state(Feedback.waiting_for_text)
    await message.answer(f"Напишите свою {type_fb}:")

@dp.message(Feedback.waiting_for_text)
async def get_fb(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_anon = get_anon(message.from_user.id)
    
    author = "Аноним" if is_anon else f"@{message.from_user.username} (ID: {message.from_user.id})"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Ответить 💬", callback_data=f"reply_{message.from_user.id}"))

    await bot.send_message(
        ADMIN_ID, 
        f"📩 **Новое {data['fb_type'].upper()}**\nОт: {author}\n\nТекст: {message.text}",
        reply_markup=builder.as_markup()
    )
    await message.answer("Отправлено! Админ скоро ответит. Хотя лучше запаситесь терпением.")
    await state.clear()

# --- ОТВЕТ АДМИНА ---

@dp.callback_query(F.data.startswith("reply_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.data.split("_")[1]
    await state.update_data(reply_to=user_id)
    await state.set_state(Feedback.waiting_for_reply)
    await callback.message.answer("Введите ответ пользователю:")
    await callback.answer()

@dp.message(Feedback.waiting_for_reply, F.from_user.id == ADMIN_ID)
async def admin_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        await bot.send_message(data['reply_to'], f"✉️ **Ответ администрации:**\n\n{message.text}")
        await message.answer("Ответ отправлен! ✅")
    except Exception as e:
        await message.answer(f"Ошибка при отправке: {e}")
    await state.clear()

async def main():
    init_db() 
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")