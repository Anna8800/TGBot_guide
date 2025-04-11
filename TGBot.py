from telegram import (Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, InlineQueryResultArticle, InputTextMessageContent)
from telegram.ext import (Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext, InlineQueryHandler)
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import osmnx as ox
import folium
from io import BytesIO
import requests
import logging

import mysql.connector
from mysql.connector import Error

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

CITIES = ["Санкт-Петербург", "Москва", "Самара", "Саратов", "Сан-Франциско", "Сан-Диего"] # примеры городов
MUSEUM_TYPES = []  # Музеи будут загружаться из БД

start_lon, start_lat = 30.3146, 59.9398 #эрмитаж

# Подключение к базе данных
def create_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',  # Замените на ваш хост
            database='museum',  # Замените на ваше имя базы данных
            user='root',  # Замените на ваше имя пользователя
            password='mysqlpassword79'  # Замените на ваш пароль
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Ошибка подключения к MySQL: {e}")
    return None

# Типы музеев из БД
def fetch_museum_types_from_db():
    connection = create_connection()
    types = []
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM museum.categories")
            results = cursor.fetchall()
            types = [row[0] for row in results]
    except Error as e:
        print(f"Ошибка при работе с MySQL: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    return types

# Получение информации о музеях по ГОРОДУ (для ближайших)
async def fetch_museums_info_by_city(city):
    connection = create_connection()
    museums_info = []
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            query = """
                SELECT m.name, m.description, m.address, m.phone, m.website 
                FROM museum.museums m
                JOIN museum.cities ci ON m.city_id = ci.city_id
                WHERE ci.name = %s
            """
            cursor.execute(query, (city,))  # исправлено: передача кортежа
            results = cursor.fetchall()
            for row in results:
                museums_info.append({
                    "name": row[0],
                    "description": row[1],
                    "address": row[2],
                    "phone": row[3],
                    "website": row[4],
                })
    except Error as e:
        print(f"Ошибка при работе с MySQL: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    return museums_info

# Получение информации о музеях по ГОРОДУ и ТИПУ (для фильтра)
async def fetch_museums_info_by_type(city, museum_type):
    connection = create_connection()
    museums_info = []
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            query = """
                SELECT m.name, m.description, m.address, m.phone, m.website
                FROM museum.museums m
                JOIN museum.museum_categories mc ON m.museum_id = mc.museum_id
                JOIN museum.categories c ON mc.category_id = c.category_id
                JOIN museum.cities ci ON m.city_id = ci.city_id
                WHERE ci.name = %s AND c.name = %s
            """
            cursor.execute(query, (city, museum_type))
            results = cursor.fetchall()
            for row in results:
                museums_info.append({
                    "name": row[0],
                    "description": row[1],
                    "address": row[2],
                    "phone": row[3],
                    "website": row[4],
                })
    except Error as e:
        print(f"Ошибка при работе с MySQL: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    return museums_info

# Получает ближайшие 5 музеев к заданным координатам пользователя, с расстоянием
async def fetch_nearest_museums(latitude: float, longitude: float, city: str, limit=5):
    connection = create_connection()
    museums = []
    try:
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT 
                    m.museum_id as id,
                    m.name,
                    m.description,
                    m.address,
                    m.latitude,
                    m.longitude,
                    (6371 * acos(
                        cos(radians(%s)) * 
                        cos(radians(m.latitude)) * 
                        cos(radians(m.longitude) - radians(%s)) + 
                        sin(radians(%s)) * 
                        sin(radians(m.latitude))
                    )) AS distance
                FROM museum.museums m
                JOIN museum.cities ci ON m.city_id = ci.city_id
                WHERE ci.name = %s
                ORDER BY distance
                LIMIT %s
            """
            cursor.execute(query, (latitude, longitude, latitude, city, limit))
            museums = cursor.fetchall()
    except Error as e:
        logger.error(f"Ошибка при запросе ближайших музеев: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    return museums

# Получает подробную информацию об одном конкретном музее по его ID
async def fetch_museum_details(museum_id: int):
    connection = create_connection()
    details = {}
    try:
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT 
                    m.name,
                    m.description,
                    m.address,
                    m.latitude,
                    m.longitude,
                    m.phone,
                    m.website,
                    GROUP_CONCAT(c.name SEPARATOR ', ') as categories
                FROM museum.museums m
                LEFT JOIN museum.museum_categories mc ON m.museum_id = mc.museum_id
                LEFT JOIN museum.categories c ON mc.category_id = c.category_id
                WHERE m.museum_id = %s
                GROUP BY m.museum_id
            """
            cursor.execute(query, (museum_id,))
            details = cursor.fetchone()
    except Error as e:
        print(f"Ошибка при работе с MySQL: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    return details

# Отображает информацию о музеях, отфильтрованных по городу и типам
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
                                  f"📜 Описание: {info['description']}\n")
        else:
            response_text = "По вашему запросу ничего не найдено."

        # Подтверждаем действие колбэка
        await query.answer()  
        # Изменяем текст сообщения с кнопками на результат
        await query.edit_message_text(response_text)  

# Стартовая команда — предлагает выбрать способ указания города (текстом или геолокацией)
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

# Обрабатывает inline-запросы (автодополнение списка городов)
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

# Обрабатывает пользовательский выбор способа указания города
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

# Обрабатывает текстовый ввод города и предлагает выбрать тип музея
async def handle_city_choice(update: Update, context: CallbackContext) -> None: # обрабатывает выбор города и предлагает выбрать тип музея
 
    city = update.message.text
    if context.user_data.get('state')=='text_input':

       if city not in CITIES:
         await update.message.reply_text("Пожалуйста, выберите город из списка.")
         return

       context.user_data["selected_city"] = city
       context.user_data["selected_museums"] = set()

       museum_types = fetch_museum_types_from_db()  # Функция для получения типов музеев
       context.user_data["museum_types"] = museum_types  # Сохраняем типы в user_data

        # Формируем клавиатуру для выбора музеев
       keyboard = [[InlineKeyboardButton(museum, callback_data=f"museum_{museum}")] for museum in museum_types]
       keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
       keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])  # Кнопка "Назад"

       await update.message.reply_text(f"Вы выбрали {city}. Теперь выберите тип музея:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard))

# Обрабатывает выбор типа музеев пользователем и отображает их информацию
async def handle_museum_choice(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if "selected_museums" not in context.user_data:
        context.user_data["selected_museums"] = set()

    if data == "done":
        selected_museums = list(context.user_data.get("selected_museums", []))
        city = context.user_data.get("selected_city")

        if not selected_museums or not city:
            await query.edit_message_text("Пожалуйста, выберите хотя бы один тип музея и город.")
            return

        museums_info = []
        for mtype in selected_museums:
            info = await fetch_museums_info_by_type(city, mtype)
            museums_info.extend(info)

        if museums_info:
            response_text = "Информация о музеях:\n\n"
            for info in museums_info:
                response_text += (
                    f"🏛 {info['name']}\n"
                    f"📜 {info['description']}\n"
                    f"📍 {info['address']}\n"
                    f"📞 {info['phone']}\n"
                    f"🌐 {info['website']}\n\n"
                )
        else:
            response_text = "По вашему запросу ничего не найдено."

        await query.edit_message_text(response_text)
        return

    elif data == "back":
        await query.message.delete()
        await start(update, context)
        return

    museum_type = data.split("_")[1]
    selected = context.user_data["selected_museums"]
    selected.symmetric_difference_update([museum_type])
    museum_types = context.user_data.get("museum_types", [])

    keyboard = [
        [InlineKeyboardButton(f"{'✅ ' if m in selected else ''}{m}", callback_data=f"museum_{m}")]
        for m in museum_types
    ]
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])

    await query.message.edit_text("Выберите тип музея (можно несколько):", reply_markup=InlineKeyboardMarkup(keyboard))

# Обрабатывает геолокацию пользователя и показывает ближайшие музеи в городе
async def handle_location(update: Update, context: CallbackContext) -> None:
    user_location = update.message.location
    if not user_location:
        await update.message.reply_text("Не удалось получить геопозицию.")
        return

    try:
        latitude = user_location.latitude
        longitude = user_location.longitude

        geolocator = Nominatim(user_agent="museum_bot")
        location = geolocator.reverse((latitude, longitude), exactly_one=True)
        city = location.raw.get("address", {}).get("city") or location.raw.get("address", {}).get("town")

        if not city:
            await update.message.reply_text("Не удалось определить город.")
            return

        if city not in CITIES:
            await update.message.reply_text("К сожалению, в вашем городе нет музеев.")
            await start(update, context)
            return

        context.user_data.update({
            "user_lat": latitude,
            "user_lon": longitude,
            "selected_city": city
        })

        museums = await fetch_nearest_museums(latitude, longitude, city)
        if not museums:
            await update.message.reply_text("В вашем городе не найдено музеев.")
            return

        context.user_data["nearest_museums"] = museums

        keyboard = [
            [InlineKeyboardButton(f"{m['name']} ({m['distance']:.1f} км)", callback_data=f"museum_{m['id']}")]
            for m in museums
        ]
        await update.message.reply_text(
            f"Ближайшие музеи в {city}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Ошибка при обработке геолокации: {e}")
        await update.message.reply_text("Произошла ошибка при обработке местоположения.")


# При выборе музея — показывает маршрут + информацию о нём (объединённая логика)
async def handle_museum_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if not query.data.startswith('museum_'):
        return

    try:
        museum_id = int(query.data.split('_')[1])
        museum = next((m for m in context.user_data.get("nearest_museums", []) if m['id'] == museum_id), None)
        if not museum:
            await query.edit_message_text("Музей не найден.")
            return

        user_lat = context.user_data.get("user_lat")
        user_lon = context.user_data.get("user_lon")

        osrm_url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{user_lon},{user_lat};{museum['longitude']},{museum['latitude']}"
            f"?overview=full&geometries=geojson"
        )
        response = requests.get(osrm_url)
        if response.status_code != 200 or response.json().get("code") != "Ok":
            await query.edit_message_text("Не удалось построить маршрут.")
            return

        route_data = response.json()
        route_coords = [(lat, lon) for lon, lat in route_data["routes"][0]["geometry"]["coordinates"]]

        route_map = folium.Map(location=[user_lat, user_lon], zoom_start=14)
        folium.PolyLine(route_coords, color="blue", weight=5).add_to(route_map)
        folium.Marker([user_lat, user_lon], popup="Вы", icon=folium.Icon(color="green")).add_to(route_map)
        folium.Marker([museum['latitude'], museum['longitude']], popup=museum['name'], icon=folium.Icon(color="red")).add_to(route_map)

        map_file = BytesIO()
        route_map.save(map_file, close_file=False)
        map_file.seek(0)

        await query.message.reply_document(
            document=map_file,
            filename=f"route_to_{museum['name']}.html",
            caption=f"Маршрут до {museum['name']}"
        )

        osm_link = (
            f"https://www.openstreetmap.org/directions?engine=osrm_car&route="
            f"{user_lat}%2C{user_lon}%3B{museum['latitude']}%2C{museum['longitude']}"
        )

        info_text = (
            f"🏛 <b>{museum['name']}</b>\n"
            f"📍 {museum.get('address', 'Не указан')}\n"
            f"📜 {museum.get('description', 'Нет описания')}\n"
            f"📏 Расстояние: {museum['distance']:.1f} км\n"
            f"\n<a href=\"{osm_link}\">Открыть маршрут в OpenStreetMap</a>"
        )

        await query.message.reply_text(info_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при показе музея: {e}")
        await query.edit_message_text("Ошибка при получении информации.")

# Команда /help — выводит справку о работе бота
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

    # Команды
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))

    # Сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_selection))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    # Inline-запросы
    app.add_handler(InlineQueryHandler(inline_query_handler))  

    # Callback кнопки
    app.add_handler(CallbackQueryHandler(handle_museum_selection, pattern="^museum_\\d+$"))
    app.add_handler(CallbackQueryHandler(handle_museum_choice, pattern="^(museum_.*|done|back)$"))
    
    app.run_polling()

if __name__ == '__main__':
    main()