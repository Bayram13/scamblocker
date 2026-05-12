import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from captcha.image import ImageCaptcha
import random
import threading
import os
from flask import Flask
from dotenv import load_dotenv

# .env faylındakı məlumatları yükləyir (Lokal kompüterdə işlətmək üçün)
load_dotenv()

# Tokeni mühit dəyişənlərindən çəkirik
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN tapılmadı! Zəhmət olmasa .env faylını yoxlayın.")

bot = telebot.TeleBot(TOKEN)

# Şəkil generatorunu inisializasiya edirik
image_captcha = ImageCaptcha(width=280, height=90)
pending_users = {}

def mute_user_timeout(chat_id, user_id, message_id):
    if user_id in pending_users:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception as e:
            print(f"Xəta (Timeout): {e}")
        finally:
            del pending_users[user_id]

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            continue

        chat_id = message.chat.id
        user_id = new_member.id

        bot.restrict_chat_member(
            chat_id, user_id,
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )

        correct_code = str(random.randint(1000, 9999))
        image_data = image_captcha.generate(correct_code)
        image_data.seek(0)

        options = [correct_code]
        while len(options) < 4:
            fake_code = str(random.randint(1000, 9999))
            if fake_code not in options:
                options.append(fake_code)
        random.shuffle(options)

        markup = InlineKeyboardMarkup()
        buttons = []
        for opt in options:
            callback_data = f"cap_{user_id}_pass" if opt == correct_code else f"cap_{user_id}_fail"
            buttons.append(InlineKeyboardButton(text=opt, callback_data=callback_data))
        
        markup.add(buttons[0], buttons[1])
        markup.add(buttons[2], buttons[3])

        caption = f"⚠️ Xoş gəldin, [{new_member.first_name}](tg://user?id={user_id})!\n\nQrupa yaza bilmək üçün **60 saniyə** ərzində şəkildəki kodu seçin."
        sent_msg = bot.send_photo(
            chat_id, 
            photo=image_data, 
            caption=caption, 
            reply_markup=markup,
            parse_mode="Markdown"
        )

        timer = threading.Timer(60.0, mute_user_timeout, args=(chat_id, user_id, sent_msg.message_id))
        timer.start()

        pending_users[user_id] = {
            'timer': timer,
            'message_id': sent_msg.message_id
        }

@bot.callback_query_handler(func=lambda call: call.data.startswith('cap_'))
def handle_captcha_click(call):
    data_parts = call.data.split('_')
    target_user_id = int(data_parts[1])
    action = data_parts[2]

    if call.from_user.id != target_user_id:
        bot.answer_callback_query(call.id, "Bu doğrulama sizin üçün deyil ⛔", show_alert=True)
        return

    chat_id = call.message.chat.id

    if target_user_id in pending_users:
        pending_users[target_user_id]['timer'].cancel()
        del pending_users[target_user_id]

    if action == "pass":
        bot.restrict_chat_member(
            chat_id, target_user_id,
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        bot.answer_callback_query(call.id, "Təsdiqləndi! Qrupa yaza bilərsiniz ✅", show_alert=False)
        bot.delete_message(chat_id, call.message.message_id)

    elif action == "fail":
        bot.answer_callback_query(call.id, "Yanlış kod! Qrupa yazma hüququnuz ləğv edildi 🔇", show_alert=True)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception as e:
            print(f"Xəta (Mute): {e}")

# --- RENDER VƏ HOSTİNG ÜÇÜN FLASK WEB SERVERİ ---
app = Flask(__name__)

@app.route('/')
def index():
    return "Captcha Bot aktivdir və işləyir!"

def run_bot():
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    print("Peşəkar CAPTCHA Botu işə düşdü...")
    threading.Thread(target=run_bot).start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
