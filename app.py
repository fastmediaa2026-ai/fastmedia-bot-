import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fastmedia_bot")

# ============================================================
# CONFIG (من Environment Variables)
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BITE_STORE_API_KEY = os.getenv("BITE_STORE_API_KEY")
BASE_URL = "https://bite-store-bot-production.up.railway.app"

USD_TO_EGP = 53.0
PROFIT_MARGIN = 2.0

HEADERS = {
    "X-API-Key": BITE_STORE_API_KEY,
    "Content-Type": "application/json"
}

PAYMENT_INFO = (
    "💳 *طرق الدفع المتاحة:*\n\n"
    "📱 *فودافون كاش:* `01096056061`\n"
    "⚡ *إنستاباي:* `01559740555`\n\n"
    "⚠️ بعد التحويل اضغط على زر *تأكيد الدفع واستلام الطلب* بالأسفل."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري جلب المنتجات والأسعار...")
    
    try:
        res = requests.get(f"{BASE_URL}/v1/products", headers=HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json()
            products = data if isinstance(data, list) else data.get("products", [])
            keyboard = []
            
            for prod in products:
                price_usd = float(prod.get("price", 0))
                price_egp = round(price_usd * PROFIT_MARGIN * USD_TO_EGP)
                stock = prod.get("stock", 0)
                name = prod.get("name", "Product")
                prod_id = prod.get("id")

                if stock > 0:
                    btn_text = f"✅ {name} | {price_egp} ج.م"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"sel_{prod_id}_{price_egp}")])
            
            if keyboard:
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🛒 *اختر المنتج المطلوب للشراء:*",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("⚠️ لا توجد منتجات متوفرة حالياً.")
        else:
            await update.message.reply_text("❌ تعذر الاتصال بالمتجر، يرجى المحاولة لاحقاً.")
    except Exception:
        logger.exception("Error in /start")
        await update.message.reply_text("❌ حدث خطأ أثناء الاتصال بالخادم.")


async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    prod_id = parts[1]
    price_egp = parts[2]
    
    msg = (
        f"🛒 *تفاصيل الطلب:*\n"
        f"💵 *المبلغ المطلوب:* {price_egp} جنيه مصري\n\n"
        f"{PAYMENT_INFO}"
    )
    keyboard = [
        [InlineKeyboardButton("✅ تأكيد الدفع واستلام الطلب", callback_data=f"buy_{prod_id}")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back")]
    ]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    prod_id = query.data.split("_")[1]
    await query.edit_message_text("⏳ جاري تنفيذ الطلب وسحب البيانات فوراً...")

    try:
        payload = {"product_id": int(prod_id) if str(prod_id).isdigit() else prod_id}
        res = requests.post(f"{BASE_URL}/v1/orders", json=payload, headers=HEADERS, timeout=15)
        
        if res.status_code == 200:
            order_data = res.json()
            delivered_key = (
                order_data.get("delivered_data")
                or order_data.get("key")
                or order_data.get("item")
                or "تم تنفيذ طلبك بنجاح!"
            )
            await query.message.reply_text(
                f"🎉 *تم استلام طلبك بنجاح!*\n\n📋 *البيانات/الكود:*\n`{delivered_key}`",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("❌ تعذر الشراء (تأكد من شحن رصيد المحفظة بالمتجر أو توفر الكمية).")
    except Exception:
        logger.exception("Error in buy_product")
        await query.message.reply_text("❌ حدث خطأ في الاتصال بالخادم أثناء إتمام الطلب.")


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)  # هنعدلها تحت


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # نرسل رسالة جديدة
    class FakeUpdate:
        def __init__(self, message):
            self.message = message
    await start(FakeUpdate(query.message), context)


def main():
    if not TELEGRAM_TOKEN or not BITE_STORE_API_KEY:
        logger.error("TELEGRAM_TOKEN or BITE_STORE_API_KEY is missing!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(select_product, pattern=r"^sel_"))
    application.add_handler(CallbackQueryHandler(buy_product, pattern=r"^buy_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern=r"^back$"))

    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)
    logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
