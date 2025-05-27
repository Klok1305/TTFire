import os
import asyncio
import logging
from datetime import datetime, timedelta
import random
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Чтение и проверка BOT_TOKEN
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен в переменных окружения!")
    exit(1)

# Чтение и проверка CHAT_IDS из окружения (JSON-массив)
raw_chat_ids = os.getenv('CHAT_IDS', '[]')
try:
    parsed = json.loads(raw_chat_ids)
    if not isinstance(parsed, list):
        raise ValueError
    CHAT_IDS = [str(x) for x in parsed]
    logger.info(f"Загружено {len(CHAT_IDS)} Chat ID(s)")
except Exception:
    logger.error("❌ Ошибка парсинга CHAT_IDS. Используйте JSON-массив")
    exit(1)

# Порт для webhook
PORT = int(os.getenv('PORT', 8000))

class OgonekBot:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.app = None
        self.users_state = {}
        self.chat_ids = CHAT_IDS

    def get_user_state(self, chat_id):
        key = str(chat_id)
        if key not in self.users_state:
            self.users_state[key] = {
                'ogonek_alive': True,
                'last_response_time': None,
                'reminders_paused_until': None
            }
        return self.users_state[key]

    def update_user_state(self, chat_id, **kwargs):
        state = self.get_user_state(chat_id)
        state.update(kwargs)
        self.users_state[str(chat_id)] = state

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text(
                f"❌ У вас нет доступа к этому боту.\nВаш Chat ID: `{chat_id}`", parse_mode='Markdown'
            )
            return

        self.update_user_state(chat_id, ogonek_alive=True, last_response_time=None, reminders_paused_until=None)
        await update.message.reply_text(
            "🔥 Бот запущен!\n"
            "⏰ Расписание: 9:00–00:59 (каждые 3 часа)\n"
            "🌙 Ночь: 1:00–8:59 (тишина)\n\n"
            "📋 Ответы на вопросы:\n"
            "• 'Да' → огонек умер, напоминания навсегда остановлены\n"
            "• 'Нет' → огонек жив, напоминания до завтра в 9:00\n"
            "• 'Еще нет' → огонек в опасности, напоминания продолжаются каждые 3 часа\n\n"
            "🛠️ Команды:\n"
            "/start — перезапуск бота\n"
            "/stop — остановить напоминания\n"
            "/status — проверить статус\n"
            "/revive — воскресить огонек\n"
            "/mychatid — узнать свой Chat ID",
            parse_mode='Markdown'
        )

    async def mychatid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"🆔 Ваш Chat ID: `{chat_id}`", parse_mode='Markdown'
        )

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        self.update_user_state(chat_id, ogonek_alive=False, reminders_paused_until=None)
        await update.message.reply_text("⏹️ Напоминания остановлены вручную.")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        state = self.get_user_state(chat_id)
        hour = datetime.now().hour

        text = "🔥 **Статус огонька:**\n"
        text += "✅ Огонек жив\n" if state['ogonek_alive'] else "💀 Огонек мертв\n"
        if state['last_response_time']:
            text += f"🕐 Последний ответ: {state['last_response_time'].strftime('%d.%m.%Y %H:%M')}\n"
        else:
            text += "🕐 Ответов еще не было\n"
        if state['reminders_paused_until']:
            text += f"⏸️ Приостановлен до: {state['reminders_paused_until'].strftime('%d.%m.%Y %H:%M')}\n"

        if 1 <= hour < 9:
            text += "🌙 Сейчас тишина (1:00–8:59), напоминания не отправляются"
        else:
            if state['ogonek_alive'] and not state['reminders_paused_until']:
                text += "☀️ Время активности, напоминания работают"
            elif state['reminders_paused_until']:
                text += "⏸️ Напоминания на паузе до следующего дня"
            else:
                text += "💀 Огонек мертв, напоминания остановлены"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def revive_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        self.update_user_state(chat_id, ogonek_alive=True, reminders_paused_until=None)
        await update.message.reply_text("🔥 Огонек воскрешен! Напоминания возобновлены.")

    async def send_ogonek_message(self):
        now = datetime.now()
        hour = now.hour
        if 1 <= hour < 9:
            logger.info(f"Пропускаем рассылку в {hour}:00 (тишина)")
            return

        keyboard = [[
            InlineKeyboardButton("Сдох 😢", callback_data='yes'),
            InlineKeyboardButton("Живет 🎉", callback_data='no'),
            InlineKeyboardButton("Продлю 🤞", callback_data='not_yet')
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        for cid in self.chat_ids:
            try:
                state = self.get_user_state(cid)
                if state['reminders_paused_until'] and now < state['reminders_paused_until']:
                    continue
                if state['reminders_paused_until'] and now >= state['reminders_paused_until']:
                    self.update_user_state(cid, reminders_paused_until=None)
                if not state['ogonek_alive']:
                    continue
                await self.app.bot.send_message(chat_id=int(cid), text="🔥 Я надеюсь огонек жив?", reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения {cid}: {e}")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        cid = query.message.chat_id
        if str(cid) not in self.chat_ids:
            await query.edit_message_text("❌ У вас нет доступа к этому боту.")
            return
        # Обновляем время последнего ответа
        self.update_user_state(cid, last_response_time=datetime.now())
        now = datetime.now()
        emojis = random.sample(["🌟","✨","💫","🎈","🎊","🎉","🌈","🦄","🎪","🎭","🎨","🎯"], 3)
        if query.data == 'yes':
            self.update_user_state(cid, ogonek_alive=False, reminders_paused_until=None)
            response = "😭 Какая короткая была у него жизнь... Покойся с миром, маленький огонек 🕯️💔\n\n⏹️ Напоминания остановлены навсегда."
        elif query.data == 'no':
            next_day_9am = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            self.update_user_state(cid, ogonek_alive=True, reminders_paused_until=next_day_9am)
            response = f"🎉 УРА! Огонек жив и здоров! Напоминания приостановлены до {next_day_9am.strftime('%d.%m.%Y %H:%M')}"
        elif query.data == 'not_yet':
            self.update_user_state(cid, ogonek_alive=True)
            emoji_string = " ".join(emojis)
            response = f"🙏 Еще не убил(а) {emoji_string}\n\n⏰ Напоминания продолжаются каждые 3 часа."
        else:
            response = "❓ Непонятный ответ."
        original = query.message.text or ""
        await query.edit_message_text(f"{original}\n\n💬 {response}")

    async def setup_scheduler(self):
        self.scheduler.add_job(self.send_ogonek_message, trigger=IntervalTrigger(hours=3), id='ogonek_reminder')
        now = datetime.now()
        if not (1 <= now.hour < 9):
            await self.send_ogonek_message()

    def run(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("mychatid", self.mychatid_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("revive", self.revive_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        self.scheduler.start()
        asyncio.get_event_loop().run_until_complete(self.setup_scheduler())
        logger.info(f"Бот запущен для {len(self.chat_ids)} пользователей!")
        self.app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost')}/{BOT_TOKEN}",
            url_path=BOT_TOKEN
        )


def main():
    bot = OgonekBot()
    bot.run()


if __name__ == '__main__':
    main()

# requirements.txt:
# python-telegram-bot[webhooks]==20.7
# apscheduler==3.10.4
