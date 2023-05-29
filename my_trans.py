#!/usr/bin/env python3


from py_trans import PyTranslator
from langdetect import detect, detect_langs
import subprocess
import gpt_basic


def detect_lang(text):
    """ Возвращает None если не удалось определить, 2 буквенное определение языка если получилось 'en', 'ru' итп """
    # минимальное количество слов для определения языка = 8. на коротких текстах детектор сильно врёт, возможно 8 это тоже мало
    if sum(1 for word in text.split() if len(word) >= 2) < 8:
        return None

    # смотрим список вероятностей, и если в списке есть русский то возвращаем None (с русского на русский не переводим)
    #print(detect_langs(text))
    try:
        for i in detect_langs(text):
            if i.lang == 'ru':
                return None
    except Exception as e:
        print(e)
        return None

    try:
        language = detect(text)
    except Exception as e:
        print(e)
        return None
    return language


def translate_text(text, lang = 'ru'):
    """ Возвращает None если не удалось перевести и текст перевода если удалось """
    x = PyTranslator()
    r = x.translate(text, lang)
    if r['status'] == 'success':
        return r['translation']
    return None
    

def translate_text2(text, lang = 'ru'):
    """ Переводит text на язык lang с помощью утилиты trans. Возвращает None если не удалось перевести и текст перевода если удалось """
    process = subprocess.Popen(['trans', f':{lang}', '-b', text], stdout = subprocess.PIPE)
    output, error = process.communicate()
    r = output.decode('utf-8').strip()
    if error != None:
        return None
    return r


def translate(text):
    """ Проверяем надо ли переводить на русский и переводим если надо.
    Возвращает None если не удалось перевести и текст перевода если удалось """
    if text:
        d = detect_lang(text)
    else:
        return None
    # переводим если язык не русский но определился успешно
    if d and d != 'ru':
        # этот вариант почему то заметно хуже работает, хотя вроде бы тот же самый гугл переводчик
        #return translate_text(text)

        #у этого варианта есть проблемы с кодировками в докере Ж)
        #return translate_text2(text)
        
        #return gpt_basic.translate_text(text) or translate_text2(text) or None
        # отключил ГПТ, он часто включает цензуру
        return translate_text2(text) or None
    return None
    

if __name__ == "__main__":
    #text="""Звичайно, я можу написати два речення на українській мові."""
    
    
    text = """Коли у нас будуть F-16, ми виграємо цю війну, - Ігнат

F-16 – багатоцільовий літак, який може працювати по наземних, повітряних та надводних цілях, а також буде перекривати нашу територію там, де немає комплексів ППО.

"Я вам скажу більше, коли будуть F-16, ми виграємо цю війну. Якщо ці літаки прийдуть в Україну, вони стануть на бойове чергування у різних регіонах на наших оперативних аеродромах", — зауважив Ігнат.

Територія країни та протяжність державного кордону велика, а лінія фронту, враховуючи Білорусь, Придністров'я та чорноморське узбережжя - понад 2,5 тис. км і перекрити комплексами ППО, все не вдасться, саме тому нам треба F-16.

Цей винищувач може працювати по повітряних цілях як знизу, так і зверху. Там, де немає ППО, буде працювати F-16.

надiслати новину @novosti_kieva_bot
👉ПІДПИСАТИСЬ (https://t.me/+YjYxxNba5fYyN2Ni)"""
    
    print(translate_text2(text, 'en'))
    
    #print(translate_text(text))
    #print(translate_text2(text))

    #print(translate(text))
