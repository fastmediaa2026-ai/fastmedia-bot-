import logging
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)

# ============================================================
# CONFIGURATION
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BITE_STORE_API_KEY = os.getenv("BITE_STORE_API_KEY")
BASE_URL = "https://bite-store-bot-production.up.railway.app"
ADMIN_ID = 8079213467

# بيانات تعديلات الأدمن (مخزنة مؤقتاً في الذاكرة)
admin_edits = {"prices": {}, "descs": {}}

HEADERS = {"X-API-Key": BITE_STORE_API_KEY, "Content-Type": "application/json"}
PAYMENT_INFO = ("💳 *طرق الدفع:* فودافون كاش 01096056061\n⚡ إنستاباي 01559740555\n\n⚠️ أرسل صورة الإيصال بعد التحويل.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("fastmedia_bot")

pending_orders = {}
products_cache = {}

# ============================================================
# UTILS
# ============================================================
async def post_init(application: Application):
    await application.bot.set_my_commands([BotCommand("start", "🛒 فتح المتجر")])

def get_final_price(prod_id, original_price_usd):
    if str(prod_id) in admin_edits["prices"]:
        return admin_edits["prices"][str(prod_id)]
    return round(float(original_price_usd) * 2.0 * 53.0)

# ============================================================
# HANDLERS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_target = update.message if update.message else update.callback_query.message
    res = requests.get(f"{BASE_URL}/v1/products", headers=HEADERS, timeout=12)
    if res.status_code == 200:
        products = res.json()
        keyboard = []
        for prod in products:
            p_id = str(prod.get("id"))
            name = prod.get("name")
            price = get_final_price(p_id, prod.get("price", 0))
            products_cache[p_id] = {"name": name, "price": price}
            keyboard.append([InlineKeyboardButton(f"{name} | {price} ج.م", callback_data=f"view_{p_id}")])
        keyboard.append([InlineKeyboardButton("🎧 تواصل مع الدعم الفني", callback_data="contact_support")])
        await msg_target.reply_text("🛍️ *أهلاً بك في المتجر*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = query.data.split("_")[1]
    
    res = requests.get(f"{BASE_URL}/v1/products/{prod_id}", headers=HEADERS, timeout=5)
    p = res.json()
    name = p.get("name")
    desc = admin_edits["descs"].get(str(prod_id), p.get("description", "تسليم فوري ومضمون"))
    price = get_final_price(prod_id, p.get("price", 0))
    stock = p.get("stock", 0)

    text = f"📦 *{name}*\n📝 {desc}\n💰 *السعر:* `{price} ج.م`\n📊 *المتوفر:* {stock}"
    kb = [[InlineKeyboardButton("🛍️ شراء الآن", callback_data=f"buy_{prod_id}")]]
    
    if query.from_user.id == ADMIN_ID:
        kb.append([InlineKeyboardButton("✏️ تعديل السعر", callback_data=f"edit_price_{prod_id}"), 
                   InlineKeyboardButton("✏️ تعديل الوصف", callback_data=f"edit_desc_{prod_id}")])
    
    kb.append([InlineKeyboardButton("🎧 دعم فني", callback_data="contact_support"), InlineKeyboardButton("🔙 رجوع", callback_data="back")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# التعامل مع تعديلات الأدمن
async def edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, prod_id = query.data.split("_")[1], query.data.split("_")[2]
    context.user_data["editing"] = {"action": action, "prod_id": prod_id}
    await query.message.reply_text(f"✍️ اكتب {'السعر الجديد' if action == 'price' else 'الوصف الجديد'}:")

async def handle_admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("editing"): return
    edit = context.user_data.pop("editing")
    if edit["action"] == "price": admin_edits["prices"][edit["prod_id"]] = int(update.message.text)
    else: admin_edits["descs"][edit["prod_id"]] = update.message.text
    await update.message.reply_text("✅ تم التحديث بنجاح.")

# نظام الدعم الفني
async def request_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["waiting_support"] = True
    await update.callback_query.message.reply_text("✍️ اكتب استفسارك هنا:")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and context.user_data.get("replying"):
        target = context.user_data.pop("replying")
        await context.bot.send_message(chat_id=target, text=f"💬 *رد الدعم:* {update.message.text}", parse_mode="Markdown")
        await update.message.reply_text("✅ تم الرد.")
    elif context.user_data.get("waiting_support"):
        context.user_data["waiting_support"] = False
        kb = [[InlineKeyboardButton("↩️ الرد على العميل", callback_data=f"reply_to_{update.effective_user.id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 رسالة من @{update.effective_user.username}: {update.message.text}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("✅ تم إرسال رسالتك.")

async def start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["replying"] = int(query.data.split("_")[2])
    await query.message.reply_text("✍️ اكتب الرد:")

# إيصالات الطلبات
async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = query.data.split("_")[1]
    pending_orders[query.from_user.id] = prod_id
    await query.edit_message_text(f"🛒 تأكيد الدفع:\n{PAYMENT_INFO}\n\nأرسل صورة الإيصال.", parse_mode="Markdown")

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in pending_orders: return
    kb = [[InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{user_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, caption=f"🧾 طلب من {user_id}", reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("✅ تم إرسال الإيصال.")

async def approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[1])
    prod_id = pending_orders.pop(user_id)
    res = requests.post(f"{BASE_URL}/v1/orders", json={"product_id": int(prod_id)}, headers=HEADERS)
    if res.status_code == 200:
        await context.bot.send_message(chat_id=user_id, text=f"🎉 تم القبول. بياناتك: `{res.json().get('delivered_data')}`", parse_mode="Markdown")
        await query.edit_message_caption(caption="✅ تم.")

# ============================================================
# MAIN
# ============================================================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(view_product, pattern=r"^view_"))
    app.add_handler(CallbackQueryHandler(buy_product, pattern=r"^buy_"))
    app.add_handler(CallbackQueryHandler(edit_callback, pattern=r"^edit_"))
    app.add_handler(CallbackQueryHandler(start_reply, pattern=r"^reply_to_"))
    app.add_handler(CallbackQueryHandler(approve_order, pattern=r"^approve_"))
    app.add_handler(CallbackQueryHandler(request_support, pattern=r"^contact_support$"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_admin_edit))
    app.run_polling()

if __name__ == "__main__":
    main()
