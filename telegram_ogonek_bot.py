import asyncio
import logging
from datetime import datetime, timedelta
import random
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

# Вставьте сюда токен вашего бота
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"

# ID чата, куда отправлять сообщения (получите его через @userinfobot)
CHAT_ID = "ВАШ_CHAT_ID"

class OgonekBot:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.app = None
        self.ogonek_alive = True  # Статус огонька (True - жив, False - мертв)
        self.last_response_time = None  # Время последнего ответа
        self.reminders_paused_until = None  # Время до которого напоминания приостановлены
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        # Сбрасываем статус огонька при перезапуске
        self.ogonek_alive = True
        self.last_response_time = None
        self.reminders_paused_until = None
        
        await update.message.reply_text(
            "🔥 Бот запущен! Логика работы:\n\n"
            "⏰ **Расписание:** 8:00-00:00 (каждые 3 часа)\n"
            "🌙 **Ночь:** 00:00-8:00 (тишина)\n\n"
            "📋 **Ответы на вопросы:**\n"
            "• **'Да'** → огонек умер, напоминания навсегда остановлены\n"
            "• **'Нет'** → огонек жив, напоминания до завтра в 8:00\n"  
            "• **'Еще нет'** → огонек в опасности, напоминания продолжаются каждые 3 часа\n\n"
            "🛠️ **Команды:**\n"
            "/start - перезапуск бота\n"
            "/stop - остановить напоминания\n"
            "/status - проверить статус\n"
            "/revive - воскресить огонек"
        )
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stop"""
        self.ogonek_alive = False
        self.reminders_paused_until = None
        await update.message.reply_text("⏹️ Напоминания остановлены вручную.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        status_text = "🔥 **Статус огонька:**\n"
        if self.ogonek_alive:
            status_text += "✅ Огонек жив\n"
        else:
            status_text += "💀 Огонек мертв\n"
        
        if self.last_response_time:
            status_text += f"🕐 Последний ответ: {self.last_response_time.strftime('%d.%m.%Y %H:%M')}\n"
        else:
            status_text += "🕐 Ответов еще не было\n"
        
        # Информация о паузе напоминаний
        if self.reminders_paused_until:
            status_text += f"⏸️ Напоминания приостановлены до: {self.reminders_paused_until.strftime('%d.%m.%Y %H:%M')}\n"
        
        current_hour = datetime.now().hour
        if 0 <= current_hour < 8:
            status_text += "🌙 Сейчас ночное время (00:00-08:00), напоминания не отправляются"
        else:
            if self.ogonek_alive and not self.reminders_paused_until:
                status_text += "☀️ Время активности (08:00-00:00), напоминания работают"
            elif self.reminders_paused_until:
                status_text += "⏸️ Напоминания на паузе до следующего дня"
            else:
                status_text += "💀 Огонек мертв, напоминания остановлены"
        
        await update.message.reply_text(status_text)
    
    async def revive_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /revive - воскрешение огонька"""
        self.ogonek_alive = True
        self.reminders_paused_until = None
        await update.message.reply_text("🔥 Огонек воскрешен! Напоминания возобновлены.")
        logger.info("Огонек воскрешен командой /revive")
    
    async def send_ogonek_message(self):
        """Отправка сообщения с кнопками каждые 3 часа"""
        current_time = datetime.now()
        
        # Проверяем время - не отправляем с 00:00 до 8:00
        if 0 <= current_time.hour < 8:
            logger.info(f"Пропускаем отправку сообщения в {current_time.hour}:00 (ночное время)")
            return
        
        # Проверяем, не приостановлены ли напоминания
        if self.reminders_paused_until and current_time < self.reminders_paused_until:
            logger.info(f"Напоминания приостановлены до {self.reminders_paused_until}")
            return
        
        # Если наступил новый день, сбрасываем паузу
        if self.reminders_paused_until and current_time >= self.reminders_paused_until:
            self.reminders_paused_until = None
            logger.info("Пауза напоминаний сброшена, новый день начался")
        
        # Проверяем статус огонька - если мертв, не отправляем
        if not self.ogonek_alive:
            logger.info("Огонек мертв, сообщения не отправляются")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("Да 😢", callback_data='yes'),
                InlineKeyboardButton("Нет 🎉", callback_data='no'),
                InlineKeyboardButton("Еще нет 🤞", callback_data='not_yet')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await self.app.bot.send_message(
                chat_id=CHAT_ID,
                text="🔥 Я надеюсь ты не убила огонек",
                reply_markup=reply_markup
            )
            logger.info(f"Сообщение отправлено в {datetime.now()}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        # Обновляем время последнего ответа
        self.last_response_time = datetime.now()
        
        # Случайные эмодзи для ответа "еще нет"
        random_emojis = ["🌟", "✨", "💫", "🎈", "🎊", "🎉", "🌈", "🦄", "🎪", "🎭", "🎨", "🎯"]
        
        if query.data == 'yes':
            # Огонек умер - останавливаем напоминания навсегда
            self.ogonek_alive = False
            self.reminders_paused_until = None
            response = "😭 Какая короткая была у него жизнь... Покойся с миром, маленький огонек 🕯️💔\n\n⏹️ Напоминания остановлены навсегда."
            logger.info("Огонек умер, напоминания остановлены навсегда")
            
        elif query.data == 'no':
            # Огонек жив и здоров - приостанавливаем напоминания до следующего дня
            self.ogonek_alive = True
            
            # Определяем время до следующего дня в 8:00
            current_time = datetime.now()
            next_day_8am = (current_time + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
            self.reminders_paused_until = next_day_8am
            
            response = f"🎉 УРА! Огонек живет и здравствует! 🔥✨ Отличная работа!\n\n⏸️ Напоминания приостановлены до завтра в 8:00 ({next_day_8am.strftime('%d.%m.%Y %H:%M')})"
            logger.info(f"Огонек жив, напоминания приостановлены до {next_day_8am}")
            
        elif query.data == 'not_yet':
            # Огонек еще жив, но в опасности - напоминания продолжаются
            self.ogonek_alive = True
            emoji_selection = random.sample(random_emojis, 3)
            emoji_string = " ".join(emoji_selection)
            response = f"🙏 Не убей пожалуйста {emoji_string}\n\n⏰ Напоминания продолжаются каждые 3 часа"
            logger.info("Огонек еще жив, напоминания продолжаются")
        
        # Редактируем исходное сообщение, добавляя ответ
        original_text = query.message.text
        new_text = f"{original_text}\n\n💬 {response}"
        
        try:
            await query.edit_message_text(text=new_text)
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
    
    async def setup_scheduler(self):
        """Настройка планировщика для отправки сообщений каждые 3 часа"""
        # Добавляем задачу, которая будет выполняться каждые 3 часа
        self.scheduler.add_job(
            self.send_ogonek_message,
            trigger=IntervalTrigger(hours=3),
            id='ogonek_reminder',
            name='Ogonek Reminder',
            replace_existing=True
        )
        
        # Отправляем первое сообщение сразу
        await self.send_ogonek_message()
        
        logger.info("Планировщик настроен. Сообщения будут отправляться каждые 3 часа.")
    
    async def run(self):
        """Запуск бота"""
        # Создание приложения
        self.app = Application.builder().token(BOT_TOKEN).build()
        
        # Добавление обработчиков
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("revive", self.revive_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Запуск планировщика
        self.scheduler.start()
        
        # Настройка автоматических сообщений
        await self.setup_scheduler()
        
        # Запуск бота
        logger.info("Бот запущен!")
        await self.app.run_polling(drop_pending_updates=True)

async def main():
    """Главная функция"""
    if BOT_TOKEN == "ВАШ_ТОКЕН_БОТА" or CHAT_ID == "ВАШ_CHAT_ID":
        print("❌ Пожалуйста, укажите BOT_TOKEN и CHAT_ID в коде!")
        print("1. Получите токен бота у @BotFather")
        print("2. Получите CHAT_ID через @userinfobot")
        return
    
    bot = OgonekBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())

# Требования для установки (requirements.txt):
# python-telegram-bot==20.7
# apscheduler==3.10.4