import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
import requests
import json
from flask import Flask, request
import os
import asyncio
import threading

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cấu hình biến môi trường
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "gemini-bot-chat.onrender.com")

# Kiểm tra biến môi trường bắt buộc
missing_vars = []
if not TELEGRAM_TOKEN:
    missing_vars.append("TELEGRAM_TOKEN")
if not GEMINI_API_KEY:
    missing_vars.append("GEMINI_API_KEY")
if missing_vars:
    logger.error("Missing required environment variables: %s", ", ".join(missing_vars))
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Cấu hình Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Tạo Telegram Application
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Khởi tạo biến để lưu trữ event loop
application_event_loop = None
initialized = False

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
    logger.info("Processing message: %s", user_message)
    await context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action="typing")
    try:
        url = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent"
        params = {"key": GEMINI_API_KEY}
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": user_message}]}]}
        logger.info("Sending request to Gemini API")
        response = requests.post(url, headers=headers, params=params, data=json.dumps(data))
        logger.info("Gemini API response status: %s", response.status_code)
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
                logger.warning("No candidates in Gemini response: %s", response_json)
                await update.message.reply_text("Không nhận được phản hồi từ Gemini API.")
        else:
            logger.error("Gemini API error: %s - %s", response.status_code, response.text)
            await update.message.reply_text(f"Lỗi API: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error("Error calling Gemini API: %s", str(e))
        await update.message.reply_text(f"Xin lỗi, đã xảy ra lỗi: {str(e)}")

# Đăng ký handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gemini_response))

# Hàm khởi tạo ứng dụng Telegram Bot
async def initialize_application():
    """Khởi tạo ứng dụng Telegram Bot"""
    global initialized
    
    if not initialized:
        logger.info("Initializing application...")
        await application.initialize()
        initialized = True
        logger.info("Application initialized successfully")
    return application

# Hàm để khởi động event loop và khởi tạo application
def init_application():
    """Khởi động event loop và khởi tạo application"""
    global application_event_loop
    
    # Tạo event loop nếu chưa có
    if application_event_loop is None:
        application_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(application_event_loop)
        
        # Khởi tạo application
        application_event_loop.run_until_complete(initialize_application())
        
        logger.info("Application event loop started and application initialized")

# Gọi hàm khởi tạo ứng dụng khi module được import
init_application()

# Cấu hình Flask
flask_app = Flask(__name__)

# Flask routes
@flask_app.route('/healthz')
def health():
    logger.info("Health check accessed")
    return 'OK', 200

@flask_app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook_handler():
    """Xử lý webhook từ Telegram"""
    logger.info("Received webhook update")
    
    try:
        json_data = request.get_json(force=True)
        logger.info("Update data: %s", json_data)
        
        # Tạo cập nhật từ dữ liệu JSON
        update = Update.de_json(json_data, application.bot)
        
        # Xử lý cập nhật
        application_event_loop.run_until_complete(application.process_update(update))
        
        return 'OK', 200
    except Exception as e:
        logger.error("Error in webhook handler: %s", str(e))
        # Trả về 200 dù có lỗi để Telegram không gửi lại update
        return 'Error', 200

@flask_app.route('/set_webhook', methods=['GET'])
def set_webhook_handler():
    """API endpoint để thiết lập webhook"""
    webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{TELEGRAM_TOKEN}"
    logger.info("Setting webhook to: %s", webhook_url)
    
    try:
        # Thiết lập webhook
        application_event_loop.run_until_complete(application.bot.set_webhook(url=webhook_url))
        return f"Webhook đã được thiết lập thành công tại: {webhook_url}", 200
    except Exception as e:
        logger.error("Failed to set webhook: %s", str(e))
        return f"Lỗi khi thiết lập webhook: {str(e)}", 500

def main():
    """Khởi động Flask server"""
    # Cổng mặc định cho Render
    port = int(os.getenv('PORT', 10000))
    logger.info(f"Starting Flask server on port {port}")
    flask_app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()
