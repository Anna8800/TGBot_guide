from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Токен вашего бота
TOKEN = '7397155961:AAE5Uagw13oQlR5UnFz8wkXVCyQkU8-loy4'

# Обработчик команды /start
async def start(update: Update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

# Обработчик текстовых сообщений
async def echo(update: Update, context):
    text = 'ECHO: ' + update.message.text
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

def main() -> None:
    # Создаем экземпляр Application
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики команд
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    # Регистрируем обработчик текстовых сообщений
    echo_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, echo)
    application.add_handler(echo_handler)

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()