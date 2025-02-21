from telegram import (Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, InlineQueryResultArticle, InputTextMessageContent)
from telegram.ext import (Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext, InlineQueryHandler,)
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# TODO: нормальные типы музеев + нормальные города
# TODO: база данных музеев с метками "пушкинская карта" ...
# TODO: разбивка по файлам функций (под вопросом)

# Сделано:
# первичная ветка выбора (геолокация или текст)
# inline-подсказки для выбора города
# кнопки для выбора типа музея
# определение города по геометке
# возможность на каждом этапе возвращаться назад
# красота типа картинки бота и описания в тг
# \help бота

# Токен бота
TOKEN = '7397155961:AAE5Uagw13oQlR5UnFz8wkXVCyQkU8-loy4'

CITIES = ["Санкт-Петербург", "Самара", "Саратов", "Сан-Франциско", "Сан-Диего"] # примеры городов
MUSEUM_TYPES = ["Исторический", "Художественный", "Научный", "Технический", "Военный"] # примеры типов

async def start(update: Update, context: CallbackContext) -> None: # выбор способа определения города
    context.user_data['state']='start'
    keyboard = [
        [KeyboardButton("🏙 Ввести текстом")],
        [KeyboardButton("📍 Определить по геолокации", request_location=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    if update.message:
        await update.message.reply_text("Как вы хотите выбрать город?", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Как вы хотите выбрать город?", reply_markup=reply_markup)


async def inline_query_handler(update: Update, context) -> None:
    query = update.inline_query.query.strip().lower()  
    filtered_cities = [
        city for city in CITIES if city.lower().startswith(query)
    ]
    if not filtered_cities:
        await update.inline_query.answer([])  
        return
    results = [
        InlineQueryResultArticle(
            id=str(i),
            title=city,  # Название города
            input_message_content=InputTextMessageContent(city)  # Сабмит значения при выборе
        ) for i, city in enumerate(filtered_cities)
    ]
    await update.inline_query.answer(results)  # Ответ пользователю

async def handle_city_selection(update: Update, context: CallbackContext) -> None:     # обрабатывает выбор метода ввода города
    
    text = update.message.text
    
    if text == "🏙 Ввести текстом":
         context.user_data['state'] = 'text_input'
         await update.message.reply_text("Привет! Используйте inline-режим для нахождения города. Пример: @museGuide_bot [название города]",
                                         reply_markup=ReplyKeyboardRemove())
    
    elif text == "📍 Определить по геолокации":
        context.user_data['state'] = 'geolocation'
        await update.message.reply_text("Отправьте вашу геолокацию, чтобы определить город.",
                                        reply_markup=ReplyKeyboardRemove())
    
    elif context.user_data.get('state')=='text_input':
      if text in CITIES:
        await handle_city_choice(update, context)  
    
    else:
       await update.message.reply_text("Пожалуйста, выберите один из предложенных вариантов.")



async def handle_location(update: Update, context: CallbackContext) -> None: # обрабатывает отправленную геопозицию
    user_location = update.message.location
    if not user_location:
        await update.message.reply_text("Не удалось получить геопозицию.")
        return

    # Извлекаем широту и долготу
    latitude = user_location.latitude
    longitude = user_location.longitude

    # Используем Nominatim для определения города
    geolocator = Nominatim(user_agent="telegram_bot")
    try:
        # Получаем адрес по координатам
        location = geolocator.reverse((latitude, longitude), exactly_one=True)
        address = location.raw.get("address", {})

        # Извлекаем город из адреса
        city = address.get("city") or address.get("town") or address.get("village")
        if not city:
            await update.message.reply_text("Не удалось определить город.")
            return
    except GeocoderTimedOut:
        await update.message.reply_text("Ошибка: время ожидания геокодера истекло.")
        return
    except Exception as e:
        await update.message.reply_text(f"Ошибка при определении города: {e}")
        return
    if city not in CITIES:
        await update.message.reply_text("К сожалению, в вашем городе нет музеев.")
        await start(update, context)  # Возвращаем пользователя в начало
        return

    context.user_data["selected_city"] = city
    context.user_data["selected_museums"] = set()
    
    keyboard = [[InlineKeyboardButton(museum, callback_data=f"museum_{museum}")] for museum in MUSEUM_TYPES]
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])  # Кнопка "Назад"
    
    await update.message.reply_text(f"Определен город: {city}. Теперь выберите тип музея:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_city_choice(update: Update, context: CallbackContext) -> None: # обрабатывает выбор города и предлагает выбрать тип музея
 
    city = update.message.text
    if context.user_data.get('state')=='text_input':

       if city not in CITIES:
         await update.message.reply_text("Пожалуйста, выберите город из списка.")
         return

       context.user_data["selected_city"] = city
       context.user_data["selected_museums"] = set()

       keyboard = [[InlineKeyboardButton(museum, callback_data=f"museum_{museum}")] for museum in MUSEUM_TYPES]
       keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
       keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])  # Кнопка "Назад"

       await update.message.reply_text(f"Вы выбрали {city}. Теперь выберите тип музея:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_museum_choice(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data
    if "selected_museums" not in context.user_data:
        context.user_data["selected_museums"] = set()

    if data == "done":
        selected_museums = list(context.user_data.get("selected_museums", []))
        if not selected_museums:
            await query.answer("Вы не выбрали ни одного музея!")
            return
        selected_city = context.user_data.get("selected_city", "Неизвестный город")
        await query.message.edit_text(f"Вы выбрали:\n🏙 Город: {selected_city}\n🏛 Музеи: {', '.join(selected_museums)}")
        return

    elif data == "back":
        await query.message.delete()
        await start(update, context)  # Возвращаемся в начало
        return

    museum = data.split("_")[1]
    if museum in context.user_data["selected_museums"]:
        context.user_data["selected_museums"].remove(museum)
    else:
        context.user_data["selected_museums"].add(museum)

    keyboard = [[InlineKeyboardButton(f"{'✅ ' if m in context.user_data['selected_museums'] else ''}{m}", callback_data=f"museum_{m}")] for m in MUSEUM_TYPES]
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])

    await query.answer()
    await query.message.edit_text("Выберите тип музея (можно несколько):", reply_markup=InlineKeyboardMarkup(keyboard))


async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "🤖 *Как пользоваться ботом?*\n\n"
        "1️⃣ Используйте команду /start, чтобы начать.\n"
        "2️⃣ Выберите город: вручную или отправьте геолокацию.\n"
        "3️⃣ Выберите тип музея (можно несколько).\n"
        "4️⃣ Нажмите ✅ Готово, чтобы подтвердить выбор.\n\n"
        "🔙 Если хотите вернуться назад на любом этапе, используйте кнопку *Назад*.\n"
        "🆘 Если возникли вопросы, напишите администратору."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_selection))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(CallbackQueryHandler(handle_museum_choice, pattern="^(museum_|done|back)"))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(InlineQueryHandler(inline_query_handler))  

    app.run_polling()

if __name__ == '__main__':
    main()