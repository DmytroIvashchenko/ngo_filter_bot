import telebot
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
from telebot import types
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

from const import workshop_info, actions_map, token, scope, id_spreadsheet, google_form_link, scope_calendar, \
    calendar_id

bot = telebot.TeleBot(token)

# Завантажте ключ API (завдання API Google Sheets) зі свого облікового запису Google

creds = ServiceAccountCredentials.from_json_keyfile_name('your-api-key.json', scope)
client = gspread.authorize(creds)

# Отримуємо доступ до таблиці за ідентифікатором
spreadsheet = client.open_by_key(id_spreadsheet)

# Виберіть аркуш таблиці
worksheets = [spreadsheet.get_worksheet(i) for i in range(4)]


def add_user_data_to_sheet(worksheet, user_message):
    data_to_append = [user_message]
    worksheet.append_row(data_to_append)


def create_inline_keyboard(buttons):
    keyboard = types.InlineKeyboardMarkup()

    for button_info in buttons:
        if isinstance(button_info, str):
            button = types.InlineKeyboardButton(text=button_info, callback_data=button_info)
        elif isinstance(button_info, tuple) and len(button_info) == 2:
            button = types.InlineKeyboardButton(text=button_info[0], callback_data=button_info[1])
        else:
            continue

        keyboard.add(button)

    return keyboard


def handle_action(chat_id, action):
    if isinstance(action, list):
        keyboard = create_inline_keyboard(action)
        bot.send_message(chat_id, 'Оберіть дію:', reply_markup=keyboard)
    else:
        bot.send_message(chat_id, action)


@bot.message_handler(commands=['start'])
def get_text_messages(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Привіт, вас вітає ГО "Волонтерський центр Filter"')
    keyboard = types.InlineKeyboardMarkup()

    first_row_buttons = [
        types.InlineKeyboardButton(text='Просвіта', callback_data='Просвіта'),
        types.InlineKeyboardButton(text='Консультування', callback_data='Консультування')
    ]

    second_row_buttons = [
        types.InlineKeyboardButton(text='Соціальний', callback_data='Соціальний')
    ]

    keyboard.row(*first_row_buttons)
    keyboard.row(*second_row_buttons)

    bot.send_message(user_id, 'Який напрямок вас цікавить?', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    actions = {
        "Просвіта": ["Подивитися розклад", "Зареєструватися на подію",
                     "Воркшоп по волонтерству",
                     "Ідея проєкту", "Головне меню"],
        "Подивитися розклад": lambda chat_id: show_calendar_schedule(chat_id),
        "Зареєструватися на подію": "Введіть інформацію по такому зразку:\nПодія: Ім'я: телеграм",
        "Консультування": ["Записатися на консультацію", "Головне меню"],
        "Соціальний": ["Записати свої потреби", "Головне меню"],
        "Записати свої потреби": "Опишіть свою потребу у форматі: Потреба: Ім'я, телеграм, ваша потреба",
        "Головне меню": ["Просвіта", "Консультування", "Соціальний"],
        "Записатися на консультацію": "Введіть ваші дані у форматі: Консультація: Ім'я, номер телефону телеграм, "
                                      "вид консультації (індивідуальна/групова)",
        "Ідея проєкту": "Ви можете подати ідею проєкту у форматі: Ідея: Ім'я, телеграм, коротко опис ідеї проєкту",
        "Наступний тиждень": lambda chat_id: show_next_week_schedule(chat_id),
        "Воркшоп по волонтерству": lambda chat_id: show_workshop_info(chat_id),
        "Зареєструватися на воркшоп": lambda chat_id: register_for_event(chat_id),
    }
    if call.data in actions:
        if callable(actions[call.data]):
            actions[call.data](call.message.chat.id)
        else:
            handle_action(call.message.chat.id, actions[call.data])
    else:
        bot.send_message(call.message.chat.id, 'Оберіть дію')


def process_user_message(user_id, user_message):
    for action, action_data in actions_map.items():
        if action in user_message:
            if "success_message" in action_data:
                bot.send_message(user_id, action_data["success_message"])
            add_user_data_to_sheet(worksheets[action_data["worksheet_index"]], user_message)
            handle_action(user_id, action_data.get("menu_options", []))
            return

    # Default action
    if "error_message" in actions_map["default"]:
        bot.send_message(user_id, actions_map["default"]["error_message"])
    handle_action(user_id, actions_map["default"]["menu_options"])


@bot.message_handler(func=lambda message: True)
def handle_event_registration(message):
    user_id = message.from_user.id
    user_message = message.text
    process_user_message(user_id, user_message)


def register_for_event(chat_id):
    # Тут ви можете відправити користувача посиланням на Google Forms
    bot.send_message(chat_id,
                     f"Для реєстрації на подію, будь ласка, використовуйте [це посилання]({google_form_link}).",
                     parse_mode='Markdown')


def show_workshop_info(chat_id):
    buttons = ["Головне меню", "Зареєструватися на воркшоп"]
    keyboard = create_inline_keyboard(buttons)
    bot.send_message(chat_id, workshop_info, reply_markup=keyboard, parse_mode='Markdown')


def get_calendar_schedule(start_date, end_date):
    credentials = service_account.Credentials.from_service_account_file('your-api-key.json', scopes=scope_calendar)
    service = build('calendar', 'v3', credentials=credentials)
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=start_date.isoformat() + 'Z',
        timeMax=end_date.isoformat() + 'Z',
        maxResults=20,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    schedule = ""
    for event in events:
        start_time = event['start'].get('dateTime', event['start'].get('date'))
        end_time = event['end'].get('dateTime', event['end'].get('date'))
        summary = event['summary']
        description = event.get('description', '')

        day_of_week = datetime.fromisoformat(start_time[:-6]).strftime("%A")
        if not re.search(r'\b(?:Open|школа|проєкт|психологічні|малювання)\b', summary, flags=re.IGNORECASE):
            start_time = datetime.fromisoformat(start_time[:-6])
            end_time = datetime.fromisoformat(end_time[:-6])

            start_time_str = start_time.strftime("%d.%m.%Y %H:%M")
            end_time_str = end_time.strftime("%H:%M")

            schedule += f"{day_of_week} {start_time_str} - {end_time_str} — {summary}\n"
            print(schedule)
            if description:
                description = re.sub(r'<[^>]*>', '', description)
                schedule += f"Опис: {description}\n"

    return schedule


def show_calendar_schedule(chat_id, current_date=None):
    if not current_date:
        current_date = datetime.utcnow()

    end_of_week = current_date + timedelta(days=(7 - current_date.weekday()))
    end_of_week_replace = end_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    schedule_text = get_calendar_schedule(current_date, end_of_week_replace)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item_next_week = types.KeyboardButton("Наступний тиждень")
    markup.add(item_next_week)
    print(current_date, end_of_week)
    buttons = ["Головне меню", "Зареєструватися на подію", "Наступний тиждень"]
    keyboard = create_inline_keyboard(buttons)

    bot.send_message(chat_id, schedule_text)
    bot.send_message(chat_id, 'Оберіть дію:', reply_markup=keyboard)


def show_next_week_schedule(chat_id):
    current_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    days_until_next_monday = (7 - current_date.weekday()) % 7  # Додати дні до наступного понеділка
    print(current_date, days_until_next_monday)
    if days_until_next_monday == 0:  # Якщо сьогодні понеділок, додайте 7 днів
        days_until_next_monday = 7
    next_monday = current_date + timedelta(days=days_until_next_monday)
    end_of_next_week = next_monday + timedelta(days=7)
    schedule_text = get_calendar_schedule(next_monday, end_of_next_week)

    buttons = ["Зареєструватися на подію", "Головне меню"]
    bot.send_message(chat_id, schedule_text)
    handle_action(chat_id, buttons)


if __name__ == "__main__":
    bot.polling(none_stop=True, interval=0)
