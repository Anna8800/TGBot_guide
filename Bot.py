from turtle import update
import mysql.connector
from mysql.connector import Error
from telegram import (
    Update, 
    KeyboardButton, 
    ReplyKeyboardMarkup, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    InputTextMessageContent, 
    InlineQueryResultArticle
)
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, InlineQueryHandler, CallbackContext

TOKEN = '7963749541:AAFCetUySc3pjEQWJo90je0VdRPoDBhih5k'

CITIES = ["Москва"]  # Примеры городов
MUSEUM_TYPES = []  # Музеи будут загружаться из БД

# Подключение к базе данных
def create_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',  # Замените на ваш хост
            database='museum',  # Замените на ваше имя базы данных
            user='root',  # Замените на ваше имя пользователя
            password='password'  # Замените на ваш пароль
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Ошибка подключения к MySQL: {e}")
    return None

# Функция для получения типов музеев
def fetch_museum_types_from_db():
    connection = create_connection()
    types = []
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("SELECT type_name FROM museum_types")
            results = cursor.fetchall()
            types = [row[0] for row in results]
    except Error as e:
        print(f"Ошибка при работе с MySQL: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    return types

# Запуск бота
async def start(update: Update, context: CallbackContext) -> None:
    context.user_data['state'] = 'start'
    keyboard = [
        [KeyboardButton("🏙 Ввести текстом")],
        [KeyboardButton("📍 Определить по геолокации", request_location=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Как вы хотите выбрать город?", reply_markup=reply_markup)

# Обработка инлайн-запросов на выбор города
async def inline_query_handler(update: Update, context) -> None:
    query = update.inline_query.query.strip().lower()
    print("Доступные города:", CITIES)
    filtered_cities = [city for city in CITIES if city.lower().startswith(query)]
    if not filtered_cities:
        await update.inline_query.answer([])
        return
    results = [
        InlineQueryResultArticle(
            id=str(i),
            title=city,
            input_message_content=InputTextMessageContent(city)
        ) for i, city in enumerate(filtered_cities)
    ]
    await update.inline_query.answer(results)

# Обработка выбора способа ввода города
async def handle_city_selection(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    
    if text == "🏙 Ввести текстом":
        context.user_data['state'] = 'text_input'
        await update.message.reply_text("Привет! Используйте inline-режим для нахождения города. Пример: @Chancefm_bot [название города]")
    
    elif text == "📍 Определить по геолокации":

        context.user_data['state'] = 'geolocation'
        await update.message.reply_text("Отправьте вашу геолокацию, чтобы определить город.")
    
    elif context.user_data.get('state') == 'text_input':
        if text in CITIES:
            await handle_city_choice(update, context)  
    
    else:
        await update.message.reply_text("Пожалуйста, выберите один из предложенных вариантов.")

# Обработка геолокации
async def handle_location(update: Update, context: CallbackContext) -> None:
    user_location = update.message.location
    if not user_location:
        await update.message.reply_text("Не удалось получить геопозицию.")
        return

    city = "Санкт-Петербург"  # ЗАГЛУШКА: здесь должен быть алгоритм определения города
    context.user_data["selected_city"] = city
    context.user_data["selected_museums"] = set()
    
    await show_museum_types(update)

# Обработка выбора города
async def handle_city_choice(update: Update, context: CallbackContext) -> None:
    city = update.message.text
    if context.user_data.get('state') == 'text_input':
        if city not in CITIES:
            await update.message.reply_text("Пожалуйста, выберите город из списка.")
            return

        context.user_data["selected_city"] = city
        context.user_data["selected_museums"] = set()

        # Получаем типы музеев из базы данных
        museum_types = fetch_museum_types_from_db()  # Функция для получения типов музеев
        context.user_data["museum_types"] = museum_types  # Сохраняем типы в user_data

        # Формируем клавиатуру для выбора музеев
        keyboard = [[InlineKeyboardButton(museum, callback_data=f"museum_{museum}")] for museum in museum_types]
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])

        await update.message.reply_text(f"Вы выбрали {city}. Теперь выберите тип музея:",
                                         reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_museum_choice(update: Update, context: CallbackContext) -> None:
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

    # Обновление inline-кнопок для отображения выбранных музеев
    museum_types = context.user_data["museum_types"]  # Получаем типы музеев из user_data

    keyboard = [[InlineKeyboardButton(f"{'✅ ' if m in context.user_data['selected_museums'] else ''}{m}",
                                      callback_data=f"museum_{m}")] for m in museum_types]
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])

    await query.answer()
    await query.message.edit_text("Выберите тип музея (можно несколько):", reply_markup=InlineKeyboardMarkup(keyboard))
    await handle_museum_info_request(update,context)



# Получение информации о музеях
async def fetch_museums_info(museum_type, city):
    connection = create_connection()
    museums_info = []

    try:
        if connection.is_connected():
            cursor = connection.cursor()
            query = """
                SELECT m.name, m.description, m.address, c.phone, c.email, c.website 
                FROM museum.museums m
                JOIN museum.museum_category mc ON m.id = mc.museum_id
                JOIN museum_types mt ON mc.type_id = mt.id
                LEFT JOIN contacts c ON m.id = c.museum_id
                WHERE mt.type_name = %s AND m.city = %s
            """
            cursor.execute(query, (museum_type, city))
            results = cursor.fetchall()
            for row in results:
                museums_info.append({
                    "name": row[0],
                    "description": row[1],
                    "address": row[2],
                    "phone": row[3],
                    "email": row[4],
                    "website": row[5],
                })
    except Error as e:
        print(f"Ошибка при работе с MySQL: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    
    return museums_info



async def handle_museum_info_request(update: Update, context: CallbackContext) -> None:
    """Обработчик для получения информации о музеях."""

    # Проверяем, является ли обновление колбэком
    if update.callback_query:
        # Получаем данные из колбэка
        query: CallbackQuery = update.callback_query
        
        # Получаем информацию о выбранном типе музея и городе
        selected_museums = context.user_data.get("selected_museums", [])
        city = context.user_data.get("selected_city")

        # Проверка наличия выбранных музеев
        if not selected_museums or city is None:
            await query.answer("Пожалуйста, выберите хотя бы один тип музея и укажите город.")
            return

        # Получаем информацию о музеях
        museums_info = []
        for museum_type in selected_museums:
            info = await fetch_museums_info(museum_type, city)
            museums_info.extend(info)  # Собираем информацию по всем выбранным музеям

        # Формирование текста для ответа
        if museums_info:
            response_text = "Информация о музеях:\n\n"
            for info in museums_info:
                response_text += (f"🏛 Название: {info['name']}\n"
                                  f"📜 Описание: {info['description']}\n"
                                  f"📍 Адрес: {info['address']}\n"
                                  f"📞 Телефон: {info['phone']}\n"
                                  f"✉️ Email: {info['email']}\n"
                                  f"🌐 Вебсайт: {info['website']}\n\n")
        else:
            response_text = "По вашему запросу ничего не найдено."

        # Подтверждаем действие колбэка
        await query.answer()  
        # Изменяем текст сообщения с кнопками на результат
        await query.edit_message_text(response_text)  





def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_selection))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(CallbackQueryHandler(handle_museum_choice, pattern="^(museum_|done)"))
    app.add_handler(CallbackQueryHandler(handle_museum_info_request, pattern='done')) 
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.run_polling()

if __name__ == '__main__':
    main()


