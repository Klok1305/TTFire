import asyncio
import logging
import os
from datetime import datetime, timedelta
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import json

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение переменных окружения Railway
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_IDS = os.getenv('CHAT_IDS')  # JSON строка с массивом chat_id: ["123456789", "987654321", "111222333"]
PORT = int(os.getenv('PORT', 8000))

class OgonekBot:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.app = None
        # Состояние для каждого пользователя
        self.users_state = {}
        
        # Парсим chat_ids из переменной окружения
        try:
            self.chat_ids = json.loads(CHAT_IDS) if CHAT_IDS else []
            logger.info(f"Загружено {len(self.chat_ids)} chat IDs")
        except json.JSONDecodeError:
            logger.error("Ошибка парсинга CHAT_IDS. Используйте JSON формат: [\"123\", \"456\", \"789\"]")
            self.chat_ids = []
    
    def get_user_state(self, chat_id):
        """Получить состояние пользователя"""
        if str(chat_id) not in self.users_state:
            self.users_state[str(chat_id)] = {
                'ogonek_alive': True,
                'last_response_time': None,
                'reminders_paused_until': None
            }
        return self.users_state[str(chat_id)]
    
    def update_user_state(self, chat_id, **kwargs):
        """Обновить состояние пользователя"""
        state = self.get_user_state(chat_id)
        state.update(kwargs)
        self.users_state[str(chat_id)] = state
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        chat_id = update.effective_chat.id
        
        # Проверяем, авторизован ли пользователь
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text(
                "❌ Извините, у вас нет доступа к этому боту.\n"
                f"Ваш Chat ID: `{chat_id}`\n"
                "Обратитесь к администратору для добавления.",
                parse_mode='Markdown'
            )
            return
        
        # Сбрасываем состояние пользователя при перезапуске
        self.update_user_state(chat_id, 
            ogonek_alive=True,
            last_response_time=None,
            reminders_paused_until=None
        )
        
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
            "/revive - воскресить огонек\n"
            "/mychatid - узнать свой Chat ID"
        )
    
    async def mychatid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для получения Chat ID"""
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"🆔 **Ваш Chat ID:** `{chat_id}`\n\n"
            "Скопируйте этот ID и передайте администратору для добавления в бота.",
            parse_mode='Markdown'
        )
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stop"""
        chat_id = update.effective_chat.id
        
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        self.update_user_state(chat_id, 
            ogonek_alive=False,
            reminders_paused_until=None
        )
        await update.message.reply_text("⏹️ Напоминания остановлены вручную.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        chat_id = update.effective_chat.id
        
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        state = self.get_user_state(chat_id)
        
        status_text = "🔥 **Статус огонька:**\n"
        if state['ogonek_alive']:
            status_text += "✅ Огонек жив\n"
        else:
            status_text += "💀 Огонек мертв\n"
        
        if state['last_response_time']:
            status_text += f"🕐 Последний ответ: {state['last_response_time'].strftime('%d.%m.%Y %H:%M')}\n"
        else:
            status_text += "🕐 Ответов еще не было\n"
        
        # Информация о паузе напоминаний
        if state['reminders_paused_until']:
            status_text += f"⏸️ Напоминания приостановлены до: {state['reminders_paused_until'].strftime('%d.%m.%Y %H:%M')}\n"
        
        current_hour = datetime.now().hour
        if 0 <= current_hour < 8:
            status_text += "🌙 Сейчас ночное время (00:00-08:00), напоминания не отправляются"
        else:
            if state['ogonek_alive'] and not state['reminders_paused_until']:
                status_text += "☀️ Время активности (08:00-00:00), напоминания работают"
            elif state['reminders_paused_until']:
                status_text += "⏸️ Напоминания на паузе до следующего дня"
            else:
                status_text += "💀 Огонек мертв, напоминания остановлены"
        
        await update.message.reply_text(status_text)
    
    async def revive_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /revive - воскрешение огонька"""
        chat_id = update.effective_chat.id
        
        if str(chat_id) not in self.chat_ids:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        self.update_user_state(chat_id,
            ogonek_alive=True,
            reminders_paused_until=None
        )
        await update.message.reply_text("🔥 Огонек воскрешен! Напоминания возобновлены.")
        logger.info(f"Огонек воскрешен командой /revive для пользователя {chat_id}")
    
    async def send_ogonek_message(self):
        """Отправка сообщения с кнопками каждые 3 часа всем пользователям"""
        current_time = datetime.now()
        
        # Проверяем время - не отправляем с 00:00 до 8:00
        if 0 <= current_time.hour < 8:
            logger.info(f"Пропускаем отправку сообщения в {current_time.hour}:00 (ночное время)")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("Да 😢", callback_data='yes'),
                InlineKeyboardButton("Нет 🎉", callback_data='no'),
                InlineKeyboardButton("Еще нет 🤞", callback_data='not_yet')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение каждому пользователю
        for chat_id in self.chat_ids:
            try:
                state = self.get_user_state(chat_id)
                
                # Проверяем, не приостановлены ли напоминания для этого пользователя
                if state['reminders_paused_until'] and current_time < state['reminders_paused_until']:
                    logger.info(f"Напоминания приостановлены для {chat_id} до {state['reminders_paused_until']}")
                    continue
                
                # Если наступил новый день, сбрасываем паузу
                if state['reminders_paused_until'] and current_time >= state['reminders_paused_until']:
                    self.update_user_state(chat_id, reminders_paused_until=None)
                    logger.info(f"Пауза напоминаний сброшена для {chat_id}, новый день начался")
                
                # Проверяем статус огонька - если мертв, не отправляем
                if not state['ogonek_alive']:
                    logger.info(f"Огонек мертв для {chat_id}, сообщения не отправляются")
                    continue
                
                await self.app.bot.send_message(
                    chat_id=int(chat_id),
                    text="🔥 Я надеюсь ты не убила огонек",
                    reply_markup=reply_markup
                )
                logger.info(f"Сообщение отправлено пользователю {chat_id} в {datetime.now()}")
                
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения пользователю {chat_id}: {e}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        chat_id = query.message.chat_id
        
        # Проверяем доступ
        if str(chat_id) not in self.chat_ids:
            await query.edit_message_text("❌ У вас нет доступа к этому боту.")
            return
        
        # Обновляем время последнего ответа
        self.update_user_state(chat_id, last_response_time=datetime.now())
        
        # Случайные эмодзи для ответа "еще нет"
        random_emojis = ["🌟", "✨", "💫", "🎈", "🎊", "🎉", "🌈", "🦄", "🎪", "🎭", "🎨", "🎯"]
        
        if query.data == 'yes':
            # Огонек умер - останавливаем напоминания навсегда
            self.update_user_state(chat_id,
                ogonek_alive=False,
                reminders_paused_until=None
            )
            response = "😭 Какая короткая была у него жизнь... Покойся с миром, маленький огонек 🕯️💔\n\n⏹️ Напоминания остановлены навсегда."
            logger.info(f"Огонек умер для пользователя {chat_id}, напоминания остановлены навсегда")
            
        elif query.data == 'no':
            # Огонек жив и здоров - приостанавливаем напоминания до следующего дня
            current_time = datetime.now()
            next_day_8am = (current_time + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
            
            self.update_user_state(chat_id,
                ogonek_alive=True,
                reminders_paused_until=next_day_8am
            )
            
            response = f"🎉 УРА! Огонек живет и здравствует! 🔥✨ Отличная работа!\n\n⏸️ Напоминания приостановлены до завтра в 8:00 ({next_day_8am.strftime('%d.%m.%Y %H:%M')})"
            logger.info(f"Огонек жив для пользователя {chat_id}, напоминания приостановлены до {next_day_8am}")
            
        elif query.data == 'not_yet':
            # Огонек еще жив, но в опасности - напоминания продолжаются
            self.update_user_state(chat_id, ogonek_alive=True)
            emoji_selection = random.sample(random_emojis, 3)
            emoji_string = " ".join(emoji_selection)
            response = f"🙏 Не убей пожалуйста {emoji_string}\n\n⏰ Напоминания продолжаются каждые 3 часа"
            logger.info(f"Огонек еще жив для пользователя {chat_id}, напоминания продолжаются")
        
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
        
        # Отправляем первое сообщение сразу (только если не ночь)
        current_hour = datetime.now().hour
        if not (0 <= current_hour < 8):
            await self.send_ogonek_message()
        
        logger.info("Планировщик настроен. Сообщения будут отправляться каждые 3 часа.")
    
    async def run(self):
        """Запуск бота"""
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN не установлен в переменных окружения!")
            return
        
        if not self.chat_ids:
            logger.error("CHAT_IDS не установлены или некорректны!")
            return
        
        # Создание приложения
        self.app = Application.builder().token(BOT_TOKEN).build()
        
        # Добавление обработчиков
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("revive", self.revive_command))
        self.app.add_handler(CommandHandler("mychatid", self.mychatid_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Запуск планировщика
        self.scheduler.start()
        
        # Настройка автоматических сообщений
        await self.setup_scheduler()
        
        # Запуск бота с webhook для Railway
        logger.info(f"Бот запущен для {len(self.chat_ids)} пользователей!")
        
        # Railway предоставляет внешний URL автоматически
        await self.app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost')}/{BOT_TOKEN}",
            url_path=BOT_TOKEN
        )

async def main():
    """Главная функция"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен в переменных окружения Railway!")
        logger.error("Установите переменную BOT_TOKEN в настройках Railway")
        return
    
    if not CHAT_IDS:
        logger.error("❌ CHAT_IDS не установлены в переменных окружения Railway!")
        logger.error("Установите переменную CHAT_IDS в формате JSON: [\"123456789\", \"987654321\"]")
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

# requirements.txt содержимое:
# python-telegram-bot==20.7
# apscheduler==3.10.4
