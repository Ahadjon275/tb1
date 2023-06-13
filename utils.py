#!/usr/bin/env python3


import re
import my_log
import my_dic


# диалог всегда начинается одинаково

gpt_start_message1 = 'Ты искусственный интеллект отвечающий на запросы юзера.'
gpt_start_message2 = 'Ты искусственный интеллект отвечающий на запросы юзера. Отвечай с подходящим к запросу типом иронии или юмора но не перегибай палку. Добавляй один смайлик с подходящей эмоцией если это уместно.'
#gpt_start_message3 = 'Ты искусственный интеллект отвечающий на запросы юзера. Отвечай с сильной иронией и токсичностью.'
gpt_start_message3 = 'Ты троль из интернета. Отвечай с сильной иронией и токсичностью.'

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


if __name__ == '__main__':
    #a = my_dic.PersistentDict('test.pkl')
    
    text = """

[12-06-2023 23:10:03] [GPTChat]: Конечно, вот пример:
**жирный**
*наклонный*
<u>подчеркнутый</u>
~~перечеркнутый~~
`одной ширины`
```python
print("Hello, World!")
```
|||спойлер (скрытый текст)|||
[ссылка](https://www.google.com/) с подписью


[12-06-2023 23:12:31] [BingAI]: Здравствуйте, это Bing. Я могу показать вам примеры текста, отформатированного по вашему запросу. Вот они:
- **Жирный**
- *Наклонный*
- <u>Подчеркнутый</u>
- ~~Перечеркнутый~~
- `Одной ширины`
- ```# Код на языке Python
def hello():
    print("Привет, мир!")
```
- >!Спойлер (скрытый текст)!<
- [Ссылка с подписью](https://www.bing.com)

Что-то еще я могу для вас сделать? 😊

<a href='sfsdf'>asdasd</a>

"""
 
    text = """
[13-06-2023 09:45:19] [BOT]: К сожалению, я не могу отформатировать текст всеми возможными вариантами, так как их слишком много. Однако, я могу показать примеры разных типов ф
орматирования текста:

* **Жирный шрифт**: Этот текст будет **жирным**.
* *Курсивный шрифт*: Этот текст будет *курсивным*.
* Подчёркнутый текст: Этот текст будет <u>подчёркнутым</u>.
* ~~Зачёркнутый текст~~: Этот текст будет ~~зачёркнутым~~.
* `Моноширинный шрифт`: Этот текст будет `моноширинным`.

Кроме того, можно комбинировать эти типы форматирования для создания более сложных эффектов. Например, такой текст будет ***жирным и курсивным***.
"""
 
    #text = """'привет к��к дела ("tesd<\*__t text)"""
    #print(escape_markdown(text))

    print(html(text))