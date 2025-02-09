from telegram import (Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton)
from telegram.ext import (Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext)

# TODO: нормальные типы музеев + нормальные города
# TODO: база данных музеев с метками "пушкинская карта" ...
# TODO: определение города по геометке
# TODO: разбивка по файлам функций
# TODO: \help бота + возможность на каждом этапе возвращаться назад

# Сделано:
# кнопки для выбора города, кнопки для выбора типа музея
# первичная ветка выбора (геолокация или текст)
# красота типа картинки бота и описания в тг

# Токен бота
TOKEN = '7397155961:AAE5Uagw13oQlR5UnFz8wkXVCyQkU8-loy4'

CITIES = ["Санкт-Петербург", "Самара", "Саратов", "Сан-Франциско", "Сан-Диего"] # примеры городов
MUSEUM_TYPES = ["Исторический", "Художественный", "Научный", "Технический", "Военный"] # примеры типов

async def start(update: Update, context: CallbackContext) -> None:     # выбор способа определения города: текстом или по геолокации
    keyboard = [
        [KeyboardButton("🏙 Ввести текстом")],
        [KeyboardButton("📍 Определить по геолокации", request_location=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Как вы хотите выбрать город?", reply_markup=reply_markup)

async def handle_city_selection(update: Update, context: CallbackContext) -> None:     # обрабатывает выбор метода ввода города
    text = update.message.text

    if text == "🏙 Ввести текстом":
        keyboard = [[city] for city in CITIES]  # кнопки с городами
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Выберите город:", reply_markup=reply_markup)
    
    elif text == "📍 Определить по геолокации":
        await update.message.reply_text("Отправьте вашу геолокацию, чтобы определить город.")
    
    elif text in CITIES:
        await handle_city_choice(update, context)  # передаем управление выбору города
    
    else:
        await update.message.reply_text("Пожалуйста, выберите один из предложенных вариантов.")

async def handle_location(update: Update, context: CallbackContext) -> None: # обрабатывает отправленную геопозицию
    user_location = update.message.location
    if not user_location:
        await update.message.reply_text("Не удалось получить геопозицию.")
        return

    city = "Санкт-Петербург"  # ЗАГЛУШКА: тут должен быть алгоритм определения города

    context.user_data["selected_city"] = city
    context.user_data["selected_museums"] = set()
    
    keyboard = [[InlineKeyboardButton(museum, callback_data=f"museum_{museum}")] for museum in MUSEUM_TYPES]
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
    
    await update.message.reply_text(f"Определен город: {city}. Теперь выберите тип музея:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_city_choice(update: Update, context: CallbackContext) -> None: # обрабатывает выбор города и предлагает выбрать тип музея
    city = update.message.text
    if city not in CITIES:
        await update.message.reply_text("Пожалуйста, выберите город из списка.")
        return

    context.user_data["selected_city"] = city
    context.user_data["selected_museums"] = set()

    keyboard = [[InlineKeyboardButton(museum, callback_data=f"museum_{museum}")] for museum in MUSEUM_TYPES]
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])

    await update.message.reply_text(f"Вы выбрали {city}. Теперь выберите тип музея:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_museum_choice(update: Update, context: CallbackContext) -> None: # позволяет выбрать несколько типов музеев и завершить выбор
    query = update.callback_query
    data = query.data

    if data == "done":
        selected_museums = list(context.user_data.get("selected_museums", []))
        if not selected_museums:
            await query.answer("Вы не выбрали ни одного музея!")
            return
        selected_city = context.user_data.get("selected_city", "Неизвестный город")
        await query.message.edit_text(f"Вы выбрали:\n🏙 Город: {selected_city}\n🏛 Музеи: {', '.join(selected_museums)}")
        return

    museum = data.split("_")[1]
    if museum in context.user_data["selected_museums"]:
        context.user_data["selected_museums"].remove(museum)
    else:
        context.user_data["selected_museums"].add(museum)

    # обновление inline-кнопок с галочками ✅
    keyboard = [[InlineKeyboardButton(f"{'✅ ' if m in context.user_data['selected_museums'] else ''}{m}", 
                                      callback_data=f"museum_{m}")] for m in MUSEUM_TYPES]
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])

    await query.answer()
    await query.message.edit_text("Выберите тип музея (можно несколько):", reply_markup=InlineKeyboardMarkup(keyboard))

def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_selection))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(CallbackQueryHandler(handle_museum_choice, pattern="^(museum_|done)"))

    app.run_polling()

if __name__ == '__main__':
    main()