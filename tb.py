#!/usr/bin/env python3


from aiogram import Bot, Dispatcher, types, executor
import io, os
import my_ocr, my_trans, my_log
import gpt_basic

if os.path.exists('cfg.py'):
    from cfg import token
else:
    token = os.getenv('TOKEN')


bot = Bot(token=token)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    # Отправляем приветственное сообщение
    await message.reply("Привет!")
    await my_log.log(message)


@dp.message_handler()
async def echo(message: types.Message):
    if message.entities:
        if message.entities[0]['type'] in ('code', 'spoiler'):
            await my_log.log(message, 'code or spoiler in message')
            return
    text = my_trans.translate(message.text)
    if text:
        await message.answer(text)
        await my_log.log(message, text)
    else:
        await my_log.log(message, '')


@dp.message_handler(content_types=types.ContentType.VIDEO)
async def handle_video(message: types.Message):
    # пересланные сообщения пытаемся перевести даже если в них видео
    if "forward_from_chat" in message:
        if message.entities:
            if message.entities[0]['type'] in ('code', 'spoiler'):
                await my_log.log(message, 'code or spoiler in message')
                return
        # у видео нет текста но есть заголовок caption. его и будем переводить
        text = my_trans.translate(message.caption)
        if text:
            await message.answer(text)
            await my_log.log(message, text)
        else:
            await my_log.log(message, '')
        return


@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_photo(message: types.Message):
    # пересланные сообщения пытаемся перевести даже если в них картинка
    if "forward_from_chat" in message:
        if message.entities:
            if message.entities[0]['type'] in ('code', 'spoiler'):
                await my_log.log(message, 'code or spoiler in message')
                return
        # у фотографий нет текста но есть заголовок caption. его и будем переводить
        text = my_trans.translate(message.caption)
        if text:
            await message.answer(text)
            await my_log.log(message, text)
        else:
            await my_log.log(message, '')
        return

    # распознаем текст только если есть команда для этого
    if not message.caption: return
    if not gpt_basic.detect_ocr_command(message.caption.lower()): return

    #chat_type = message.chat.type
    #if chat_type != types.ChatType.PRIVATE: return
    # получаем самую большую фотографию из списка
    photo = message.photo[-1]
    fp = io.BytesIO()
    # скачиваем фотографию в байтовый поток
    await photo.download(destination_file=fp)
    # распознаем текст на фотографии с помощью pytesseract
    text = my_ocr.get_text_from_image(fp.read())
    # отправляем распознанный текст пользователю
    if text.strip() != '':
        # если текст слишком длинный, отправляем его в виде текстового файла
        if len(text) > 4096:
            with io.StringIO(text) as f:
                f.name = 'text.txt'
                await message.reply_document(f)
                await my_log.log(message, '[OCR] Sent as file: ' + text)
        else:
            await message.reply(text)
            await my_log.log(message, '[OCR] ' + text)
    else:
        await my_log.log(message, '[OCR] no results')

    
@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    #отключено пока. слишком долго выполняется
    return
    # получаем самый большой документ из списка
    document = message.document
    # если документ не является PDF-файлом, отправляем сообщение об ошибке
    if document.mime_type != 'application/pdf':
        await message.reply('Это не PDF-файл.')
        return
    fp = io.BytesIO()
    # скачиваем документ в байтовый поток
    await message.document.download(destination_file=fp)
    # распознаем текст в документе с помощью функции get_text
    text = my_ocr.get_text(fp)
    # отправляем распознанный текст пользователю
    if text.strip() != '':
        # если текст слишком длинный, отправляем его в виде текстового файла
        if len(text) > 4096:
            with io.StringIO(text) as f:
                f.name = 'text.txt'
                await message.reply_document(f)
        else:
            await message.reply(text)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
