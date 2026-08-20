import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = "8950574142:AAEfyRo3YEpfmcJvual-YtabONsp7kJnz8w"
BITE_STORE_API_KEY = "bsk_wAcyzJdgjXGJL9S3VAd-9UQ92g7IGDu_zwF7_tDo1og"
BASE_URL = "https://bite-store-bot-production.up.railway.app"

USD_TO_EGP = 53.0
PROFIT_MARGIN = 2.0  # زيادة 100% قطاعي

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
        res = requests.get(f"{BASE_URL}/v1/products", headers=HEADERS, timeout=10)
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
                await update.message.reply_text("🛒 *اختر المنتج المطلوب للشراء:*", reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await update.message.reply_text("⚠️ لا توجد منتجات متوفرة حالياً.")
        else:
            await update.message.reply_text("❌ تعذر الاتصال بالمتجر، يرجى المحاولة لاحقاً.")
    except Exception:
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
        payload = {"product_id": int(prod_id) if prod_id.isdigit() else prod_id}
        res = requests.post(f"{BASE_URL}/v1/orders", json=payload, headers=HEADERS, timeout=15)
        
        if res.status_code == 200:
            order_data = res.json()
            delivered_key = order_data.get("delivered_data") or order_data.get("key") or order_data.get("item") or "تم تنفيذ طلبك بنجاح!"
            await query.message.reply_text(f"🎉 *تم استلام طلبك بنجاح!*\n\n📋 *البيانات/الكود:*\n`{delivered_key}`", parse_mode="Markdown")
        else:
            await query.message.reply_text("❌ تعذر الشراء (تأكد من شحن رصيد المحفظة بالمتجر أو توفر الكمية).")
    except Exception:
        await query.message.reply_text("❌ حدث خطأ في الاتصال بالخادم أثناء إتمام الطلب.")

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(query, context)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_product, pattern="^sel_"))
    app.add_handler(CallbackQueryHandler(buy_product, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back$"))
    app.run_polling()

if __name__ == "__main__":
    main()
