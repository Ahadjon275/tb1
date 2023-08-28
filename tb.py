#!/usr/bin/env python3

import io
import os
import random
import re
import tempfile
import datetime
import string
import threading
import time
import queue

import openai
import PyPDF2
import telebot
from langdetect import detect_langs
from natsort import natsorted

import bingai
import cfg
import gpt_basic
import my_bard
import my_claude
import my_genimg
import my_dic
import my_google
import my_log
import my_ocr
import my_p_hub
import my_pandoc
import my_perplexity
import my_stt
import my_sum
import my_trans
import my_tts
import my_wikipedia
import utils


# использовать прокси (пиратские сайты обычно лочат ваш ип, так что смотрите за этим)
#cfg.all_proxy = ''
#cfg.all_proxy = 'socks5://172.28.1.5:1080'
if cfg.all_proxy:
    os.environ['all_proxy'] = cfg.all_proxy


# устанавливаем рабочую папку = папке в которой скрипт лежит
os.chdir(os.path.abspath(os.path.dirname(__file__)))


bot = telebot.TeleBot(cfg.token, skip_pending=True)
_bot_name = bot.get_me().username
BOT_ID = bot.get_me().id
#telebot.apihelper.proxy = cfg.proxy_settings


# телеграм группа для отправки сгенерированных картинок
pics_group = cfg.pics_group
pics_group_url = cfg.pics_group_url

# до 40 одновременных потоков для чата с гпт и бингом
semaphore_talks = threading.Semaphore(40)

# папка для постоянных словарей, памяти бота
if not os.path.exists('db'):
    os.mkdir('db')


# заблокированные юзера {id:True/False}
BAD_USERS = my_dic.PersistentDict('db/bad_users.pkl')

# в каких чатах какой чатбот отвечает {chat_id_full(str):chatbot(str)}
# 'bard', 'claude', 'chatgpt', 'bing'
CHAT_MODE = my_dic.PersistentDict('db/chat_mode.pkl')

# история диалогов для GPT chat
DIALOGS_DB = my_dic.PersistentDict('db/dialogs.pkl')
# в каких чатах выключены автопереводы. 0 - выключено, 1 - включено
BLOCKS = my_dic.PersistentDict('db/blocks.pkl')

# каким голосом озвучивать, мужским или женским
TTS_GENDER = my_dic.PersistentDict('db/tts_gender.pkl')

# в каких чатах какой промт
PROMPTS = my_dic.PersistentDict('db/prompts.pkl')

# запоминаем промпты для повторения рисования
IMAGE_PROMPTS = my_dic.PersistentDict('db/image_prompts.pkl')

# температура для chatGPT, от 0 до 1, чем больше чем больше бреда и вранья будет
# по умолчанию - авто
# {id:float [0:1]}
TEMPERATURE = my_dic.PersistentDict('db/temperature.pkl')

# запоминаем диалоги в чатах для того что бы потом можно было сделать самморизацию,
# выдать краткое содержание
CHAT_LOGS = my_dic.PersistentDict('db/chat_logs.pkl')

# запоминаем у какого юзера какой язык OCR выбран
OCR_DB = my_dic.PersistentDict('db/ocr_db.pkl')

# для запоминания ответов на команду /sum
SUM_CACHE = my_dic.PersistentDict('db/sum_cache.pkl')

# запоминаем книги присланные юзерами {user_id:(chunks, lang, name)}
BOOKS = my_dic.PersistentDict('db/books.pkl')

# в каких чатах активирован режим суперчата, когда бот отвечает на все реплики всех участников
# {chat_id:0|1}
SUPER_CHAT = my_dic.PersistentDict('db/super_chat.pkl')

# в каких чатах какая команда дана, как обрабатывать последующий текст
# например после команды /image ожидаем описание картинки
# COMMAND_MODE[chat_id] = 'google'|'image'|...
COMMAND_MODE = {}

# в каких чатах включен режим только голосовые сообщения {'chat_id_full':True/False}
VOICE_ONLY_MODE = my_dic.PersistentDict('db/voice_only_mode.pkl')

# в каких чатах отключена клавиатура {'chat_id_full':True/False}
DISABLED_KBD = my_dic.PersistentDict('db/disabled_kbd.pkl')

# автоматически заблокированные за слишком частые обращения к боту 
# {user_id:Time to release in seconds - дата когда можно выпускать из бана} 
DDOS_BLOCKED_USERS = my_dic.PersistentDict('db/ddos_blocked_users.pkl')

# замки для блокировки одновременных ответов бинга в режиме стриминга
BING_LOCKS_STREAMING_MODE = {}

# в каких чатах какое у бота кодовое слово для обращения к боту
BOT_NAMES = my_dic.PersistentDict('db/names.pkl')
# имя бота по умолчанию, в нижнем регистре без пробелов и символов
BOT_NAME_DEFAULT = cfg.default_bot_name

supported_langs_trans = [
        "af","am","ar","az","be","bg","bn","bs","ca","ceb","co","cs","cy","da","de",
        "el","en","eo","es","et","eu","fa","fi","fr","fy","ga","gd","gl","gu","ha",
        "haw","he","hi","hmn","hr","ht","hu","hy","id","ig","is","it","iw","ja","jw",
        "ka","kk","km","kn","ko","ku","ky","la","lb","lo","lt","lv","mg","mi","mk",
        "ml","mn","mr","ms","mt","my","ne","nl","no","ny","or","pa","pl","ps","pt",
        "ro","ru","rw","sd","si","sk","sl","sm","sn","so","sq","sr","st","su","sv",
        "sw","ta","te","tg","th","tl","tr","uk","ur","uz","vi","xh","yi","yo","zh",
        "zh-TW","zu"]
supported_langs_tts = [
        'af', 'am', 'ar', 'as', 'az', 'be', 'bg', 'bn', 'bs', 'ca', 'cs', 'cy', 'da',
        'de', 'el', 'en', 'eo', 'es', 'et', 'eu', 'fa', 'fi', 'fil', 'fr', 'ga', 'gl',
        'gu', 'he', 'hi', 'hr', 'ht', 'hu', 'hy', 'id', 'is', 'it', 'ja', 'jv', 'ka',
        'kk', 'km', 'kn', 'ko', 'ku', 'ky', 'la', 'lb', 'lo', 'lt', 'lv', 'mg', 'mi',
        'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 'my', 'nb', 'ne', 'nl', 'nn', 'no', 'ny',
        'or', 'pa', 'pl', 'ps', 'pt', 'ro', 'ru', 'rw', 'sd', 'si', 'sk', 'sl', 'sm',
        'sn', 'so', 'sq', 'sr', 'st', 'su', 'sv', 'sw', 'ta', 'te', 'tg', 'th', 'tk',
        'tl', 'tr', 'tt', 'ug', 'uk', 'ur', 'uz', 'vi', 'xh', 'yi', 'yo', 'zh', 'zu']

MSG_CONFIG = """***Панель управления***

Тут можно:

- стереть память боту

- переключить чат с chatGPT на Microsoft Bing или Google Bard

- изменить голос

- выключить авто переводы иностранных текстов на канале и перевод голосовых сообщений в текст

Настройки стиля /style и история /mem ***относятся только к chatGPT***
У Барда и Бинга свои особенные правила, которые не могут быть изменены
"""

class RequestCounter:
    """Ограничитель числа запросов к боту
    не дает делать больше 10 в минуту, банит на сутки после превышения"""
    def __init__(self):
        self.counts = {}

    def check_limit(self, user_id):
        """Возвращает True если лимит не превышен, False если превышен или юзер уже забанен"""
        current_time = time.time()

        if user_id in DDOS_BLOCKED_USERS:
            if DDOS_BLOCKED_USERS[user_id] > current_time:
                return False
            else:
                del DDOS_BLOCKED_USERS[user_id]

        if user_id not in self.counts:
            self.counts[user_id] = [current_time]
            return True
        else:
            timestamps = self.counts[user_id]
            # Удаляем старые временные метки, которые находятся за пределами 1 минуты
            timestamps = [timestamp for timestamp in timestamps if timestamp >= current_time - 60]
            if len(timestamps) < cfg.DDOS_MAX_PER_MINUTE:
                timestamps.append(current_time)
                self.counts[user_id] = timestamps
                return True
            else:
                DDOS_BLOCKED_USERS[user_id] = current_time + cfg.DDOS_BAN_TIME
                my_log.log2(f'tb:request_counter:check_limit: user blocked {user_id}')
                return False


request_counter = RequestCounter()


class ShowAction(threading.Thread):
    """Поток который можно остановить. Беспрерывно отправляет в чат уведомление об активности.
    Телеграм автоматически гасит уведомление через 5 секунд, по-этому его надо повторять.

    Использовать в коде надо как то так
    with ShowAction(message, 'typing'):
        делаем что-нибудь и пока делаем уведомление не гаснет
    """
    def __init__(self, message, action):
        """_summary_

        Args:
            chat_id (_type_): id чата в котором будет отображаться уведомление
            action (_type_):  "typing", "upload_photo", "record_video", "upload_video", "record_audio", 
                              "upload_audio", "upload_document", "find_location", "record_video_note", "upload_video_note"
        """
        super().__init__()
        self.actions = [  "typing", "upload_photo", "record_video", "upload_video", "record_audio",
                         "upload_audio", "upload_document", "find_location", "record_video_note", "upload_video_note"]
        assert action in self.actions, f'Допустимые actions = {self.actions}'
        self.chat_id = message.chat.id
        self.thread_id = message.message_thread_id
        self.is_topic = message.is_topic_message
        self.action = action
        self.is_running = True
        self.timerseconds = 1

    def run(self):
        while self.is_running:
            try:
                if self.is_topic:
                    bot.send_chat_action(self.chat_id, self.action, message_thread_id = self.thread_id)
                else:
                    bot.send_chat_action(self.chat_id, self.action)
            except Exception as error:
                my_log.log2(f'tb:show_action:run: {error}')
            n = 50
            while n > 0:
                time.sleep(0.1)
                n = n - self.timerseconds

    def stop(self):
        self.timerseconds = 50
        self.is_running = False
        try:
            bot.send_chat_action(self.chat_id, 'cancel', message_thread_id = self.thread_id)
        except Exception as error:
            my_log.log2(f'tb:show_action: {error}')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def dialog_add_user_request(chat_id: str, text: str, engine: str = 'gpt') -> str:
    """добавляет в историю переписки с юзером его новый запрос и ответ от чатбота
    делает запрос и возвращает ответ

    Args:
        chat_id (str): номер чата или юзера, нужен для хранения истории переписки
        text (str): новый запрос от юзера
        engine (str, optional): 'gpt' или 'bing'. Defaults to 'gpt'.

    Returns:
        str: возвращает ответ который бот может показать, возможно '' или None
    """

    # в каждом чате своя температура
    if chat_id in TEMPERATURE:
        temp = TEMPERATURE[chat_id]
    else:
        temp = 0

    # в каждом чате свой собственный промт
    if chat_id in PROMPTS:
        current_prompt = PROMPTS[chat_id]
    else:
        # по умолчанию формальный стиль
        PROMPTS[chat_id] = [{"role": "system", "content": utils.gpt_start_message1}]
        current_prompt =   [{"role": "system", "content": utils.gpt_start_message1}]

    # создаем новую историю диалогов с юзером из старой если есть
    # в истории диалогов не храним системный промпт
    if chat_id in DIALOGS_DB:
        new_messages = DIALOGS_DB[chat_id]
    else:
        new_messages = []

    # теперь ее надо почистить что бы влезла в запрос к GPT
    # просто удаляем все кроме max_hist_lines последних
    if len(new_messages) > cfg.max_hist_lines:
        new_messages = new_messages[cfg.max_hist_lines:]
    # удаляем первую запись в истории до тех пор пока общее количество токенов не станет меньше cfg.max_hist_bytes
    # удаляем по 2 сразу так как первая - промпт для бота
    while (utils.count_tokens(new_messages) > cfg.max_hist_bytes):
        new_messages = new_messages[2:]

    # добавляем в историю новый запрос и отправляем
    new_messages = new_messages + [{"role":    "user",
                                    "content": text}]

    if engine == 'gpt':
        # пытаемся получить ответ
        try:
            resp = gpt_basic.ai(prompt = text, temp = temp, messages = current_prompt + new_messages, chat_id=chat_id)
            if resp:
                new_messages = new_messages + [{"role":    "assistant",
                                                    "content": resp}]
            else:
                # не сохраняем диалог, нет ответа
                # если в последнем сообщении нет текста (глюк) то убираем его
                if new_messages[-1]['content'].strip() == '':
                    new_messages = new_messages[:-1]
                DIALOGS_DB[chat_id] = new_messages or []
                return 'GPT не ответил.'
        # бот не ответил или обиделся
        except AttributeError:
            # не сохраняем диалог, нет ответа
            return 'Не хочу говорить об этом. Или не могу.'
        # произошла ошибка переполнения ответа
        except openai.error.InvalidRequestError as error2:
            if """This model's maximum context length is""" in str(error2):
                # чистим историю, повторяем запрос
                p = '\n'.join(f'{i["role"]} - {i["content"]}\n' for i in new_messages) or 'Пусто'
                # сжимаем весь предыдущий разговор до cfg.max_hist_compressed символов
                r = gpt_basic.ai_compress(p, cfg.max_hist_compressed, 'dialog')
                new_messages = [{'role':'system','content':r}] + new_messages[-1:]
                # и на всякий случай еще
                while (utils.count_tokens(new_messages) > cfg.max_hist_compressed):
                    new_messages = new_messages[2:]

                try:
                    resp = gpt_basic.ai(prompt = text, temp=temp, messages = current_prompt + new_messages, chat_id=chat_id)
                except Exception as error3:
                    print(error3)
                    return 'GPT не ответил.'

                # добавляем в историю новый запрос и отправляем в GPT, если он не пустой, иначе удаляем запрос юзера из истории
                if resp:
                    new_messages = new_messages + [{"role":    "assistant",
                                                    "content": resp}]
                else:
                    return 'GPT не ответил.'
            else:
                print(error2)
                return 'GPT не ответил.'
    else:
        # для бинга
        hist_compressed = ''
        bing_prompt = hist_compressed + '\n\n' + 'Отвечай по-русски\n\n' + text

        msg_bing_no_answer = 'Бинг не ответил.'
        try:
            #my_log.log2(bing_prompt)
            resp = bingai.ai(bing_prompt, 1)
        except Exception as error2:
            print(error2)
            my_log.log2(error2)
            return msg_bing_no_answer
        if resp:
            new_messages = new_messages + [{"role":    "assistant",
                                            "content": resp}]
        else:
            # не сохраняем диалог, нет ответа
            return msg_bing_no_answer

    # сохраняем диалог, на данном этапе в истории разговора должны быть 2 последних записи несжатыми
    new_messages = new_messages[:-2]
    # если запрос юзера был длинным то в истории надо сохранить его коротко
    if len(text) > cfg.max_hist_mem:
        new_text = gpt_basic.ai_compress(text, cfg.max_hist_mem, 'user')
        # заменяем запрос пользователя на сокращенную версию
        new_messages += [{"role":    "user",
                             "content": new_text}]
    else:
        new_messages += [{"role":    "user",
                            "content": text}]
    # если ответ бота был длинным то в истории надо сохранить его коротко
    if len(resp) > cfg.max_hist_mem:
        new_resp = gpt_basic.ai_compress(resp, cfg.max_hist_mem, 'assistant')
        new_messages += [{"role":    "assistant",
                             "content": new_resp}]
    else:
        new_messages += [{"role":    "assistant",
                             "content": resp}]
    DIALOGS_DB[chat_id] = new_messages or []

    return resp


def get_ocr_language(message) -> str:
    """Возвращает настройки языка OCR для этого чата"""
    chat_id_full = get_topic_id(message)

    if chat_id_full in OCR_DB:
        lang = OCR_DB[chat_id_full]
    else:
        try:
            OCR_DB[chat_id_full] = cfg.ocr_language
        except:
            OCR_DB[chat_id_full] = 'rus+eng'
        lang = OCR_DB[chat_id_full]
    return lang


def get_topic_id(message: telebot.types.Message) -> str:
    """
    Get the topic ID from a Telegram message.

    Parameters:
        message (telebot.types.Message): The Telegram message object.

    Returns:
        str: '[chat.id] [topic.id]'
    """

    chat_id = message.chat.id
    # topic_id = 'not topic'
    topic_id = 0

    if message.reply_to_message and message.reply_to_message.is_topic_message:
        topic_id = message.reply_to_message.message_thread_id
    elif message.is_topic_message:
        topic_id = message.message_thread_id

    # bot.reply_to(message, f'DEBUG: [{chat_id}] [{topic_id}]')

    return f'[{chat_id}] [{topic_id}]'


def is_admin_member(message: telebot.types.Message):
    """Checks if the user is an admin member of the chat."""
    if not message:
        return False
    chat_id = message.chat.id
    user_id = message.from_user.id
    member = bot.get_chat_member(chat_id, user_id).status.lower()
    return True if 'creator' in member or 'administrator' in member else False


def disabled_kbd(chat_id_full):
    """проверяет не отключена ли тут клавиатура"""
    if chat_id_full not in DISABLED_KBD:
        DISABLED_KBD[chat_id_full] = False
    return DISABLED_KBD[chat_id_full]


def get_keyboard(kbd: str, message: telebot.types.Message, flag: str = '') -> telebot.types.InlineKeyboardMarkup:
    """создает и возвращает клавиатуру по текстовому описанию
    'chat' - клавиатура для чата
    'mem' - клавиатура для команды mem, с кнопками Забудь и Скрой
    'hide' - клавиатура с одной кнопкой Скрой
    ...
    """
    chat_id_full = get_topic_id(message)

    if kbd == 'chat':
        if disabled_kbd(chat_id_full):
            return None
        markup  = telebot.types.InlineKeyboardMarkup(row_width=5)
        button1 = telebot.types.InlineKeyboardButton("➡", callback_data='continue_gpt')
        button2 = telebot.types.InlineKeyboardButton("♻️", callback_data='forget_all')
        button3 = telebot.types.InlineKeyboardButton("🙈", callback_data='erase_answer')
        button4 = telebot.types.InlineKeyboardButton("📢", callback_data='tts')
        button5 = telebot.types.InlineKeyboardButton("🇷🇺", callback_data='translate_chat')
        markup.add(button1, button2, button3, button4, button5)
        return markup
    elif kbd == 'mem':
        markup  = telebot.types.InlineKeyboardMarkup()
        button1 = telebot.types.InlineKeyboardButton("Стереть историю", callback_data='clear_history')
        button2 = telebot.types.InlineKeyboardButton("Скрыть", callback_data='erase_answer')
        markup.add(button1, button2)
        return markup
    elif kbd == 'hide':
        markup  = telebot.types.InlineKeyboardMarkup()
        button1 = telebot.types.InlineKeyboardButton("Скрыть", callback_data='erase_answer')
        markup.add(button1)
        return markup
    elif kbd == 'command_mode':
        markup  = telebot.types.InlineKeyboardMarkup()
        button1 = telebot.types.InlineKeyboardButton("Отмена", callback_data='cancel_command')
        markup.add(button1)
        return markup
    elif kbd == 'perplexity':
        markup  = telebot.types.InlineKeyboardMarkup(row_width=4)
        button1 = telebot.types.InlineKeyboardButton("🙈", callback_data='erase_answer')
        button2 = telebot.types.InlineKeyboardButton("📢", callback_data='tts')
        button3 = telebot.types.InlineKeyboardButton("🇷🇺", callback_data='translate_perplexity')
        button4 = telebot.types.InlineKeyboardButton("⛔️Выход", callback_data='cancel_command_not_hide')
        markup.row(button1, button2, button3, button4)
        return markup       
    elif kbd == 'translate_and_repair':
        markup  = telebot.types.InlineKeyboardMarkup(row_width=4)
        button1 = telebot.types.InlineKeyboardButton("🙈", callback_data='erase_answer')
        button2 = telebot.types.InlineKeyboardButton("📢", callback_data='tts')
        button3 = telebot.types.InlineKeyboardButton("🇷🇺", callback_data='translate')
        button4 = telebot.types.InlineKeyboardButton("✨Исправить✨", callback_data='voice_repair')
        markup.row(button1, button2, button3)
        markup.row(button4)
        return markup
    elif kbd == 'translate':
        markup  = telebot.types.InlineKeyboardMarkup()
        button1 = telebot.types.InlineKeyboardButton("Скрыть", callback_data='erase_answer')
        button2 = telebot.types.InlineKeyboardButton("📢", callback_data='tts')
        button3 = telebot.types.InlineKeyboardButton("Перевод 🇷🇺", callback_data='translate')
        markup.add(button1, button2, button3)
        return markup
    elif kbd == 'hide_image':
        markup  = telebot.types.InlineKeyboardMarkup()
        button1 = telebot.types.InlineKeyboardButton("Скрыть", callback_data='erase_image')
        button2 = telebot.types.InlineKeyboardButton("Повторить", callback_data='repeat_image')
        markup.add(button1, button2)
        return markup
    elif kbd == 'start':
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        button1 = telebot.types.KeyboardButton('🎨Нарисуй')
        button2 = telebot.types.KeyboardButton('🌐Найди')
        button3 = telebot.types.KeyboardButton('📋Перескажи')
        button4 = telebot.types.KeyboardButton('🎧Озвучь')
        button5 = telebot.types.KeyboardButton('🈶Переведи')
        button6 = telebot.types.KeyboardButton('⚙️Настройки')
        markup.row(button1, button2, button3)
        markup.row(button4, button5, button6)
        return markup
    elif kbd == 'bing_chat':
        if disabled_kbd(chat_id_full):
            return None
        markup  = telebot.types.InlineKeyboardMarkup(row_width=5)
        button0 = telebot.types.InlineKeyboardButton("➡", callback_data='continue_gpt')
        button1 = telebot.types.InlineKeyboardButton('♻️', callback_data='bingAI_reset')
        button2 = telebot.types.InlineKeyboardButton("🙈", callback_data='erase_answer')
        button3 = telebot.types.InlineKeyboardButton("📢", callback_data='tts')
        button4 = telebot.types.InlineKeyboardButton("🇷🇺", callback_data='translate_chat')
        markup.add(button0, button1, button2, button3, button4)
        return markup
    elif kbd == 'claude_chat':
        if disabled_kbd(chat_id_full):
            return None
        markup  = telebot.types.InlineKeyboardMarkup(row_width=5)
        button0 = telebot.types.InlineKeyboardButton("➡", callback_data='continue_gpt')
        button1 = telebot.types.InlineKeyboardButton('♻️', callback_data='claudeAI_reset')
        button2 = telebot.types.InlineKeyboardButton("🙈", callback_data='erase_answer')
        button3 = telebot.types.InlineKeyboardButton("📢", callback_data='tts')
        button4 = telebot.types.InlineKeyboardButton("🇷🇺", callback_data='translate_chat')
        markup.add(button0, button1, button2, button3, button4)
        return markup
    elif kbd == 'bard_chat':
        if disabled_kbd(chat_id_full):
            return None
        markup  = telebot.types.InlineKeyboardMarkup(row_width=5)
        button0 = telebot.types.InlineKeyboardButton("➡", callback_data='continue_gpt')
        button1 = telebot.types.InlineKeyboardButton('♻️', callback_data='bardAI_reset')
        button2 = telebot.types.InlineKeyboardButton("🙈", callback_data='erase_answer')
        button3 = telebot.types.InlineKeyboardButton("📢", callback_data='tts')
        button4 = telebot.types.InlineKeyboardButton("🇷🇺", callback_data='translate_chat')
        markup.add(button0, button1, button2, button3, button4)
        return markup
    elif kbd == 'config':
        if chat_id_full in TTS_GENDER:
            voice = f'tts_{TTS_GENDER[chat_id_full]}'
        else:
            voice = 'tts_female'

        voices = {'tts_female': 'MS жен.',
                  'tts_male': 'MS муж.',
                  'tts_google_female': 'Google',
                  'tts_silero_xenia': 'Xenia',
                  'tts_silero_aidar': 'Aidar'
                  }
        voice_title = voices[voice]

        # кто по умолчанию
        if chat_id_full not in CHAT_MODE:
            CHAT_MODE[chat_id_full] = cfg.chat_mode_default

        markup  = telebot.types.InlineKeyboardMarkup(row_width=1)

        if CHAT_MODE[chat_id_full] == 'chatgpt':
            button1 = telebot.types.InlineKeyboardButton('✅ChatGPT', callback_data='chatGPT_mode_disable')
        else:
            button1 = telebot.types.InlineKeyboardButton('☑️ChatGPT', callback_data='chatGPT_mode_enable')
        button2 = telebot.types.InlineKeyboardButton('❌Стереть', callback_data='chatGPT_reset')
        markup.row(button1, button2)

        if CHAT_MODE[chat_id_full] == 'bard':
            button1 = telebot.types.InlineKeyboardButton('✅Bard AI', callback_data='bard_mode_disable')
        else:
            button1 = telebot.types.InlineKeyboardButton('☑️Bard AI', callback_data='bard_mode_enable')

        button2 = telebot.types.InlineKeyboardButton('❌Стереть', callback_data='bardAI_reset')
        markup.row(button1, button2)

        if CHAT_MODE[chat_id_full] == 'claude':
            button1 = telebot.types.InlineKeyboardButton('✅Claude AI', callback_data='claude_mode_disable')
        else:
            button1 = telebot.types.InlineKeyboardButton('☑️Claude AI', callback_data='claude_mode_enable')

        button2 = telebot.types.InlineKeyboardButton('❌Стереть', callback_data='claudeAI_reset')
        markup.row(button1, button2)

        if CHAT_MODE[chat_id_full] == 'bing':
            button1 = telebot.types.InlineKeyboardButton('✅Bing AI', callback_data='bing_mode_disable')
        else:
            button1 = telebot.types.InlineKeyboardButton('☑️Bing AI', callback_data='bing_mode_enable')

        button2 = telebot.types.InlineKeyboardButton('❌Стереть', callback_data='bingAI_reset')
        markup.row(button1, button2)

        button1 = telebot.types.InlineKeyboardButton(f'📢Голос: {voice_title}', callback_data=voice)
        if chat_id_full not in VOICE_ONLY_MODE:
            VOICE_ONLY_MODE[chat_id_full] = False
        if VOICE_ONLY_MODE[chat_id_full]:
            button2 = telebot.types.InlineKeyboardButton('✅Только голос', callback_data='voice_only_mode_disable')
        else:
            button2 = telebot.types.InlineKeyboardButton('☑️Только голос', callback_data='voice_only_mode_enable')
        markup.row(button1, button2)

        if chat_id_full not in BLOCKS:
            BLOCKS[chat_id_full] = 0

        if BLOCKS[chat_id_full] == 1:
            button1 = telebot.types.InlineKeyboardButton(f'✅Автопереводы', callback_data='autotranslate_disable')
        else:
            button1 = telebot.types.InlineKeyboardButton(f'☑️Автопереводы', callback_data='autotranslate_enable')
        if chat_id_full not in DISABLED_KBD:
            DISABLED_KBD[chat_id_full] = False
        if DISABLED_KBD[chat_id_full]:
            button2 = telebot.types.InlineKeyboardButton(f'☑️Чат-кнопки', callback_data='disable_chat_kbd')
        else:
            button2 = telebot.types.InlineKeyboardButton(f'✅Чат-кнопки', callback_data='enable_chat_kbd')
        markup.row(button1, button2)

        if cfg.pics_group_url:
            button_pics = telebot.types.InlineKeyboardButton("🖼️Галерея",  url = cfg.pics_group_url)
            markup.add(button_pics)

        button = telebot.types.InlineKeyboardButton('🔍История ChatGPT', callback_data='chatGPT_memory_debug')
        markup.add(button)

        is_admin_of_group = False
        if message.reply_to_message:
            is_admin_of_group = is_admin_member(message.reply_to_message)
            from_user = message.reply_to_message.from_user.id
        else:
            from_user = message.from_user.id
            is_admin_of_group = is_admin_member(message)

        if flag == 'admin' or is_admin_of_group or from_user in cfg.admins:
            if chat_id_full not in SUPER_CHAT:
                SUPER_CHAT[chat_id_full] = 0
            if SUPER_CHAT[chat_id_full] == 1:
                button = telebot.types.InlineKeyboardButton('✅Автоответы в чате', callback_data='admin_chat')
            else:
                button = telebot.types.InlineKeyboardButton('☑️Автоответы в чате', callback_data='admin_chat')
            markup.add(button)

        button = telebot.types.InlineKeyboardButton('🙈Закрыть меню', callback_data='erase_answer')
        markup.add(button)

        return markup
    elif kbd == 'book_tts':
        markup  = telebot.types.InlineKeyboardMarkup(row_width=2)
        counter = 0
        for _ in BOOKS[chat_id_full][0]:
            button = telebot.types.InlineKeyboardButton(f'📢 Часть #{counter + 1}', callback_data=f'tts_book:{counter}')
            markup.add(button)
            counter += 1
        markup.add(telebot.types.InlineKeyboardButton(f'Скачать текст', callback_data=f'tts_book:get_text'))
        return markup

    else:
        raise f"Неизвестная клавиатура '{kbd}'"


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call: telebot.types.CallbackQuery):
    """Обработчик клавиатуры"""
    thread = threading.Thread(target=callback_inline_thread, args=(call,))
    thread.start()
def callback_inline_thread(call: telebot.types.CallbackQuery):
    """Обработчик клавиатуры"""

    with semaphore_talks:
        message = call.message
        chat_id = message.chat.id
        chat_id_full = get_topic_id(message)
        # check_blocked_user(chat_id_full)

        if call.data == 'clear_history':
            # обработка нажатия кнопки "Стереть историю"
            #bot.edit_message_reply_markup(message.chat.id, message.message_id)
            DIALOGS_DB[chat_id_full] = []
            bot.delete_message(message.chat.id, message.message_id)
        elif call.data == 'continue_gpt':
            # обработка нажатия кнопки "Продолжай GPT"
            message.dont_check_topic = True
            echo_all(message, 'Продолжай')
            return
        elif call.data == 'forget_all':
            # обработка нажатия кнопки "Забудь всё"
            DIALOGS_DB[chat_id_full] = []
        elif call.data == 'cancel_command':
            # обработка нажатия кнопки "Отменить ввод команды"
            COMMAND_MODE[chat_id_full] = ''
            bot.delete_message(message.chat.id, message.message_id)
        elif call.data == 'cancel_command_not_hide':
            # обработка нажатия кнопки "Отменить ввод команды, но не скрывать"
            COMMAND_MODE[chat_id_full] = ''
            # bot.delete_message(message.chat.id, message.message_id)
            bot.reply_to(message, 'Режим гугления отключен')
        # режим автоответов в чате, бот отвечает на все реплики всех участников
        # комната для разговоров с ботом Ж)
        elif call.data == 'admin_chat':
            #bot.reply_to(message, 'Автоответы в чате активированы, бот будет отвечать на все реплики всех участников')
            if chat_id_full in SUPER_CHAT:
                SUPER_CHAT[chat_id_full] = 1 if SUPER_CHAT[chat_id_full] == 0 else 0
            else:
                SUPER_CHAT[chat_id_full] = 1
            bot.edit_message_text(chat_id=chat_id, parse_mode='Markdown', message_id=message.message_id,
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message, 'admin'))
        elif call.data == 'erase_answer':
            # обработка нажатия кнопки "Стереть ответ"
            bot.delete_message(message.chat.id, message.message_id)
        elif call.data == 'tts':
            lang = my_trans.detect_lang(message.text) or 'ru'
            message.text = f'/tts {lang} {message.text}'
            tts(message)
        elif call.data == 'erase_image':
            # обработка нажатия кнопки "Стереть ответ"
            bot.delete_message(message.chat.id, message.message_id)
            # получаем номер сообщения с картинками из сообщения с ссылками на картинки который идет следом
            for i in message.text.split('\n')[0].split():
                bot.delete_message(message.chat.id, int(i))
        elif call.data == 'repeat_image':
            # получаем номер сообщения с картинками (первый из группы)
            for i in message.text.split('\n')[0].split():
                id = int(i)
                break
            p = IMAGE_PROMPTS[id]
            message.text = f'/image {p}'
            # рисуем еще картинки с тем же запросом
            image(message)
        elif call.data == 'voice_repair':
            # реакция на клавиатуру для исправить текст после распознавания
            with ShowAction(message, 'typing'):
                translated = my_bard.bard_clear_text_chunk_voice(message.text)
            if translated and translated != message.text:
                bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=translated,
                                      reply_markup=get_keyboard('translate', message))
                # bot.reply_to(message, translated, reply_markup=get_keyboard('translate', message))
        elif call.data == 'translate':
            # реакция на клавиатуру для OCR кнопка перевести текст
            with ShowAction(message, 'typing'):
                translated = my_trans.translate_text2(message.text)
            if translated and translated != message.text:
                bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=translated, 
                                      reply_markup=get_keyboard('translate', message))
        elif call.data == 'translate_perplexity':
            # реакция на клавиатуру для OCR кнопка перевести текст
            with ShowAction(message, 'typing'):
                translated = my_trans.translate_text2(message.text)
            if translated and translated != message.text:
                bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=translated, 
                                      reply_markup=get_keyboard('perplexity', message))
        elif call.data == 'translate_chat':
            # реакция на клавиатуру для Чата кнопка перевести текст
            with ShowAction(message, 'typing'):
                translated = my_trans.translate_text2(message.text)
            if translated and translated != message.text:
                bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=translated, 
                                      reply_markup=get_keyboard('chat', message))
        elif call.data == 'bardAI_reset':
            my_bard.reset_bard_chat(chat_id_full)
            msg = 'История диалога с бардом отчищена.'
            bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, msg)
        elif call.data == 'claudeAI_reset':
            my_claude.reset_claude_chat(chat_id_full)
            msg = 'История диалога с клодом отчищена.'
            bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, msg)
        elif call.data == 'chatGPT_reset':
            DIALOGS_DB[chat_id_full] = []
            msg = 'История диалога с chatGPT отчищена.'
            bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, msg)
        elif call.data == 'bingAI_reset':
            bingai.reset_bing_chat(chat_id_full)
            msg = 'История диалога с бингом отчищена.'
            bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, msg)
        elif call.data == 'tts_female':
            TTS_GENDER[chat_id_full] = 'male'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'tts_male':
            TTS_GENDER[chat_id_full] = 'google_female'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'tts_google_female':
            TTS_GENDER[chat_id_full] = 'silero_xenia'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'tts_silero_xenia':
            TTS_GENDER[chat_id_full] = 'silero_aidar'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'tts_silero_aidar':
            TTS_GENDER[chat_id_full] = 'female'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'voice_only_mode_disable':
            VOICE_ONLY_MODE[chat_id_full] = False
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'voice_only_mode_enable':
            VOICE_ONLY_MODE[chat_id_full] = True
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'chatGPT_mode_disable':
            del CHAT_MODE[chat_id_full]
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'chatGPT_mode_enable':
            CHAT_MODE[chat_id_full] = 'chatgpt'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'bing_mode_enable':
            CHAT_MODE[chat_id_full] = 'bing'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'bing_mode_disable':
            del CHAT_MODE[chat_id_full]
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'bard_mode_enable':
            CHAT_MODE[chat_id_full] = 'bard'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'bard_mode_disable':
            del CHAT_MODE[chat_id_full]
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'claude_mode_enable':
            CHAT_MODE[chat_id_full] = 'claude'
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'claude_mode_disable':
            del CHAT_MODE[chat_id_full]
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'autotranslate_disable':
            BLOCKS[chat_id_full] = 0
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'autotranslate_enable':
            BLOCKS[chat_id_full] = 1
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'chatGPT_memory_debug':
            send_debug_history(message)
        elif call.data.startswith('tts_book:'):
            lang = BOOKS[chat_id_full][1]
            name = BOOKS[chat_id_full][2]

            if 'get_text' in call.data:
                text = ''.join(BOOKS[chat_id_full][0])
                reply_to_long_message(message, text)
                return

            chunk_number = int(call.data.split(':')[1])
            text = BOOKS[chat_id_full][0][chunk_number]

            message.text = f'/tts {lang} {text}'
            tts(message, f'Книга: {name}\n\nЧасть: {chunk_number+1}\n\nЯзык: {lang}')
        elif call.data == 'disable_chat_kbd':
            DISABLED_KBD[chat_id_full] = False
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))
        elif call.data == 'enable_chat_kbd':
            DISABLED_KBD[chat_id_full] = True
            bot.edit_message_text(chat_id=message.chat.id, parse_mode='Markdown', message_id=message.message_id, 
                                  text = MSG_CONFIG, reply_markup=get_keyboard('config', message))


def check_blocks(chat_id: str) -> bool:
    if chat_id not in BLOCKS:
        BLOCKS[chat_id] = 0
    return False if BLOCKS[chat_id] == 1 else True


@bot.message_handler(content_types = ['voice', 'audio'])
def handle_voice(message: telebot.types.Message): 
    """Автоматическое распознавание текст из голосовых сообщений"""
    thread = threading.Thread(target=handle_voice_thread, args=(message,))
    thread.start()
def handle_voice_thread(message: telebot.types.Message):
    """Автоматическое распознавание текст из голосовых сообщений и аудио файлов"""

    my_log.log_media(message)

    is_private = message.chat.type == 'private'
    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)
    if chat_id_full not in SUPER_CHAT:
        SUPER_CHAT[chat_id_full] = 0
    if SUPER_CHAT[chat_id_full] == 1:
        is_private = True

    if check_blocks(get_topic_id(message)) and not is_private:
        return

    with semaphore_talks:
        # Создание временного файла 
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            file_path = temp_file.name
        # Скачиваем аудиофайл во временный файл
        try:
            file_info = bot.get_file(message.voice.file_id)
        except AttributeError:
            file_info = bot.get_file(message.audio.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        # Распознаем текст из аудио
        if chat_id_full in VOICE_ONLY_MODE and VOICE_ONLY_MODE[chat_id_full]:
            action = 'record_audio'
        else:
            action = 'typing'
        with ShowAction(message, action):
            text = my_stt.stt(file_path)

            os.remove(file_path)

            text = text.strip()
            # Отправляем распознанный текст
            if text:
                if VOICE_ONLY_MODE[chat_id_full]:
                    # в этом режиме не показываем распознанный текст а просто отвечаем на него голосом
                    pass
                else:
                    reply_to_long_message(message, text, reply_markup=get_keyboard('translate', message))
                    my_log.log_echo(message, f'[ASR] {text}')
            else:
                if VOICE_ONLY_MODE[chat_id_full]:
                    message.text = '/tts ' + 'Очень интересно, но ничего не понятно.'
                    tts(message)
                else:
                    bot.reply_to(message, 'Очень интересно, но ничего не понятно.', reply_markup=get_keyboard('hide', message))
                    my_log.log_echo(message, '[ASR] no results')

            # и при любом раскладе отправляем текст в обработчик текстовых сообщений, возможно бот отреагирует на него если там есть кодовые слова
            if text:
                message.text = text
                echo_all(message)


@bot.message_handler(content_types = ['document'])
def handle_document(message: telebot.types.Message):
    """Обработчик документов"""
    thread = threading.Thread(target=handle_document_thread, args=(message,))
    thread.start()
def handle_document_thread(message: telebot.types.Message):
    """Обработчик документов"""

    my_log.log_media(message)

    chat_id_full = get_topic_id(message)

    is_private = message.chat.type == 'private'
    if chat_id_full not in SUPER_CHAT:
        SUPER_CHAT[chat_id_full] = 0
    if SUPER_CHAT[chat_id_full] == 1:
        is_private = True

    chat_id = message.chat.id

    if check_blocks(chat_id_full) and not is_private:
        return

    with semaphore_talks:
        # если в режиме клауда чата то закидываем файл прямо в него
        if chat_id_full in CHAT_MODE and CHAT_MODE[chat_id_full] == 'claude':
            check_blocked_user(chat_id_full)
            with ShowAction(message, 'typing'):
                file_name = message.document.file_name
                file_info = bot.get_file(message.document.file_id)
                file = bot.download_file(file_info.file_path)
                # сгенерировать случайное имя папки во временной папке для этого файла
                folder_name = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
                # создать эту папку во временной папке. как получить путь до временной папки в системе?
                folder_path = os.path.join(tempfile.gettempdir(), folder_name)
                os.mkdir(folder_path)
                # сохранить файл в этой папке
                if file_name.endswith(('.pdf', '.txt')):
                    full_path = os.path.join(folder_path, file_name)
                    with open(full_path, 'wb') as new_file:
                        new_file.write(file)
                else:
                    file_name += '.txt'
                    text = my_pandoc.fb2_to_text(file)
                    full_path = os.path.join(folder_path, file_name)
                    with open(full_path, 'w', encoding='utf-8') as new_file:
                        new_file.write(text)
                caption = message.caption or 'Вот файл'
                message.text = f'[File uploaded for Claude] [{file_name}] ' + caption
                my_log.log_echo(message)
                try:
                    response = my_claude.chat(caption, chat_id_full, False, full_path)
                    response = utils.bot_markdown_to_html(response)
                except Exception as error:
                    print(f'tb:handle_document_thread:claude: {error}')
                    my_log.log2(f'tb:handle_document_thread:claude: {error}')
                    msg = f'Что-то пошло не так'
                    bot.reply_to(message, msg)
                    my_log.log2(msg)
                    os.remove(full_path)
                    os.rmdir(folder_path)
                    return
                # удалить сначала файл а потом и эту папку
                os.remove(full_path)
                os.rmdir(folder_path)
                my_log.log_echo(message, response)
                reply_to_long_message(message, response, parse_mode='HTML', reply_markup=get_keyboard('claude_chat', message))
            return

        # если прислали fb2 в приват то озвучить ее (msword)
        mimes = ('fictionbook', 'epub' ,'plain' , 'vnd.openxmlformats-officedocument.wordprocessingml.document',
                 'html', 'msword', 'vnd.oasis.opendocument.text', 'rtf', 'x-mobipocket-ebook')
        if is_private and any([x for x in mimes if x in message.document.mime_type]):
            check_blocked_user(chat_id_full)
            with ShowAction(message, 'typing'):
                file_name = message.document.file_name
                file_info = bot.get_file(message.document.file_id)
                file = bot.download_file(file_info.file_path)
                text = my_pandoc.fb2_to_text(file)
                if text:
                    try:
                        lang = detect_langs(text)[0].lang
                    except Exception as error_fb2:
                        lang = 'ru'
                        print(f'tb:handle_document_thread:fb2: {error_fb2}')
                        my_log.log2(f'tb:handle_document_thread:fb2: {error_fb2}')

                    chunks = my_pandoc.split_text_of_book(text, 40000)
                    BOOKS[chat_id_full] = (chunks, lang, file_name)
                    msg = f'Книга\n\n{file_name}\n\nОзвучивание занимает много времени\n\nВсего символов {len(text)}, язык: {lang}, количество частей: {len(chunks)}'
                    bot.reply_to(message, msg, reply_markup=get_keyboard('book_tts', message))
            return

        # если прислали текстовый файл или pdf с подписью перескажи
        # то скачиваем и вытаскиваем из них текст и показываем краткое содержание
        if message.caption \
        and message.caption.startswith(('что там','перескажи','краткое содержание', 'кратко')) \
        and message.document.mime_type in ('text/plain', 'application/pdf'):
            check_blocked_user(chat_id_full)
            with ShowAction(message, 'typing'):
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                file_bytes = io.BytesIO(downloaded_file)
                text = ''
                if message.document.mime_type == 'application/pdf':
                    pdf_reader = PyPDF2.PdfReader(file_bytes)
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                elif message.document.mime_type == 'text/plain':
                    text = file_bytes.read().decode('utf-8')

                if text.strip():
                    summary = my_sum.summ_text(text)
                    reply_to_long_message(message, summary, parse_mode='',
                                          disable_web_page_preview = True,
                                          reply_markup=get_keyboard('translate', message))
                    my_log.log_echo(message, summary)
                else:
                    help = 'Не удалось получить никакого текста из документа.'
                    bot.reply_to(message, help, reply_markup=get_keyboard('hide', message))
                    my_log.log_echo(message, help)
                return

        # начитываем текстовый файл только если его прислали в привате или с указанием прочитай/читай
        caption = message.caption or ''
        if is_private or caption.lower() in ['прочитай', 'читай']:
            check_blocked_user(chat_id_full)
            # если текстовый файл то пытаемся озвучить как книгу. русский голос
            if message.document.mime_type == 'text/plain':
                with ShowAction(message, 'record_audio'):
                    file_name = message.document.file_name + '.ogg'
                    file_info = bot.get_file(message.document.file_id)
                    file = bot.download_file(file_info.file_path)
                    text = file.decode('utf-8')
                    try:
                        lang = detect_langs(text)[0].lang
                    except Exception as error2:
                        lang = 'ru'
                        print(error2)
                    # Озвучиваем текст
                    if chat_id_full in TTS_GENDER:
                        gender = TTS_GENDER[chat_id_full]
                    else:
                        gender = 'female'    
                    audio = my_tts.tts(text, lang, gender=gender)
                    if not is_private:
                        bot.send_voice(chat_id, audio, reply_to_message_id=message.message_id, reply_markup=get_keyboard('hide', message))
                    else:
                        bot.send_voice(chat_id, audio, reply_markup=get_keyboard('hide', message))
                    my_log.log_echo(message, f'[tts file] {text}')
                    return

        # дальше идет попытка распознать ПДФ или jpg файл, вытащить текст с изображений
        if is_private or caption.lower() in ['прочитай', 'читай']:
            check_blocked_user(chat_id_full)
            with ShowAction(message, 'upload_document'):
                # получаем самый большой документ из списка
                document = message.document
                # если документ не является PDF-файлом или изображением jpg png, отправляем сообщение об ошибке
                if document.mime_type in ('image/jpeg', 'image/png'):
                    with ShowAction(message, 'typing'):
                        # скачиваем документ в байтовый поток
                        file_id = message.document.file_id
                        file_info = bot.get_file(file_id)
                        file_name = message.document.file_name + '.jpg'
                        file = bot.download_file(file_info.file_path)
                        fp = io.BytesIO(file)
                        # распознаем текст на фотографии с помощью pytesseract
                        text = my_ocr.get_text_from_image(fp.read(), get_ocr_language(message))
                        # отправляем распознанный текст пользователю
                        if text.strip() != '':
                            reply_to_long_message(message, text, parse_mode='',
                                                  reply_markup=get_keyboard('translate', message),
                                                  disable_web_page_preview = True)
                            my_log.log_echo(message, '[OCR] ' + text)
                        else:
                            reply_to_long_message(message, 'Не смог распознать текст.', reply_markup=get_keyboard('translate', message))
                            my_log.log_echo(message, '[OCR] no results')
                    return
                if document.mime_type != 'application/pdf':
                    bot.reply_to(message, f'Это не PDF-файл. {document.mime_type}', reply_markup=get_keyboard('hide', message))
                    my_log.log_echo(message, f'Это не PDF-файл. {document.mime_type}')
                    return
                # скачиваем документ в байтовый поток
                file_id = message.document.file_id
                file_info = bot.get_file(file_id)
                file_name = message.document.file_name + '.txt'
                file = bot.download_file(file_info.file_path)
                fp = io.BytesIO(file)

                # распознаем текст в документе с помощью функции get_text
                text = my_ocr.get_text(fp, get_ocr_language(message))
                # отправляем распознанный текст пользователю
                if text.strip() != '':
                    # если текст слишком длинный, отправляем его в виде текстового файла
                    if len(text) > 4096:
                        with io.StringIO(text) as f:
                            if not is_private:
                                bot.send_document(chat_id, document = f, visible_file_name = file_name, caption=file_name, 
                                                  reply_to_message_id = message.message_id, reply_markup=get_keyboard('hide', message))
                            else:
                                bot.send_document(chat_id, document = f, visible_file_name = file_name, caption=file_name, 
                                                  reply_markup=get_keyboard('hide', message))
                    else:
                        bot.reply_to(message, text, reply_markup=get_keyboard('translate', message))
                    my_log.log_echo(message, f'[распознанный из PDF текст] {text}')


@bot.message_handler(content_types = ['photo'])
def handle_photo(message: telebot.types.Message):
    """Обработчик фотографий. Сюда же попадают новости которые создаются как фотография + много текста в подписи, и пересланные сообщения в том числе"""
    thread = threading.Thread(target=handle_photo_thread, args=(message,))
    thread.start()
def handle_photo_thread(message: telebot.types.Message):
    """Обработчик фотографий. Сюда же попадают новости которые создаются как фотография + много текста в подписи, и пересланные сообщения в том числе"""

    my_log.log_media(message)

    chat_id_full = get_topic_id(message)

    is_private = message.chat.type == 'private'
    if chat_id_full not in SUPER_CHAT:
        SUPER_CHAT[chat_id_full] = 0
    if SUPER_CHAT[chat_id_full] == 1:
        is_private = True

    if check_blocks(get_topic_id(message)) and not is_private and message.caption not in ('ocr', 'прочитай'):
        return

    with semaphore_talks:
        # пересланные сообщения пытаемся перевести даже если в них картинка
        # новости в телеграме часто делают как картинка + длинная подпись к ней
        if message.forward_from_chat and message.caption:
            # у фотографий нет текста но есть заголовок caption. его и будем переводить
            check_blocked_user(chat_id_full)
            with ShowAction(message, 'typing'):
                text = my_trans.translate(message.caption)
            if text:
                bot.reply_to(message, text, reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, text)
            else:
                my_log.log_echo(message, """Не удалось/понадобилось перевести.""")
            return

        # распознаем текст только если есть команда для этого или если прислали в приват
        if not message.caption and not is_private: return
        if not is_private and not gpt_basic.detect_ocr_command(message.caption.lower()): return

        with ShowAction(message, 'typing'):
            check_blocked_user(chat_id_full)
            # получаем самую большую фотографию из списка
            photo = message.photo[-1]
            fp = io.BytesIO()
            # скачиваем фотографию в байтовый поток
            file_info = bot.get_file(photo.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            fp.write(downloaded_file)
            fp.seek(0)
            # распознаем текст на фотографии с помощью pytesseract
            text = my_ocr.get_text_from_image(fp.read(), get_ocr_language(message))
            # отправляем распознанный текст пользователю
            if text.strip() != '':
                reply_to_long_message(message, text, parse_mode='', reply_markup=get_keyboard('translate', message), disable_web_page_preview = True)
                my_log.log_echo(message, '[OCR] ' + text)
            else:
                my_log.log_echo(message, '[OCR] no results')


@bot.message_handler(content_types = ['video', 'video_note'])
def handle_video(message: telebot.types.Message):
    """Обработчик видеосообщений. Сюда же относятся новости и репосты с видео"""
    thread = threading.Thread(target=handle_video_thread, args=(message,))
    thread.start()
def handle_video_thread(message: telebot.types.Message):
    """Обработчик видеосообщений. Сюда же относятся новости и репосты с видео"""

    my_log.log_media(message)

    chat_id_full = get_topic_id(message)

    is_private = message.chat.type == 'private'
    if chat_id_full not in SUPER_CHAT:
        SUPER_CHAT[chat_id_full] = 0
    if SUPER_CHAT[chat_id_full] == 1:
        is_private = True

    if check_blocks(get_topic_id(message)) and not is_private:
        return

    with semaphore_talks:
        # пересланные сообщения пытаемся перевести даже если в них видео
        if message.forward_from_chat:
            check_blocked_user(chat_id_full)
            # у видео нет текста но есть заголовок caption. его и будем переводить
            text = my_trans.translate(message.caption)
            if text:
                bot.reply_to(message, text, reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, text)
            else:
                my_log.log_echo(message, """Не удалось/понадобилось перевести.""")

    with semaphore_talks:
        with ShowAction(message, 'typing'):
            check_blocked_user(chat_id_full)
            # Создание временного файла 
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                file_path = temp_file.name
            # Скачиваем аудиофайл во временный файл
            try:
                file_info = bot.get_file(message.video.file_id)
            except AttributeError:
                file_info = bot.get_file(message.video_note.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            # Распознаем текст из аудио 
            text = my_stt.stt(file_path)
            os.remove(file_path)
            # Отправляем распознанный текст
            if text:
                reply_to_long_message(message, text, reply_markup=get_keyboard('translate', message))
                my_log.log_echo(message, f'[ASR] {text}')
            else:
                bot.reply_to(message, 'Очень интересно, но ничего не понятно.', reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, '[ASR] no results')


def is_for_me(cmd: str):
    """Checks who the command is addressed to, this bot or another one.
    
    /cmd@botname args
    
    Returns (True/False, 'the same command but without the bot name').
    If there is no bot name at all, assumes that the command is addressed to this bot.
    """
    command_parts = cmd.split()
    first_arg = command_parts[0]

    if '@' in first_arg:
        message_cmd = first_arg.split('@', maxsplit=1)[0]
        message_bot = first_arg.split('@', maxsplit=1)[1] if len(first_arg.split('@', maxsplit=1)) > 1 else ''
        message_args = cmd.split(maxsplit=1)[1] if len(command_parts) > 1 else ''
        return (message_bot == _bot_name, f'{message_cmd} {message_args}'.strip())
    else:
        return (True, cmd)


@bot.message_handler(commands=['config'])
def config(message: telebot.types.Message):
    """Меню настроек"""
    # не обрабатывать команды к другому боту /cmd@botname args
    try:
        if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
        else: return
    except Exception as error:
        my_log.log2(f'config:{error}')

    my_log.log_echo(message)

    try:
        bot.reply_to(message, MSG_CONFIG, parse_mode='Markdown', reply_markup=get_keyboard('config', message))
    except Exception as error:
        my_log.log2(f'tb:config:{error}')
        print(error)


@bot.message_handler(commands=['style'])
def change_mode(message: telebot.types.Message):
    """Меняет роль бота, строку с указаниями что и как говорить.
    /stype <1|2|3|свой текст>
    1 - формальный стиль (Ты искусственный интеллект отвечающий на запросы юзера.)
    2 - формальный стиль + немного юмора (Ты искусственный интеллект отвечающий на запросы юзера. Отвечай с подходящим к запросу типом иронии или юмора но не перегибай палку.)
    3 - токсичный стиль (Ты искусственный интеллект отвечающий на запросы юзера. Отвечай с сильной иронией и токсичностью.)
    """

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    # в каждом чате свой собственный промт
    if chat_id_full not in PROMPTS:
        # по умолчанию формальный стиль
        PROMPTS[chat_id_full] = [{"role": "system", "content": utils.gpt_start_message1}]

    arg = message.text.split(maxsplit=1)[1:]
    if arg:
        if arg[0] == '1':
            new_prompt = utils.gpt_start_message1
        elif arg[0] == '2':
            new_prompt = utils.gpt_start_message2
        elif arg[0] == '3':
            new_prompt = utils.gpt_start_message3
        elif arg[0] == '4':
            new_prompt = utils.gpt_start_message4
        else:
            new_prompt = arg[0]
        PROMPTS[chat_id_full] =  [{"role": "system", "content": new_prompt}]
        msg =  f'[Новая роль установлена] `{new_prompt}`\n\n***Роли работают только с chatGPT, используйте команду /config что бы выбрать chatGPT***'
        bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, msg)
    else:
        msg = f"""Текущий стиль

`{PROMPTS[chat_id_full][0]['content']}`

Меняет роль бота, строку с указаниями что и как говорить. Работает только для ChatGPT.

***Роли работают только с chatGPT, используйте команду /config что бы выбрать chatGPT***

`/style <1|2|3|4|свой текст>`

1 - формальный стиль `{utils.gpt_start_message1}`

2 - формальный стиль + немного юмора `{utils.gpt_start_message2}`

3 - токсичный стиль `{utils.gpt_start_message3}`

4 - Ева Элфи `{utils.gpt_start_message4}`

Напишите свой текст или цифру одного из готовых стилей
    """
        COMMAND_MODE[chat_id_full] = 'style'
        bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=get_keyboard('command_mode', message))
        my_log.log_echo(message, msg)


@bot.message_handler(commands=['mem'])
def send_debug_history(message: telebot.types.Message):
    """
    Отправляет текущую историю сообщений пользователю.
    """

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    
    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    # создаем новую историю диалогов с юзером из старой если есть
    messages = []
    if chat_id_full in DIALOGS_DB:
        messages = DIALOGS_DB[chat_id_full]
    prompt = '\n'.join(f'{i["role"]} - {i["content"]}\n' for i in messages) or 'Пусто'
    my_log.log_echo(message, prompt)
    reply_to_long_message(message, prompt, parse_mode = '', disable_web_page_preview = True, reply_markup=get_keyboard('mem', message))


@bot.message_handler(commands=['restart']) 
def restart(message: telebot.types.Message):
    """остановка бота. после остановки его должен будет перезапустить скрипт systemd"""
    if message.from_user.id in cfg.admins:
        bot.stop_polling()
    else:
        bot.reply_to(message, 'Эта команда только для админов.', reply_markup=get_keyboard('hide', message))


@bot.message_handler(commands=['temperature', 'temp'])
def set_new_temperature(message: telebot.types.Message):
    """меняет температуру для chatGPT
    /temperature <0...2>
    по умолчанию 0 - автоматическая
    чем меньше температура тем менее творчейский ответ, меньше бреда и вранья,
    и желания давать ответ
    """

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    if len(message.text.split()) == 2:
        try:
            new_temp = float(message.text.split()[1])
        except ValueError:
            new_temp = -1
    else:
        new_temp = -1

    if new_temp < 0 or new_temp > 2:
        new_temp = -1

    if len(message.text.split()) < 2 or new_temp == -1:
        help = """/temperature <0-1>

меняет температуру для chatGPT

Температура у ChatGPT - это параметр, который контролирует степень случайности генерируемого текста. Чем выше температура, тем более случайным и креативным будет текст. Чем ниже температура, тем более точным и сфокусированным будет текст.

Например, если вы хотите, чтобы ChatGPT сгенерировал стихотворение, вы можете установить температуру выше 1,5. Это будет способствовать тому, что ChatGPT будет выбирать более неожиданные и уникальные слова. Однако, если вы хотите, чтобы ChatGPT сгенерировал текст, который является более точным и сфокусированным, вы можете установить температуру ниже 0,5. Это будет способствовать тому, что ChatGPT будет выбирать более вероятные и ожидаемые слова.

По-умолчанию 0 - автоматическая

`/temperature 0.1`
`/temperature 1`
`/temperature 1.9` На таких высоких значения он пишет один сплошной бред
"""
        bot.reply_to(message, help, parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
        return

    TEMPERATURE[chat_id_full] = new_temp
    bot.reply_to(message, f'Новая температура для chatGPT установлена: {new_temp}', parse_mode='Markdown',
                 reply_markup=get_keyboard('hide', message))


@bot.message_handler(commands=['model'])
def set_new_model(message: telebot.types.Message):
    """меняет модель для гпт, никаких проверок не делает"""

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    if chat_id_full in gpt_basic.CUSTOM_MODELS:
        current_model = gpt_basic.CUSTOM_MODELS[chat_id_full]
    else:
        current_model = cfg.model

    if len(message.text.split()) < 2:
        available_models = ''
        for m in gpt_basic.get_list_of_models():
            available_models += f'`/model {m}`\n'
        msg = f"""Меняет модель для chatGPT.

Выбрано: `/model {current_model}`

Возможные варианты (на самом деле это просто примеры а реальные варианты зависят от настроек бота, его бекэндов):

`/model gpt-4`
`/model gpt-3.5-turbo-16k`

{available_models}
"""
        bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=get_keyboard('hide', message)) 
        my_log.log_echo(message, msg)
        return

    if not (message.from_user.id in cfg.admins or is_admin_member(message)):
       msg = 'Эта команда только для админов.'
       bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
       my_log.log_echo(message, msg)
       return

    model = message.text.split()[1]
    msg0 = f'Старая модель `{current_model}`.'
    msg = f'Установлена новая модель `{model}`.'
    gpt_basic.CUSTOM_MODELS[chat_id_full] = model
    bot.reply_to(message, msg0, parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
    bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
    my_log.log_echo(message, msg0)
    my_log.log_echo(message, msg)


@bot.message_handler(commands=['wikipedia','wiki']) 
def wikipedia(message: telebot.types.Message):
    """показывает текст из википедии"""
    thread = threading.Thread(target=wikipedia_thread, args=(message,))
    thread.start()
def wikipedia_thread(message: telebot.types.Message):
    """показывает текст из википедии"""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    args = message.text.split(maxsplit=1)
    if len(args) == 2:
        query = args[1]
        with semaphore_talks:
            with ShowAction(message, 'typing'):
                result = my_wikipedia.get_content(query)
                reply_to_long_message(message, result, parse_mode='HTML', reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, result)
    else:
        msg = '/wikipedia <что найти>'
        bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, msg)


@bot.message_handler(commands=['tts']) 
def tts(message: telebot.types.Message, caption = None):
    thread = threading.Thread(target=tts_thread, args=(message,caption))
    thread.start()
def tts_thread(message: telebot.types.Message, caption = None):
    """ /tts [ru|en|uk|...] [+-XX%] <текст>
        /tts <URL>
    """

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    urls = re.findall(r'^/tts\s*(https?://[^\s]+)?$', message.text.lower())

    # обрабатываем урл, просто достаем текст и показываем с клавиатурой для озвучки
    args = message.text.split()
    if len(args) == 2 and my_sum.is_valid_url(args[1]):
        url = args[1]
        if '/youtu.be/' in url or 'youtube.com/' in url:
            text = my_sum.get_text_from_youtube(url)
        else:
            text = my_google.download_text([url, ], 100000, no_links = True)
        if text:
            reply_to_long_message(message, text, parse_mode='',
                                  reply_markup=get_keyboard('translate', message),
                                      disable_web_page_preview=True)
        return

    # разбираем параметры
    # регулярное выражение для разбора строки
    pattern = r'/tts\s+((?P<lang>' + '|'.join(supported_langs_tts) + r')\s+)?\s*(?P<rate>([+-]\d{1,2}%\s+))?\s*(?P<text>.+)'
    # поиск совпадений с регулярным выражением
    match = re.match(pattern, message.text, re.DOTALL)
    # извлечение параметров из найденных совпадений
    if match:
        lang = match.group("lang") or "ru"  # если lang не указан, то по умолчанию 'ru'
        rate = match.group("rate") or "+0%"  # если rate не указан, то по умолчанию '+0%'
        text = match.group("text") or ''
    else:
        text = lang = rate = ''
    lang = lang.strip()
    rate = rate.strip()

    if not text or lang not in supported_langs_tts:
        help = f"""Использование: /tts [ru|en|uk|...] [+-XX%] <текст>|<URL>

+-XX% - ускорение с обязательным указанием направления + или -

/tts привет
/tts en hello, let me speak from all my heart
/tts +50% привет со скоростью 1.5х
/tts uk -50% тянем время, говорим по-русски с украинским акцентом :)

Поддерживаемые языки: {', '.join(supported_langs_tts)}

Напишите что надо произнести, чтобы получить голосовое сообщение
"""

        COMMAND_MODE[chat_id_full] = 'tts'
        bot.reply_to(message, help, parse_mode='Markdown', reply_markup=get_keyboard('command_mode', message))
        my_log.log_echo(message, help)
        return

    with semaphore_talks:
        with ShowAction(message, 'record_audio'):
            if chat_id_full in TTS_GENDER:
                gender = TTS_GENDER[chat_id_full]
            else:
                gender = 'female'

            # микрософт не умеет в латинский язык
            if lang == 'la':
                gender = 'google_female'

            # это голоса только по русски могут
            if gender == 'silero_xenia' and lang != 'ru':
                gender = 'female'
            if gender == 'silero_aidar' and lang != 'ru':
                gender = 'male'

            if chat_id_full in VOICE_ONLY_MODE and VOICE_ONLY_MODE[chat_id_full]:
                text = utils.bot_markdown_to_tts(text)
            audio = my_tts.tts(text, lang, rate, gender=gender)
            if audio:
                if message.chat.type != 'private':
                    bot.send_voice(message.chat.id, audio, reply_to_message_id = message.message_id,
                                   reply_markup=get_keyboard('hide', message), caption=caption)
                else:
                    # в привате не надо добавлять клавиатуру с кнопкой для удаления, 
                    # там можно удалить без нее, а случайное удаление ни к чему
                    bot.send_voice(message.chat.id, audio, caption=caption)
                my_log.log_echo(message, '[Отправил голосовое сообщение]')
            else:
                msg = 'Не удалось озвучить. Возможно вы перепутали язык, например немецкий голос не читает по-русски.'
                if message.chat.type != 'private':
                    bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
                else:
                    bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
                    my_log.log_echo(message, msg)


@bot.message_handler(commands=['ask', 'perplexity'])
def ask(message: telebot.types.Message):
    thread = threading.Thread(target=ask_thread, args=(message,))
    thread.start()
def ask_thread(message: telebot.types.Message):
    """ищет в perplexity.ai ответ"""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    try:
        query = message.text.split(maxsplit=1)[1]
    except Exception as error2:
        print(error2)
        help = """/ask <текст запроса>

Нажмите ***Отмена*** что бы выйти из режима поиска

Напишите что надо найти в интернете:
"""
        COMMAND_MODE[chat_id_full] = 'perplexity'
        bot.reply_to(message, help, parse_mode = 'Markdown', disable_web_page_preview = True, reply_markup=get_keyboard('command_mode', message))
        return

    with ShowAction(message, 'typing'):
        with semaphore_talks:
            try:
                response = my_perplexity.ask(query)
            except Exception as error2:
                my_log.log2(f'tb:ask: {error2}')
                f'tb:ask: {error2}'
                response = ''
        if not response:
            bot.reply_to(message, 'Интернет вам не ответил, перезвоните позже', parse_mode = '', disable_web_page_preview = True, reply_markup=get_keyboard('command_mode', message))
            return
        try:
            reply_to_long_message(message, response, parse_mode = 'HTML', disable_web_page_preview = True, reply_markup=get_keyboard('perplexity', message))
        except Exception as error2:
            my_log.log2(error2)
            reply_to_long_message(message, response, parse_mode = '', disable_web_page_preview = True, reply_markup=get_keyboard('perplexity', message))
        my_log.log_echo(message, response)

        if chat_id_full not in DIALOGS_DB:
            DIALOGS_DB[chat_id_full] = []
        DIALOGS_DB[chat_id_full] += [{"role":    'system',
                                   "content": f'user попросил сделать запрос в Интернет: {query}'},
                                     {"role":    'system',
                                   "content": f'assistant поискал в интернете и ответил: {response}'}
                                ]


@bot.message_handler(commands=['google',])
def google(message: telebot.types.Message):
    thread = threading.Thread(target=google_thread, args=(message,))
    thread.start()
def google_thread(message: telebot.types.Message):
    """ищет в гугле перед ответом"""

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    try:
        q = message.text.split(maxsplit=1)[1]
    except Exception as error2:
        print(error2)
        help = """/google текст запроса

Будет делать запрос в гугл, и потом пытаться найти нужный ответ в результатах

/google курс биткоина, прогноз на ближайшее время

/google текст песни малиновая лада

/google кто звонил +69997778888, из какой страны

Можно попробовать сделать запрос в гугл и добавить указание что делать с найденным боту, но не факт что это нормально сработает. Текст запроса будет целиком передан в гугол и дополнительные инструкции могут испортить результат поиска.

вместо команды /google можно написать кодовое слово гугл в начале

гугл, сколько на земле людей, точные цифры и прогноз

Напишите запрос в гугл
"""
        COMMAND_MODE[chat_id_full] = 'google'
        bot.reply_to(message, help, parse_mode = 'Markdown', disable_web_page_preview = True, reply_markup=get_keyboard('command_mode', message))
        return

    with ShowAction(message, 'typing'):
        with semaphore_talks:
            r = my_google.search(q)
        try:
            bot.reply_to(message, r, parse_mode = 'Markdown', disable_web_page_preview = True, reply_markup=get_keyboard('chat', message))
        except Exception as error2:
            my_log.log2(error2)
            bot.reply_to(message, r, parse_mode = '', disable_web_page_preview = True, reply_markup=get_keyboard('chat', message))
        my_log.log_echo(message, r)

        if chat_id_full not in DIALOGS_DB:
            DIALOGS_DB[chat_id_full] = []
        DIALOGS_DB[chat_id_full] += [{"role":    'system',
                                   "content": f'user попросил сделать запрос в Google: {q}'},
                                     {"role":    'system',
                                   "content": f'assistant поискал в Google и ответил: {r}'}
                                ]


@bot.message_handler(commands=['ddg',])
def ddg(message: telebot.types.Message):
    thread = threading.Thread(target=ddg_thread, args=(message,))
    thread.start()
def ddg_thread(message: telebot.types.Message):
    """ищет в DuckDuckGo перед ответом"""

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    try:
        q = message.text.split(maxsplit=1)[1]
    except Exception as error2:
        print(error2)
        help = """/ddg текст запроса

Будет делать запрос в DuckDuckGo, и потом пытаться найти нужный ответ в результатах

/ddg курс биткоина, прогноз на ближайшее время

/ddg текст песни малиновая лада

/ddg кто звонил +69997778888, из какой страны

Можно попробовать сделать запрос в гугл и добавить указание что делать с найденным боту, но не факт что это нормально сработает. Текст запроса будет целиком передан в гугол и дополнительные инструкции могут испортить результат поиска.

вместо команды /ddg можно написать кодовое слово утка в начале

утка, сколько на земле людей, точные цифры и прогноз

Напишите свой запрос в DuckDuckGo
"""
        COMMAND_MODE[chat_id_full] = 'ddg'
        bot.reply_to(message, help, parse_mode = 'Markdown', disable_web_page_preview = True, reply_markup=get_keyboard('command_mode', message))
        return

    with ShowAction(message, 'typing'):
        with semaphore_talks:
            r = my_google.search_ddg(q)
        try:
            bot.reply_to(message, r, parse_mode = 'Markdown', disable_web_page_preview = True, reply_markup=get_keyboard('chat', message))
        except Exception as error2:
            my_log.log2(error2)
            bot.reply_to(message, r, parse_mode = '', disable_web_page_preview = True, reply_markup=get_keyboard('chat', message))
        my_log.log_echo(message, r)
        
        if chat_id_full not in DIALOGS_DB:
            DIALOGS_DB[chat_id_full] = []
        DIALOGS_DB[chat_id_full] += [{"role":    'system',
                                   "content": f'user попросил сделать запрос в Google: {q}'},
                                     {"role":    'system',
                                   "content": f'assistant поискал в Google и ответил: {r}'}
                                ]


@bot.message_handler(commands=['image','img'])
def image(message: telebot.types.Message):
    thread = threading.Thread(target=image_thread, args=(message,))
    thread.start()
def image_thread(message: telebot.types.Message):
    """генерирует картинку по описанию"""

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    with semaphore_talks:
        help = """/image <текстовое описание картинки, что надо нарисовать>

Напишите что надо нарисовать, как это выглядит
"""
        is_private = message.chat.type == 'private'

        prompt = message.text.split(maxsplit = 1)
        if len(prompt) > 1:
            prompt = prompt[1]
            with ShowAction(message, 'upload_photo'):
                is_porn = gpt_basic.is_image_prompt_about_porn(prompt)
                if is_porn and (0==1): # слишком сильно давит на процессор, отключено пока
                    images = my_p_hub.get_screenshots(prompt)
                    medias = images
                else:
                    images = my_genimg.gen_images(prompt)
                    medias = [telebot.types.InputMediaPhoto(i) for i in images]
                if len(medias) > 0:
                    msgs_ids = bot.send_media_group(message.chat.id, medias, reply_to_message_id=message.message_id)
                    if pics_group:
                        try:
                            bot.send_message(cfg.pics_group, prompt, disable_web_page_preview = True)
                            bot.send_media_group(pics_group, medias)
                        except Exception as error2:
                            print(error2)
                    caption = ''
                    # запоминаем промпт по ключу (номер первой картинки) и сохраняем в бд запрос и картинки
                    # что бы можно было их потом просматривать отдельно
                    IMAGE_PROMPTS[msgs_ids[0].message_id] = prompt

                    for i in msgs_ids:
                        caption += f'{i.message_id} '
                    caption += '\n'
                    if not is_porn:
                        caption += ', '.join([f'<a href="{x}">PIC</a>' for x in images])
                    bot.reply_to(message, caption, parse_mode = 'HTML', disable_web_page_preview = True, 
                    reply_markup=get_keyboard('hide_image', message))
                    my_log.log_echo(message, '[image gen] ')

                    n = [{'role':'system', 'content':f'user попросил нарисовать\n{prompt}'}, {'role':'system', 'content':'assistant нарисовал с помощью DALL-E'}]
                    if chat_id_full in DIALOGS_DB:
                        DIALOGS_DB[chat_id_full] += n
                    else:
                        DIALOGS_DB[chat_id_full] = n
                    
                else:
                    bot.reply_to(message, 'Не смог ничего нарисовать. Может настроения нет, а может надо другое описание дать.', 
                    reply_markup=get_keyboard('hide', message))
                    my_log.log_echo(message, '[image gen error] ')
                    n = [{'role':'system', 'content':f'user попросил нарисовать\n{prompt}'}, {'role':'system', 'content':'assistant не захотел или не смог нарисовать это с помощью DALL-E'}]
                    if chat_id_full in DIALOGS_DB:
                        DIALOGS_DB[chat_id_full] += n
                    else:
                        DIALOGS_DB[chat_id_full] = n
        else:
            COMMAND_MODE[chat_id_full] = 'image'
            bot.reply_to(message, help, parse_mode = 'Markdown', reply_markup=get_keyboard('command_mode', message))
            my_log.log_echo(message, help)


@bot.message_handler(commands=['flip'])
def flip_text(message: telebot.types.Message):
    """эхо с переворотом текста вверх ногами"""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    text = message.text[6:]
    if text:
        bot.reply_to(message, utils.flip_text(text), reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, utils.flip_text(text))
    else:
        msg = '/flip текст который надо qɯʎнdǝʚǝdǝu'
        bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, msg)


@bot.message_handler(commands=['stats'])
def stats(message: telebot.types.Message):
    """Показывает статистику использования бота."""
    thread = threading.Thread(target=stats_thread, args=(message,))
    thread.start()
def stats_thread(message: telebot.types.Message):
    """Показывает статистику использования бота."""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    if message.chat.id in cfg.admins:
        users = [x for x in CHAT_MODE.keys()]
        users_sorted = natsorted(users)
        users_text = '\n'.join(users_sorted) + '\n\nTotal: ' + str(len(users_sorted))
        reply_to_long_message(message, f'Статистика бота:\n\n{users_text}', reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, users_text)
        return
    msg = '/stats показывает статистику бота.\n\nТолько администраторы могут использовать эту команду.'
    bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
    my_log.log_echo(message, msg)


def check_blocked_user(id: str):
    """Вызывает ошибку если юзер заблокирован и ему не надо отвечать"""
    user_id = id.replace('[','').replace(']','').split()[0]
    if not request_counter.check_limit(user_id):
        my_log.log2(f'tb:check_blocked_user: Пользователь {id} заблокирован за DDOS')
        raise Exception(f'user {user_id} in ddos stop list, ignoring')
    for i in BAD_USERS:
        u_id = i.replace('[','').replace(']','').split()[0]
        if u_id == user_id:
            if BAD_USERS[id]:
                my_log.log2(f'tb:check_blocked_user: Пользователь {id} заблокирован')
                raise Exception(f'user {user_id} in stop list, ignoring')


@bot.message_handler(commands=['blockadd'])
def block_user_add(message: telebot.types.Message):
    """Добавить юзера в стоп список"""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    if message.chat.id in cfg.admins:
        user_id = message.text[10:].strip()
        if user_id:
            BAD_USERS[user_id] = True
            bot.reply_to(message, f'Пользователь {user_id} добавлен в стоп-лист', reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, f'Пользователь {user_id} добавлен в стоп-лист')
    else:
        bot.reply_to(message, 'Только администраторы могут использовать эту команду.', reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, 'Только администраторы могут использовать эту команду.')


@bot.message_handler(commands=['blockdel'])
def block_user_del(message: telebot.types.Message):
    """Убрать юзера из стоп списка"""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    if message.chat.id in cfg.admins:
        user_id = message.text[10:].strip()
        if user_id:
            if user_id in BAD_USERS:
                del BAD_USERS[user_id]
                bot.reply_to(message, f'Пользователь {user_id} удален из стоп-листа', reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, f'Пользователь {user_id} удален из стоп-листа')
            else:
                bot.reply_to(message, f'Пользователь {user_id} не найден в стоп-листе', reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, f'Пользователь {user_id} не найден в стоп-листе')
    else:
        bot.reply_to(message, 'Только администраторы могут использовать эту команду.', reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, 'Только администраторы могут использовать эту команду.')


@bot.message_handler(commands=['blocklist'])
def block_user_list(message: telebot.types.Message):
    """Показывает список заблокированных юзеров"""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    if message.chat.id in cfg.admins:
        users = [x for x in BAD_USERS.keys() if x]
        if users:
            reply_to_long_message(message, '\n'.join(users), reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, '\n'.join(users))
    else:
        bot.reply_to(message, 'Только администраторы могут использовать эту команду.', reply_markup=get_keyboard('hide', message))
        my_log.log_echo(message, 'Только администраторы могут использовать эту команду.')


@bot.message_handler(commands=['alert'])
def alert(message: telebot.types.Message):
    """Сообщение всем кого бот знает. CHAT_MODE обновляется при каждом создании клавиатуры, 
       а она появляется в первом же сообщении.
    """
    thread = threading.Thread(target=alert_thread, args=(message,))
    thread.start()
def alert_thread(message: telebot.types.Message):
    """Сообщение всем кого бот знает. CHAT_MODE обновляется при каждом создании клавиатуры, 
       а она появляется в первом же сообщении.
    """
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    if message.chat.id in cfg.admins:
        text = message.text[7:]
        if text:
            text = utils.bot_markdown_to_html(text)
            text = '<b>Широковещательное сообщение от Верховного Адмнистратора, не обращайте внимания</b>\n\n\n' + text

            for x, _ in CHAT_MODE.items():
                x = x.replace('[','').replace(']','')
                chat = int(x.split()[0])
                # if chat not in cfg.admins:
                #     return
                thread = int(x.split()[1])
                try:
                    bot.send_message(chat_id = chat, message_thread_id=thread, text = text, parse_mode='HTML',
                                    disable_notification = True, disable_web_page_preview = True,
                                    reply_markup=get_keyboard('translate', message))
                except Exception as error2:
                    print(f'tb:alert: {error2}')
                    my_log.log2(f'tb:alert: {error2}')
                time.sleep(0.3)
            return

    msg = '/alert <текст сообщения которое бот отправит всем кого знает, форматирование маркдаун>\n\nТолько администраторы могут использовать эту команду.'
    bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
    my_log.log_echo(message, msg)


@bot.message_handler(commands=['qr'])
def qrcode_text(message: telebot.types.Message):
    """переводит текст в qrcode"""
    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)
    text = message.text[3:]
    if text:
        image = utils.text_to_qrcode(text)
        if image:
            bio = io.BytesIO()
            bio.name = 'qr.png'
            image.save(bio, 'PNG')
            bio.seek(0)
            bot.send_photo(chat_id = message.chat.id, message_thread_id = message.message_thread_id, photo=bio,
                           reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, '[QR code]')
            return

    msg = '/qr текст который надо перевести в qrcode'
    bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
    my_log.log_echo(message, msg)


@bot.message_handler(commands=['sum'])
def summ_text(message: telebot.types.Message):
    thread = threading.Thread(target=summ_text_thread, args=(message,))
    thread.start()
def summ_text_thread(message: telebot.types.Message):

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    my_log.log_echo(message)

    text = message.text
    
    if len(text.split(' ', 1)) == 2:
        url = text.split(' ', 1)[1].strip()
        if my_sum.is_valid_url(url):
            # убираем из ютуб урла временную метку
            if '/youtu.be/' in url or 'youtube.com/' in url:
                url = url.split("&t=")[0]

            with semaphore_talks:

                #смотрим нет ли в кеше ответа на этот урл
                r = ''
                if url in SUM_CACHE:
                    r = SUM_CACHE[url]
                if r:
                    reply_to_long_message(message, r, disable_web_page_preview = True, reply_markup=get_keyboard('translate', message))
                    my_log.log_echo(message, r)
                    if chat_id_full not in DIALOGS_DB:
                        DIALOGS_DB[chat_id_full] = []
                    DIALOGS_DB[chat_id_full] += [{"role":    'system',
                                "content": f'user попросил кратко пересказать содержание текста по ссылке/из файла'},
                                {"role":    'system',
                                "content": f'assistant прочитал и ответил: {r}'}
                                ]
                    return

                with ShowAction(message, 'typing'):
                    res = ''
                    try:
                        res = my_sum.summ_url(url)
                    except Exception as error2:
                        print(error2)
                        m = 'Не нашел тут текста. Возможно что в видео на ютубе нет субтитров или страница слишком динамическая и не показывает текст без танцев с бубном, или сайт меня не пускает.\n\nЕсли очень хочется то отправь мне текстовый файл .txt (utf8) с текстом этого сайта и подпиши `что там`'
                        bot.reply_to(message, m, parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
                        my_log.log_echo(message, m)
                        return
                    if res:
                        reply_to_long_message(message, res, parse_mode='',
                                              disable_web_page_preview = True,
                                              reply_markup=get_keyboard('translate', message))
                        my_log.log_echo(message, res)
                        SUM_CACHE[url] = res
                        if chat_id_full not in DIALOGS_DB:
                            DIALOGS_DB[chat_id_full] = []
                        DIALOGS_DB[chat_id_full] += [{"role":    'system',
                                "content": f'user попросил кратко пересказать содержание текста по ссылке/из файла'},
                                {"role":    'system',
                                "content": f'assistant прочитал и ответил: {res}'}
                                ]
                        return
                    else:
                        error = 'Не смог прочитать текст с этой страницы.'
                        bot.reply_to(message, error, reply_markup=get_keyboard('hide', message))
                        my_log.log_echo(message, error)
                        return
    help = """Пример: /sum https://youtu.be/3i123i6Bf-U

Давайте вашу ссылку и я перескажу содержание"""
    COMMAND_MODE[chat_id_full] = 'sum'
    bot.reply_to(message, help, parse_mode = 'Markdown', reply_markup=get_keyboard('command_mode', message))
    my_log.log_echo(message, help)


@bot.message_handler(commands=['sum2'])
def summ2_text(message: telebot.types.Message):
    # убирает запрос из кеша если он там есть и делает запрос снова

    #my_log.log_echo(message)

    text = message.text

    if len(text.split(' ', 1)) == 2:
        url = text.split(' ', 1)[1].strip()
        if my_sum.is_valid_url(url):
            # убираем из ютуб урла временную метку
            if '/youtu.be/' in url or 'youtube.com/' in url:
                url = url.split("&t=")[0]

            #смотрим нет ли в кеше ответа на этот урл
            if url in SUM_CACHE:
                SUM_CACHE.pop(url)

    summ_text(message)

@bot.message_handler(commands=['trans'])
def trans(message: telebot.types.Message):
    thread = threading.Thread(target=trans_thread, args=(message,))
    thread.start()
def trans_thread(message: telebot.types.Message):

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    my_log.log_echo(message)

    with semaphore_talks:
        help = f"""/trans [en|ru|uk|..] текст для перевода на указанный язык

Если не указан то на русский.

/trans en привет, как дела
/trans was ist das

Поддерживаемые языки: {', '.join(supported_langs_trans)}

Напишите что надо перевести
"""
        # разбираем параметры
        # регулярное выражение для разбора строки
        pattern = r'^\/trans\s+((?:' + '|'.join(supported_langs_trans) + r')\s+)?\s*(.*)$'
        # поиск совпадений с регулярным выражением
        match = re.match(pattern, message.text, re.DOTALL)
        # извлечение параметров из найденных совпадений
        if match:
            lang = match.group(1) or "ru"  # если lang не указан, то по умолчанию 'ru'
            text = match.group(2) or ''
        else:
            COMMAND_MODE[chat_id_full] = 'trans'
            bot.reply_to(message, help, parse_mode = 'Markdown', reply_markup=get_keyboard('command_mode', message))
            my_log.log_echo(message, help)
            return
        lang = lang.strip()

    with semaphore_talks:
        with ShowAction(message, 'typing'):
            translated = my_trans.translate_text2(text, lang)
            if translated:
                bot.reply_to(message, translated, reply_markup=get_keyboard('translate', message))
                my_log.log_echo(message, translated)
            else:
                msg = 'Ошибка перевода'
                bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, msg)


@bot.message_handler(commands=['last'])
def last(message: telebot.types.Message):
    thread = threading.Thread(target=last_thread, args=(message,))
    thread.start()
def last_thread(message: telebot.types.Message):
    """делает сумморизацию истории чата, берет последние X сообщений из чата и просит бинг сделать сумморизацию"""

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    with semaphore_talks:
        args = message.text.split()
        help = """/last [X] - показать сумморизацию истории чата за последние Х сообщений, либо все какие есть в памяти. X = от 1 до 60000

Напишите цифру
"""
        if len(args) == 2:
            try:
                x = int(args[1])
                assert x > 0 and x < 60000
                limit = x
            except Exception as error:
                print(error)
                bot.reply_to(message, help, reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, help)
                return
        elif len(args) > 2:
            COMMAND_MODE[chat_id_full] = 'last'
            bot.reply_to(message, help, parse_mode = 'Markdown', reply_markup=get_keyboard('command_mode', message))
            my_log.log_echo(message, help)
            return
        else:
            limit = 60000

        if chat_id_full in CHAT_LOGS:
            messages = CHAT_LOGS[chat_id_full]
        else:
            mes = 'История пуста'
            bot.reply_to(message, mes, reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, mes)
            return

        if limit > len(messages.messages):
            limit = len(messages.messages)

        with ShowAction(message, 'typing'):

            resp = my_sum.summ_text_worker('\n'.join(messages.messages[-limit:]), 'chat_log')

            if resp:
                resp = f'Сумморизация последних {limit} сообщений в чате {message.chat.username or message.chat.first_name or message.chat.title or "unknown"}\n\n' + resp
                # пробуем отправить в приват а если не получилось то в общий чат
                try:
                    bot.send_message(message.from_user.id, resp, disable_web_page_preview=True, reply_markup=get_keyboard('translate', message))
                except Exception as error:
                    print(error)
                    my_log.log2(str(error))
                    bot.reply_to(message, resp, disable_web_page_preview=True, reply_markup=get_keyboard('translate', message))
                my_log.log_echo(message, resp)
            else:
                mes = 'Бинг не ответил'
                bot.reply_to(message, mes, reply_markup=get_keyboard('hide', message))
                my_log.log_echo(message, mes)


@bot.message_handler(commands=['name'])
def send_name(message: telebot.types.Message):
    """Меняем имя если оно подходящее, содержит только русские и английские буквы и не слишком длинное"""

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    BAD_NAMES = ('бинг', 'гугл', 'утка', 'нарисуй')
    args = message.text.split()
    if len(args) > 1:
        new_name = args[1]
        
        # Строка содержит только русские и английские буквы и цифры после букв, но не в начале слова
        regex = r'^[a-zA-Zа-яА-ЯёЁ][a-zA-Zа-яА-ЯёЁ0-9]*$'
        if re.match(regex, new_name) and len(new_name) <= 10 \
                    and new_name.lower() not in BAD_NAMES:
            BOT_NAMES[chat_id_full] = new_name.lower()
            msg = f'Кодовое слово для обращения к боту изменено на ({args[1]}) для этого чата.'
            bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, msg)
        else:
            msg = f"Неправильное имя, можно только русские и английские буквы и цифры после букв, \
не больше 10 всего. Имена {', '.join(BAD_NAMES) if BAD_NAMES else ''} уже заняты."
            bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, msg)
    else:
        help = f"Напишите новое имя бота и я поменяю его, только русские и английские буквы и цифры после букв, \
не больше 10 всего. Имена {', '.join(BAD_NAMES) if BAD_NAMES else ''} уже заняты."
        COMMAND_MODE[chat_id_full] = 'name'
        bot.reply_to(message, help, parse_mode='Markdown', reply_markup=get_keyboard('command_mode', message))


@bot.message_handler(commands=['ocr'])
def ocr_setup(message: telebot.types.Message):
    """меняет настройки ocr"""

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    try:
        arg = message.text.split(maxsplit=1)[1]
    except IndexError as error:
        print(f'tb:ocr_setup: {error}')
        my_log.log2(f'tb:ocr_setup: {error}')
        bot.reply_to(message,
                     f'Меняет настройки OCR\n\nНе указан параметр, какой язык (код) \
или сочетание кодов например rus+eng+ukr\n\nСейчас выбран: \
{get_ocr_language(message)}\n\nhttps://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html',
                     reply_markup=get_keyboard('hide', message), disable_web_page_preview=True)
        return

    lang = get_ocr_language(message)

    msg = f'Старые настройки: {lang}\n\nНовые настройки: {arg}'
    OCR_DB[chat_id_full] = arg
    
    bot.reply_to(message, msg, reply_markup=get_keyboard('hide', message))


@bot.message_handler(commands=['start'])
def send_welcome_start(message: telebot.types.Message):
    # Отправляем приветственное сообщение

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    help = """Я - ваш персональный чат-бот, готовый помочь вам в любое время суток. Моя задача - помочь вам получить необходимую информацию и решить возникающие проблемы. 

Я умею обрабатывать и анализировать большие объемы данных, быстро находить нужную информацию и предоставлять ее в удобном для вас формате. 

Если у вас есть какие-то вопросы или проблемы, не стесняйтесь обращаться к чат-боту! Я готов помочь вам в любое время и в любой ситуации. 

Спасибо, что выбрали меня в качестве своего помощника! Я буду стараться быть максимально полезным для вас.

Добавьте меня в свою группу и я буду озвучивать голосовые сообщения, переводить иностранные сообщения итп."""
    bot.reply_to(message, help, parse_mode='Markdown', disable_web_page_preview=True, reply_markup=get_keyboard('start', message))
    my_log.log_echo(message, help)


@bot.message_handler(commands=['help'])
def send_welcome_help(message: telebot.types.Message):
    # Отправляем приветственное сообщение

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    my_log.log_echo(message)

    help = """Чат бот отзывается на кодовое слово ***бот***(можно сменить командой /name) ***бот расскажи про биткоин***

В привате можно не писать имя для обращения к боту

Если бот перестал отвечать то возможно надо почистить ему память командой ***бот забудь*** или ***забудь***

Кодовое слово ***гугл***(нельзя изменить) позволит получить более актуальную информацию, бот будет гуглить перед ответом ***гугл курс биткоин***

Кодовое слово ***утка***(нельзя изменить) позволит получить более актуальную информацию, бот будет искать в DuckDuckGo перед ответом ***утка курс биткоин***

Кодовое слово ***бинг***(нельзя изменить) позволит получить более актуальную информацию, бот будет дооолго гуглить перед ответом ***бинг курс биткоин***

Кодовое слово ***нарисуй*** и дальше описание даст картинки сгенерированные по описанию. В чате надо добавлять к этому обращение ***бот нарисуй на заборе неприличное слово***

В чате бот будет автоматически переводить иностранные тексты на русский и распознавать голосовые сообщения, отключить это можно кодовым словом ***бот замолчи***, включить обратно ***бот вернись***

Если отправить текстовый файл в приват или с подписью ***прочитай*** то попытается озвучить его как книгу, ожидает .txt utf8 язык пытается определить автоматически (русский если не получилось)

Если отправить картинку или .pdf с подписью ***прочитай*** то вытащит текст из них.

Если отправить fb2 или epub (odt txt doc docx rtf) то прочитает книгу голосом.

Если отправить ссылку в приват то попытается прочитать текст из неё и выдать краткое содержание.

Если отправить текстовый файл или пдф с подписью ***что там*** или ***перескажи*** то выдаст краткое содержание.

При общении с Claude загруженные файлы отправляются прямо к нему и в дальнейшем он может отвечать по их содержанию.

Команды и запросы можно делать голосовыми сообщениями, если отправить голосовое сообщение которое начинается на кодовое слово то бот отработает его как текстовую команду.

""" + '\n'.join(open('commands.txt', encoding='utf8').readlines()) + '\n\n⚙️ https://github.com/theurs/tb1\n\n💬 https://t.me/theurs'

    bot.reply_to(message, help, parse_mode='Markdown', disable_web_page_preview=True, reply_markup=get_keyboard('hide', message))
    my_log.log_echo(message, help)


@bot.message_handler(commands=['id']) 
def id_cmd_handler(message: telebot.types.Message):
    """показывает id юзера и группы в которой сообщение отправлено"""

    # не обрабатывать команды к другому боту /cmd@botname args
    if is_for_me(message.text)[0]: message.text = is_for_me(message.text)[1]
    else: return

    user_id = message.from_user.id
    chat_id_full = get_topic_id(message)
    bot.reply_to(message, f'ID пользователя: {user_id}\n\nID группы: {chat_id_full}')


def send_long_message(message: telebot.types.Message, resp: str, parse_mode:str = None, disable_web_page_preview: bool = None,
                      reply_markup: telebot.types.InlineKeyboardMarkup = None):
    """отправляем сообщение, если оно слишком длинное то разбивает на 2 части либо отправляем как текстовый файл"""
    reply_to_long_message(message=message, resp=resp, parse_mode=parse_mode,
                          disable_web_page_preview=disable_web_page_preview,
                          reply_markup=reply_markup, send_message = True)


def reply_to_long_message(message: telebot.types.Message, resp: str, parse_mode: str = None,
                          disable_web_page_preview: bool = None,
                          reply_markup: telebot.types.InlineKeyboardMarkup = None, send_message: bool = False):
    # отправляем сообщение, если оно слишком длинное то разбивает на 2 части либо отправляем как текстовый файл

    chat_id_full = get_topic_id(message)

    if len(resp) < 20000:
        if parse_mode == 'HTML':
            chunks = utils.split_html(resp, 4000)
        else:
            chunks = utils.split_text(resp, 4000)
        counter = len(chunks)
        for chunk in chunks:
            # в режиме только голоса ответы идут голосом без текста
            # скорее всего будет всего 1 чанк, не слишком длинный текст
            if chat_id_full in VOICE_ONLY_MODE and VOICE_ONLY_MODE[chat_id_full]:
                message.text = '/tts ' + chunk
                tts(message)
            else:
                try:
                    if send_message:
                        bot.send_message(message.chat.id, chunk, message_thread_id=message.message_thread_id, parse_mode=parse_mode,
                                         disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)
                    else:
                        bot.reply_to(message, chunk, parse_mode=parse_mode,
                                disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)
                except Exception as error:
                    print(error)
                    my_log.log2(f'tb:reply_to_long_message: {error}')
                    if send_message:
                        bot.send_message(message.chat.id, chunk, message_thread_id=message.message_thread_id, parse_mode='',
                                         disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)
                    else:
                        bot.reply_to(message, chunk, parse_mode='', disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)
            counter -= 1
            if counter < 0:
                break
            time.sleep(2)
    else:
        buf = io.BytesIO()
        buf.write(resp.encode())
        buf.seek(0)
        bot.send_document(message.chat.id, document=buf, caption='resp.txt', visible_file_name = 'resp.txt')


@bot.message_handler(func=lambda message: True)
def echo_all(message: telebot.types.Message, custom_prompt: str = '') -> None:
    """Обработчик текстовых сообщений"""
    thread = threading.Thread(target=do_task, args=(message, custom_prompt))
    thread.start()
def do_task(message, custom_prompt: str = ''):
    """функция обработчик сообщений работающая в отдельном потоке"""

    chat_id_full = get_topic_id(message)
    check_blocked_user(chat_id_full)

    if message.text in ['🎨Нарисуй', '🌐Найди', '📋Перескажи', '🎧Озвучь', '🈶Переведи', '⚙️Настройки']:
        if message.text == '🎨Нарисуй':
            message.text = '/image'
            image(message)
        # if message.text == '🌐Найди':
        #     message.text = '/google'
        #     google(message)
        if message.text == '🌐Найди':
            message.text = '/ask'
            ask(message)
        if message.text == '📋Перескажи':
            message.text = '/sum'
            summ_text(message)
        if message.text == '🎧Озвучь':
            message.text = '/tts'
            tts(message)
        if message.text == '🈶Переведи':
            message.text = '/trans'
            trans(message)
        if message.text == '⚙️Настройки':
            message.text = '/config'
            config(message)
        return

    if custom_prompt:
        message.text = custom_prompt

    # не обрабатывать неизвестные команды
    if message.text.startswith('/'): return

    with semaphore_talks:

        my_log.log_echo(message)

        # является ли это сообщение топика, темы (особые чаты внутри чатов)
        is_topic = message.is_topic_message or (message.reply_to_message and message.reply_to_message.is_topic_message)
        # является ли это ответом на сообщение бота
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == BOT_ID

        # не отвечать если это ответ юзера другому юзеру
        try:
            _ = message.dont_check_topic
        except AttributeError:
            message.dont_check_topic = False
        if not message.dont_check_topic:
            if is_topic: # в топиках всё не так как в обычных чатах
                # если ответ не мне либо запрос ко всем(в топике он выглядит как ответ с content_type == 'forum_topic_created')
                if not (is_reply or message.reply_to_message.content_type == 'forum_topic_created'):
                    return
            else:
                # если это ответ в обычном чате но ответ не мне то выход
                if message.reply_to_message and not is_reply:
                    return

        # определяем откуда пришло сообщение  
        is_private = message.chat.type == 'private'
        if chat_id_full not in SUPER_CHAT:
            SUPER_CHAT[chat_id_full] = 0
        # если бот должен отвечать всем в этом чате то пусть ведет себя как в привате
        # но если это ответ на чье-то сообщение то игнорируем
        # if SUPER_CHAT[chat_id_full] == 1 and not is_reply_to_other:
        if SUPER_CHAT[chat_id_full] == 1:
            is_private = True

        # удаляем пробелы в конце каждой строки
        message.text = "\n".join([line.rstrip() for line in message.text.split("\n")])

        msg = message.text.lower()

        # определяем какое имя у бота в этом чате, на какое слово он отзывается
        if chat_id_full in BOT_NAMES:
            bot_name = BOT_NAMES[chat_id_full]
        else:
            bot_name = BOT_NAME_DEFAULT
            BOT_NAMES[chat_id_full] = bot_name

        # убираем из запроса кодовое слово
        if msg.startswith((f'{bot_name} ', f'{bot_name},', f'{bot_name}\n')):
            bot_name_used = True
            message.text = message.text[len(f'{bot_name} '):].strip()
        else:
            bot_name_used = False

        msg = message.text.lower()

        # если предварительно была введена какая то команда то этот текст надо отправить в неё
        if chat_id_full in COMMAND_MODE:
            if COMMAND_MODE[chat_id_full]:
                if COMMAND_MODE[chat_id_full] == 'image':
                    message.text = f'/image {message.text}'
                    image(message)
                elif COMMAND_MODE[chat_id_full] == 'tts':
                    message.text = f'/tts {message.text}'
                    tts(message)
                elif COMMAND_MODE[chat_id_full] == 'trans':
                    message.text = f'/trans {message.text}'
                    trans(message)
                elif COMMAND_MODE[chat_id_full] == 'google':
                    message.text = f'/google {message.text}'
                    google(message)
                elif COMMAND_MODE[chat_id_full] == 'perplexity':
                    message.text = f'/ask {message.text}'
                    ask(message)
                elif COMMAND_MODE[chat_id_full] == 'ddg':
                    message.text = f'/ddg {message.text}'
                    ddg(message)
                elif COMMAND_MODE[chat_id_full] == 'name':
                    message.text = f'/name {message.text}'
                    send_name(message)
                elif COMMAND_MODE[chat_id_full] == 'style':
                    message.text = f'/style {message.text}'
                    change_mode(message)
                elif COMMAND_MODE[chat_id_full] == 'last':
                    message.text = f'/last {message.text}'
                    last(message)
                elif COMMAND_MODE[chat_id_full] == 'sum':
                    message.text = f'/sum {message.text}'
                    summ_text(message)
                # из режима поиска не выходим после первого запроса а ждем команды на отмену
                if COMMAND_MODE[chat_id_full] != 'perplexity':
                    COMMAND_MODE[chat_id_full] = ''
                return

        # если мы в чате то добавляем новое сообщение в историю чата для суммаризации с помощью бинга
        if not is_private:
            time_now = datetime.datetime.now().strftime('%H:%M')
            user_name = message.from_user.first_name or message.from_user.username or 'unknown'
            if chat_id_full in CHAT_LOGS:
                m = CHAT_LOGS[chat_id_full]
            else:
                m = utils.MessageList()
            m.append(f'[{time_now}] [{user_name}] {message.text}')
            CHAT_LOGS[chat_id_full] = m

        # кто по умолчанию отвечает
        if chat_id_full not in CHAT_MODE:
            CHAT_MODE[chat_id_full] = cfg.chat_mode_default

        # если сообщение начинается на 'заткнись или замолчи' то ставим блокировку на канал и выходим
        if msg.startswith(('замолчи', 'заткнись')) and (is_private or is_reply):
            BLOCKS[chat_id_full] = 1
            bot.reply_to(message, 'Автоперевод выключен', parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, 'Включена блокировка автопереводов в чате')
            return
        # если сообщение начинается на 'вернись' то снимаем блокировку на канал и выходим
        if msg.startswith('вернись') and (is_private or is_reply):
            BLOCKS[chat_id_full] = 0
            bot.reply_to(message, 'Автоперевод включен', parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
            my_log.log_echo(message, 'Выключена блокировка автопереводов в чате')
            return
        # если сообщение начинается на 'забудь' то стираем историю общения GPT
        if msg.startswith('забудь') and (is_private or is_reply):
            if CHAT_MODE[chat_id_full] == 'bard':
                my_bard.reset_bard_chat(chat_id_full)
                my_log.log_echo(message, 'История барда принудительно отчищена')
            elif CHAT_MODE[chat_id_full] == 'bing':
                bingai.reset_bing_chat(chat_id_full)
                my_log.log_echo(message, 'История бинга принудительно отчищена')
            elif CHAT_MODE[chat_id_full] == 'claude':
                my_claude.reset_claude_chat(chat_id_full)
                my_log.log_echo(message, 'История клода принудительно отчищена')
            elif CHAT_MODE[chat_id_full] == 'chatgpt':
                DIALOGS_DB[chat_id_full] = []
                my_log.log_echo(message, 'История GPT принудительно отчищена')
            bot.reply_to(message, 'Ок', parse_mode='Markdown', reply_markup=get_keyboard('hide', message))
            return

        # если в сообщении только ссылка и она отправлена боту в приват
        # тогда сумморизируем текст из неё
        if my_sum.is_valid_url(message.text) and is_private:
            # если в режиме клауда чата то закидываем веб страницу как файл прямо в него
            if chat_id_full in CHAT_MODE and CHAT_MODE[chat_id_full] == 'claude':
                with ShowAction(message, 'typing'):
                    file_name = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10)) + '.txt'
                    text = my_sum.summ_url(message.text, True)
                    # сгенерировать случайное имя папки во временной папке для этого файла
                    folder_name = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
                    # создать эту папку во временной папке. как получить путь до временной папки в системе?
                    folder_path = os.path.join(tempfile.gettempdir(), folder_name)
                    os.mkdir(folder_path)
                    # сохранить файл в этой папке
                    full_path = os.path.join(folder_path, file_name)
                    with open(full_path, 'w', encoding='utf-8') as new_file:
                        new_file.write(text)
                    caption = message.caption or 'Вот файл'
                    message.text = f'[File uploaded for Claude] [{file_name}] ' + caption
                    my_log.log_echo(message)
                    try:
                        response = my_claude.chat(caption, chat_id_full, False, full_path)
                        response = utils.bot_markdown_to_html(response)
                    except Exception as error:
                        print(f'tb:handle_document_thread:claude: {error}')
                        my_log.log2(f'tb:handle_document_thread:claude: {error}')
                        msg = f'Что-то пошло не так'
                        bot.reply_to(message, msg)
                        my_log.log2(msg)
                        os.remove(full_path)
                        os.rmdir(folder_path)
                        return
                    # удалить сначала файл а потом и эту папку
                    os.remove(full_path)
                    os.rmdir(folder_path)
                    my_log.log_echo(message, response)
                    reply_to_long_message(message, response, parse_mode='HTML', reply_markup=get_keyboard('claude_chat', message))
                return

        
            
            message.text = '/sum ' + message.text
            summ_text(message)
            return

        # проверяем просят ли нарисовать что-нибудь
        if msg.startswith(('нарисуй ', 'нарисуй,')):
            prompt = message.text[8:]
            message.text = f'/image {prompt}'
            image_thread(message)
            n = [{'role':'system', 'content':f'user попросил нарисовать\n{prompt}'}, {'role':'system', 'content':'assistant нарисовал с помощью DALL-E'}]
            if chat_id_full in DIALOGS_DB:
                DIALOGS_DB[chat_id_full] += n
            else:
                DIALOGS_DB[chat_id_full] = n
            return

        # можно перенаправить запрос к бингу, но он долго отвечает
        # my_log.log2(f'{is_reply} {is_private} {SUPER_CHAT[chat_id_full]} {chat_id_full}')
        if msg.startswith(('бинг ', 'бинг,', 'бинг\n')):
            # message.text = message.text[len(f'бинг '):] # убираем из запроса кодовое слово
            if len(msg) > cfg.max_message_from_user:
                bot.reply_to(message, f'Слишком длинное сообщение чат-для бота: {len(msg)} из {cfg.max_message_from_user}')
                my_log.log_echo(message, f'Слишком длинное сообщение чат-для бота: {len(msg)} из {cfg.max_message_from_user}')
                return
            with ShowAction(message, 'typing'):
                # добавляем новый запрос пользователя в историю диалога пользователя
                resp = dialog_add_user_request(chat_id_full, message.text[5:], 'bing')
                if resp:
                    try:
                        bot.reply_to(message, resp, parse_mode='Markdown', disable_web_page_preview = True, 
                        reply_markup=get_keyboard('chat', message))
                    except Exception as error:
                        print(error)
                        my_log.log2(resp)
                        bot.reply_to(message, resp, disable_web_page_preview = True, reply_markup=get_keyboard('chat', message))
                    my_log.log_echo(message, resp)

        # можно перенаправить запрос к гуглу, но он долго отвечает
        elif msg.startswith(('гугл ', 'гугл,', 'гугл\n')):
            message.text = f'/google {msg[5:]}'
            google(message)
            return

        # можно перенаправить запрос к DuckDuckGo, но он долго отвечает
        elif msg.startswith(('утка ', 'утка,', 'утка\n')):
            message.text = f'/ddg {msg[5:]}'
            ddg(message)
            return

        # так же надо реагировать если это ответ в чате на наше сообщение или диалог происходит в привате
        elif is_reply or is_private or bot_name_used:
            if len(msg) > cfg.max_message_from_user and (chat_id_full in CHAT_MODE and CHAT_MODE[chat_id_full] != 'claude'):
                bot.reply_to(message, f'Слишком длинное сообщение чат-для бота: {len(msg)} из {cfg.max_message_from_user}')
                my_log.log_echo(message, f'Слишком длинное сообщение чат-для бота: {len(msg)} из {cfg.max_message_from_user}')
                return

            if chat_id_full not in VOICE_ONLY_MODE:
                VOICE_ONLY_MODE[chat_id_full] = False
            if VOICE_ONLY_MODE[chat_id_full]:
                action = 'record_audio'
                message.text = '[голосовое сообщение, возможны ошибки распознавания речи, отвечай коротко и просто без форматирования текста - ответ будет зачитан вслух]: ' + message.text
            else:
                action = 'typing'


            # # если активирован режим общения с бинг чатом
            # # вариант со стримингом
            # if CHAT_MODE[chat_id_full] == 'bing':
            #     # не даем делать больше 1 запроса за раз, ждем пока ответит
            #     if chat_id_full in BING_LOCKS_STREAMING_MODE:
            #         lock = BING_LOCKS_STREAMING_MODE[chat_id_full]
            #     else:
            #         lock = threading.Lock()
            #         BING_LOCKS_STREAMING_MODE[chat_id_full] = lock
            #     with lock:
            #         with ShowAction(message, action):
            #             updated_message = None
            #             try:
            #                 thread = threading.Thread(target=bingai.chat_stream, args=(message.text, chat_id_full, 3, False))
            #                 thread.start()
            #                 text_clean = ''
            #                 while thread.is_alive():
            #                     time.sleep(2)
            #                     try:
            #                         chunk = ''
            #                         while 1:
            #                             try:
            #                                 chunk += bingai.DIALOGS_QUEUE[chat_id_full].get_nowait()
            #                             except queue.Empty:
            #                                 break

            #                         if chunk == '' or chunk.startswith('Searching the web for:') or \
            #                         str(chunk).startswith('{"web_search_results":'):
            #                             continue
            #                         if bingai.FINAL_SIGN in chunk:
            #                             # если это последний кусочек
            #                             chunk = chunk.replace(bingai.FINAL_SIGN, '')
            #                             if chunk == '':
            #                                 break
            #                             text_clean += chunk
            #                             if text_clean.startswith('Generating answers for you...'):
            #                                 text_clean = text_clean.replace('Generating answers for you...', '', 1).strip()
            #                             text = utils.bot_markdown_to_html(text_clean)
            #                             if len(text) <= 4000:
            #                                 if updated_message:
            #                                     updated_message_text = updated_message.text
            #                                 else:
            #                                     updated_message_text = ''
            #                                 if text != updated_message_text:
            #                                     if updated_message:
            #                                         bot.edit_message_text(text, chat_id = message.chat.id, 
            #                                                               message_id = updated_message.message_id,
            #                                                               parse_mode='HTML', disable_web_page_preview=True)
            #                                     else:
            #                                         updated_message = bot.reply_to(message, text, parse_mode='HTML', 
            #                                                                       disable_web_page_preview=True)
            #                             break

            #                         text_clean += chunk
            #                         if text_clean.startswith('Generating answers for you...'):
            #                             text_clean = text_clean.replace('Generating answers for you...', '', 1).strip()
            #                         text = utils.bot_markdown_to_html(text_clean)
            #                         # если текст меньше 4к
            #                         if len(text) <= 4000:
            #                             if updated_message:
            #                                 updated_message_text = updated_message.text
            #                             else:
            #                                 updated_message_text = ''
            #                             if text != updated_message_text:
            #                                 if updated_message:
            #                                     bot.edit_message_text(text, chat_id = message.chat.id,
            #                                                           message_id = updated_message.message_id,
            #                                                           parse_mode='HTML', disable_web_page_preview=True)
            #                                 else:
            #                                     updated_message = bot.reply_to(message, text, parse_mode='HTML', 
            #                                                                    disable_web_page_preview=True)
            #                     except KeyError:
            #                         pass
            #                     except queue.Empty:
            #                         pass

            #                 if len(text) <= 4000:
            #                     if chat_id_full in DISABLED_KBD and DISABLED_KBD[chat_id_full] == False:
            #                         bot.edit_message_reply_markup(chat_id = message.chat.id, message_id = updated_message.message_id,
            #                                                     reply_markup=get_keyboard('bing_chat', message))
            #                 else:
            #                     bot.delete_message(chat_id = message.chat.id, message_id = updated_message.message_id)
            #                     if chat_id_full in DISABLED_KBD and DISABLED_KBD[chat_id_full] == False:
            #                         reply_to_long_message(message, text, parse_mode='HTML', disable_web_page_preview = True,
            #                                                 reply_markup=get_keyboard('bing_chat', message))
            #                     else:
            #                         reply_to_long_message(message, text, parse_mode='HTML', disable_web_page_preview = True)
            #                 my_log.log_echo(message, text)
            #                 my_log.log2(text_clean)
            #                 my_log.log2(text)
            #             except Exception as error:
            #                 print(f'tb:do_task:bing answer:0: {error}')
            #                 my_log.log2(f'tb:do_task:bing answer:0: {error}')
            #                 bot.reply_to(message, 'Бинг не хочет об этом говорить', parse_mode='Markdown', disable_web_page_preview = True, 
            #                             reply_markup=get_keyboard('chat', message))
            #                 my_log.log_echo(message, 'Бинг не хочет об этом говорить')
            #     return


            # # если активирован режим общения с бинг чатом
            # вариант без стриминга
            if CHAT_MODE[chat_id_full] == 'bing':
                with ShowAction(message, action):
                    try:
                        answer = bingai.chat(message.text, chat_id_full)
                        if answer:
                            # my_log.log_echo(message, answer['text'], debug = True)
                            text = answer['text']
                            if not VOICE_ONLY_MODE[chat_id_full]:
                                text = utils.bot_markdown_to_html(text)
                            messages_left = str(answer['messages_left'])
                            if not VOICE_ONLY_MODE[chat_id_full]:
                                text = f"{text}\n\n{messages_left}/30"
                            try:
                                reply_to_long_message(message, text, parse_mode='HTML', disable_web_page_preview = True, 
                                                      reply_markup=get_keyboard('bing_chat', message))
                            except Exception as error:
                                print(error)
                                reply_to_long_message(message, text, parse_mode='', disable_web_page_preview = True, 
                                                      reply_markup=get_keyboard('bing_chat', message))
                            my_log.log_echo(message, text)
                            if int(messages_left) == 1:
                                bingai.reset_bing_chat(chat_id_full)
                        else:
                            bot.reply_to(message, 'Бинг не хочет об этом говорить', parse_mode='Markdown', disable_web_page_preview = True, 
                                         reply_markup=get_keyboard('chat', message))
                            my_log.log_echo(message, 'Бинг не хочет об этом говорить')
                    except Exception as error:
                        print(f'tb:do_task:bing answer: {error}')
                        my_log.log2(f'tb:do_task:bing answer: {error}')
                        bot.reply_to(message, 'Бинг не хочет об этом говорить', parse_mode='Markdown', disable_web_page_preview = True, 
                                     reply_markup=get_keyboard('chat', message))
                        my_log.log_echo(message, 'Бинг не хочет об этом говорить')
                    return

            # если активирован режим общения с бард чатом
            if CHAT_MODE[chat_id_full] == 'bard':
                if len(msg) > my_bard.MAX_REQUEST:
                    bot.reply_to(message, f'Слишком длинное сообщение для барда: {len(msg)} из {my_bard.MAX_REQUEST}')
                    my_log.log_echo(message, f'Слишком длинное сообщение для барда: {len(msg)} из {my_bard.MAX_REQUEST}')
                    return
                with ShowAction(message, action):
                    try:
                        # имя пользователя если есть или ник
                        user_name = message.from_user.first_name or message.from_user.username or ''
                        answer = my_bard.chat(message.text, chat_id_full, user_name = user_name)
                        # answer = my_bard.convert_markdown(answer)
                        # my_log.log_echo(message, answer, debug = True)
                        if not VOICE_ONLY_MODE[chat_id_full]:
                            answer = utils.bot_markdown_to_html(answer)
                        my_log.log_echo(message, answer)
                        if answer:
                            try:
                                reply_to_long_message(message, answer, parse_mode='HTML', disable_web_page_preview = True, 
                                                      reply_markup=get_keyboard('bard_chat', message))
                            except Exception as error:
                                print(f'tb:do_task: {error}')
                                my_log.log2(f'tb:do_task: {error}')
                                reply_to_long_message(message, answer, parse_mode='', disable_web_page_preview = True, 
                                                      reply_markup=get_keyboard('bard_chat', message))
                    except Exception as error3:
                        print(error3)
                        my_log.log2(str(error3))
                    return

            # если активирован режим общения с клод чатом
            if CHAT_MODE[chat_id_full] == 'claude':
                with ShowAction(message, action):
                    try:
                        answer = my_claude.chat(message.text, chat_id_full)
                        if not VOICE_ONLY_MODE[chat_id_full]:
                            answer = utils.bot_markdown_to_html(answer)
                        my_log.log_echo(message, answer)
                        if answer:
                            try:
                                reply_to_long_message(message, answer, parse_mode='HTML', disable_web_page_preview = True, 
                                                      reply_markup=get_keyboard('claude_chat', message))
                            except Exception as error:
                                print(f'tb:do_task: {error}')
                                my_log.log2(f'tb:do_task: {error}')
                                reply_to_long_message(message, answer, parse_mode='', disable_web_page_preview = True, 
                                                      reply_markup=get_keyboard('claude_chat', message))
                    except Exception as error3:
                        print(error3)
                        my_log.log2(str(error3))
                    return

            # добавляем новый запрос пользователя в историю диалога пользователя
            with ShowAction(message, action):
                resp = dialog_add_user_request(chat_id_full, message.text, 'gpt')
                if resp:
                    # my_log.log_echo(message, resp, debug = True)
                    if not VOICE_ONLY_MODE[chat_id_full]:
                        resp = utils.bot_markdown_to_html(resp)
                    my_log.log_echo(message, resp)
                    try:
                        reply_to_long_message(message, resp, parse_mode='HTML', disable_web_page_preview = True, 
                                                reply_markup=get_keyboard('chat', message))
                    except Exception as error2:    
                        print(error2)
                        my_log.log2(resp)
                        reply_to_long_message(message, resp, parse_mode='', disable_web_page_preview = True, 
                                                reply_markup=get_keyboard('chat', message))
        else: # смотрим надо ли переводить текст
            if check_blocks(get_topic_id(message)):
                return
            text = my_trans.translate(message.text)
            if text:
                bot.reply_to(message, text, parse_mode='Markdown', reply_markup=get_keyboard('translate', message))
                my_log.log_echo(message, text)


def set_default_commands():
    """
    Reads a file containing a list of commands and their descriptions,
    and sets the default commands for the bot.
    """
    commands = []
    with open('commands.txt', encoding='utf-8') as file:
        for line in file:
            try:
                command, description = line[1:].strip().split(' - ', 1)
                if command and description:
                    commands.append(telebot.types.BotCommand(command, description))
            except Exception as error:
                print(error)
    bot.set_my_commands(commands)

    bot_name = bot.get_my_name().name.strip()
    description = bot.get_my_description().description.strip()
    short_description = str(bot.get_my_short_description().short_description).strip()

    new_bot_name = cfg.bot_name.strip()
    new_description = cfg.bot_description.strip()
    new_short_description = cfg.bot_short_description.strip()

    if bot_name != new_bot_name:
        if not bot.set_my_name(cfg.bot_name):
            my_log.log2(f'Не удалось установить имя бота: {cfg.bot_name}')
    if description != new_description:
        if not bot.set_my_description(cfg.bot_description):
            my_log.log2(f'Не удалось установить описание бота: {cfg.bot_description}')
    if short_description != new_short_description:
        if not bot.set_my_short_description(cfg.bot_short_description):
            my_log.log2(f'Не удалось установить короткое описание бота: {cfg.bot_short_description}')


def main():
    """
    Runs the main function, which sets default commands and starts polling the bot.
    """
    set_default_commands()
    bot.polling(timeout=90, long_polling_timeout=90)


if __name__ == '__main__':
    main()
