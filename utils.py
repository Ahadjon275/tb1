#!/usr/bin/env python3


import my_log
import os
import re
import subprocess
import tempfile
import platform as platform_module


# диалог всегда начинается одинаково

gpt_start_message1 = 'Ты искусственный интеллект отвечающий на запросы юзера.'
gpt_start_message2 = 'Ты искусственный интеллект отвечающий на запросы юзера. Отвечай с подходящим к запросу типом иронии или юмора но не перегибай палку. Добавляй один смайлик с подходящей эмоцией если это уместно.'
#gpt_start_message3 = 'Ты искусственный интеллект отвечающий на запросы юзера. Отвечай с сильной иронией и токсичностью.'
gpt_start_message3 = 'Ты троль из интернета. Отвечай с сильной иронией и токсичностью.'
gpt_start_message4 = 'Ты известная порно актриса Ева Элфи и отвечаешь на вопросы поклонников в телеграм чате, твои ответы всегда очень горячие и провокационные, короткие, с жаргоном из порноиндустрии, намекающие на порно.'

def escape_markdown(text):
    """функция для экранирования символов перед отправкой в маркдауне телеграма"""
    #pattern = r"([_*\[\]()~|`])"
    pattern = r"([_*\[\]~|`])"
    my_log.log2(text + '\n\n\n\n')
    return re.sub(pattern, r"\\\1", text)


def count_tokens(messages):
    """пытаемся посчитать количество символов в диалоге юзера с ботом
    хз что такое токены считаем просто символы"""
    if messages:
        # тут будет некоторое количество лишнего но пусть будет
       return len(str(messages))
    return 0


def remove_vowels(text: str) -> str:
    """
    Функция для удаления из текста русских и английских гласных букв "а", "о", "e" и "a".
    :param text: текст, в котором нужно удалить гласные буквы
    :type text: str
    :return: текст без указанных гласных букв
    :rtype: str
    """
    vowels = [  'а', 'о',   # русские
                'a', 'e']   # английские. не стоит наверное удалять слишком много
    for vowel in vowels:
        text = text.replace(vowel, '') # заменяем гласные буквы на пустую строку
    return text


class MessageList:
    """список последних сообщений в чате с заданным максимальным размером в байтах
    это нужно для суммаризации событий в чате с помощью бинга
    """
    def __init__(self, max_size=60000):
        self.max_size = max_size
        self.messages = []
        self.size = 0

    def append(self, message: str):
        assert len(message) < (4*1024)+1
        message_bytes = message.encode('utf-8')
        message_size = len(message_bytes)
        if self.size + message_size > self.max_size:
            while self.size + message_size > self.max_size:
                oldest_message = self.messages.pop(0)
                self.size -= len(oldest_message.encode('utf-8'))
        self.messages.append(message)
        self.size += message_size


# не использует. удалить
def html(text: str) -> str:
    """конвертирует маркдаун который генерируют gpt chat и bing ai в html коды телеграма"""

    # заменить символы <> в строке так что бы не менять их в хтмл теге <u></u> и в маркаун теге >!Спойлер (скрытый текст)!<
    # сначала меняем их на что то другое
    html = text.replace('<u>', '🌞🌸🐝🍯🍓')
    html = html.replace('</u>', '🌊🌴🍹🕶️🌞')
    html = html.replace('>!', '🐶🦴🏠🌳🎾')
    html = html.replace('!<', '🎬🍿🎥🎞️🤩')
    # потом меняем символы <>
    html = html.replace('<', '&lt;')
    html = html.replace('>', '&gt;')
    # и возвращаем обратно
    html = html.replace('🌞🌸🐝🍯🍓', '<u>')
    html = html.replace('🌊🌴🍹🕶️🌞', '</u>')
    html = html.replace('🐶🦴🏠🌳🎾', '>!')
    html = html.replace('🎬🍿🎥🎞️🤩', '!<')

    html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'\*(.*?)\*', r'<i>\1</i>', html)
    html = re.sub(r'\~\~(.*?)\~\~', r'<s>\1</s>', html)


    code_pattern = r"```([a-z]+)\n([\s\S]+?)\n```"
    replacement = r"<pre language='\1'>\2</pre>"
    html = re.sub(code_pattern, replacement, html)


    code_pattern = r"\`\`\`([\s\S]*?)\`\`\`"
    replacement = r'<pre>\1</pre>'
    html = re.sub(code_pattern, replacement, html)


    spoiler_pattern = r"\|\|\|([\s\S]*?)\|\|\|"
    replacement = r'<span class="tg-spoiler">\1</span>'
    html = re.sub(spoiler_pattern, replacement, html)

    html = re.sub(r'>!(.*?)!<', r'<span class="tg-spoiler">\1</span>', html)

    html = re.sub(r'\`(.*?)\`', r'<code>\1</code>', html)

    regex = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
    html = regex.sub(r'<a href="\2">\1</a>', html)

    return html


def split_text(text: str, chunk_limit: int = 1500):
    """разбивает текст на части заданной длины не разрывая слова,
    в результате куски могут быть больше чем задано, если в тексте нет пробелов то намного больше Ж)"""
    # создаем пустой список для хранения частей текста
    chunks = []
    # создаем переменную для хранения текущей позиции в тексте
    position = 0
    # пока позиция меньше длины текста
    while position < len(text):
        # находим индекс пробела после лимита
        space_index = text.find(" ", position + chunk_limit)
        # если пробел не найден, то берем весь оставшийся текст
        if space_index == -1:
            space_index = len(text)
        # добавляем часть текста от текущей позиции до пробела в список
        chunks.append(text[position:space_index])
        # обновляем текущую позицию на следующий символ после пробела
        position = space_index + 1
    # возвращаем список частей текста
    return chunks


def platform() -> str:
    """Определяет на какой платформе работает скрипт, windows или linux"""
    return platform_module.platform()


def convert_to_mp3(input_file: str) -> str:
    """Конвертирует аудиофайл в MP3 формат с помощью ffmpeg
    возвращает имя нового файла (созданного во временной папке)"""
    # Создаем временный файл с расширением .mp3
    temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    temp_file.close()
    output_file = temp_file.name
    os.remove(output_file)
    # Конвертируем аудиофайл в wav с помощью ffmpeg
    command = ["ffmpeg", "-i", input_file, output_file]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Проверяем, успешно ли прошла конвертация
    if os.path.exists(output_file):
        return output_file
    else:
        return None


if __name__ == '__main__':
    pass
    text="""
Не судите строго, это моя первая статья, наверное если бы я был гуру Nginx и "Линуха", то скорее всего боли и страданий бы не было.

С чего все началось?

Одним днем мне понадобилось реализовать довольно не тривиальную задачу:

Есть множество сервисов с которых нужно собирать данные для обработки и дальнейшей аналитики, модуль который это все собирает может быть установлен на множество серверов (пока 40, но в горизонте года это 1000), но хочется чтобы все обращения от этих серверов шли на один ip , а с него уже распределялись в зависимости от типа запроса или конечной точки обращения. Условно мы обращаемся к серваку 100.1.2.101 по порту 8080 и просим от него данные о всех домах на определенной территории ,он в свою очередь по заданному сценарию коннектится к определенному proxy (Допустим squid, он нужен так как некоторые api залочены по ip) и через него получает данные из конечного api.

P.S. Данные нельзя хранить на промежуточном сервере, так как они слишком часто обновляются :(

В итоге я решил эту задачу разделить на несколько этапов одна из них это распределение нагрузки...

"""
    for i in split_text(text, 200):
        print(i, '\n==============\n')

    """
    #import gpt_basic
    import my_trans
    for i in split_text(open('1.txt').read()):
        #t = gpt_basic.ai('переведи на русский язык\n\n' + i)
        t = my_trans.translate(i)
        print(t)
        print('======================')
    """