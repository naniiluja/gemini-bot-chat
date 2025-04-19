import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
import requests
import json
from flask import Flask, request
import os

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cấu hình Flask
flask_app = Flask(__name__)

# Cấu hình API key
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7589027326:AAEV-zWEAByhhj-8mxGpQ9ZdjiCrWP58shY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB5E5i1WMUR963uLh7N3fDOf43tEaxptcE")

# Cấu hình Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Tạo Telegram Application
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gửi tin nhắn khi nhận được lệnh /start."""
    user = update.effective_user
    await update.message.reply_text(
        f"Xin chào {user.first_name}! Tôi là bot sử dụng Google Gemini AI. Hãy gửi cho tôi một tin nhắn để trò chuyện."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gửi tin nhắn khi nhận được lệnh /help."""
    await update.message.reply_text(
        "Gửi tin nhắn cho tôi và tôi sẽ sử dụng Google Gemini AI để trả lời bạn."
    )

async def gemini_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xử lý tin nhắn và gửi phản hồi từ Gemini API."""
    user_message = update.message.text
    
    # Thông báo đang gõ...
    await context.bot.send_chat_action(
        chat_id=update.effective_message.chat_id, 
        action="typing"
    )
    
    try:
        # Gọi Gemini API sử dụng requests
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": user_message}]}]
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(data))
        
        if response.status_code == 200:
            response_json = response.json()
            if "candidates" in response_json and len(response_json["candidates"]) > 0:
                response_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
                if len(response_text) > 4096:
                    for i in range(0, len(response_text), 4096):
                        await update.message.reply_text(response_text[i:i+4096])
                else:
                    await update.message.reply_text(response_text)
            else:
                await update.message.reply_text("Không nhận được phản hồi từ Gemini API.")
        else:
            await update.message.reply_text(f"Lỗi API: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"Lỗi khi gọi Gemini API: {e}")
        await update.message.reply_text(f"Xin lỗi, đã xảy ra lỗi: {str(e)}")

# Đăng ký handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gemini_response))

# Flask routes
@flask_app.route('/healthz')
def health():
    """Endpoint cho UptimeRobot."""
    return 'OK', 200

@flask_app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
async def webhook():
    """Xử lý webhook từ Telegram."""
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return 'OK', 200

async def set_webhook():
    """Thiết lập webhook cho Telegram."""
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TELEGRAM_TOKEN}"
    await application.bot.set_webhook(url=webhook_url)

def main():
    """Khởi động bot và Flask server."""
    # Khởi tạo application
    application.loop.run_until_complete(set_webhook())
    
    # Chạy Flask server
    port = int(os.getenv('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()