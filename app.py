import logging
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fastmedia_bot")

# ============================================================
# CONFIG
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BITE_STORE_API_KEY = os.getenv("BITE_STORE_API_KEY")
BASE_URL = "https://bite-store-bot-production.up.railway.app"

ADMIN_ID = 8079213467

# يوزر حسابك المباشر
SUPPORT_USERNAME = "Fastmedia1"

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
    "⚠️ بعد التحويل اضغط على زر إرسال الإيصال بالأسفل وأرسل صورة التحويل."
)

# تخزين الطلبات المؤقتة
pending_orders = {}
# تخزين بيانات المنتجات كاملة (prod_id -> dict)
products_cache = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_target = update.message if update.message else update.callback_query.message
    status_msg = await msg_target.reply_text("⏳ جاري جلب المنتجات والأسعار...")

    try:
        res = requests.get(f"{BASE_URL}/v1/products", headers=HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json()
            products = data if isinstance(data, list) else data.get("products", [])
            keyboard = []
            products_cache.clear()

            for prod in products:
                price_usd = float(prod.get("price", 0))
                price_egp = round(price_usd * PROFIT_MARGIN * USD_TO_EGP)
                stock = prod.get("stock", 0)
                name = prod.get("name", "Product")
                prod_id = str(prod.get("id"))
                desc = prod.get("description") or prod.get("desc") or "تسليم فوري وبيانات رسمية ومضمونة."
                delivery_type = prod.get("delivery_type") or "تلقائي 🤖"

                if stock > 0:
                    products_cache[prod_id] = {
                        "name": name,
                        "price_egp": price_egp,
                        "stock": stock,
                        "desc": desc,
                        "delivery_type": delivery_type
                    }
                    short_name = name[:28] + "..." if len(name) > 28 else name
                    btn_text = f"✨ {short_name} | {price_egp} ج.م"
                    keyboard.append([
                        InlineKeyboardButton(
                            btn_text,
                            callback_data=f"view_{prod_id}"
                        )
                    ])

            # زر الدعم الفني في أسفل القائمة الرئيسية
            keyboard.append([
                InlineKeyboardButton("🎧 الدعم الفني والمساعدة", url=f"https://t.me/{SUPPORT_USERNAME}")
            ])

            if len(keyboard) > 1:
                reply_markup = InlineKeyboardMarkup(keyboard)
                await status_msg.edit_text(
                    "🛍️ *أهلاً بك في متجر Fastmedia Store*\n\n"
                    "اختر المنتج المطلوب من القائمة لعرض التفاصيل والشراء 👇",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await status_msg.edit_text("⚠️ لا توجد منتجات متوفرة حالياً.")
        else:
            await status_msg.edit_text("❌ تعذر الاتصال بالمتجر، يرجى المحاولة لاحقاً.")
    except Exception:
        logger.exception("Error in /start")
        await status_msg.edit_text("❌ حدث خطأ أثناء الاتصال بالخادم.")


async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prod_id = query.data.split("_")[1]
    prod = products_cache.get(prod_id)

    if not prod:
        await query.edit_message_text("⚠️ لم يتم العثور على تفاصيل المنتج، يرجى الرجوع للقائمة عبر /start")
        return

    card_text = (
        f"📦 *{prod['name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *الوصف:* {prod['desc']}\n\n"
        f"💰 *السعر:* `{prod['price_egp']} جنيه مصري`\n"
        f"🚦 *الحالة:* ✅ متوفر وجاهز للتسليم\n"
        f"📦 *نوع التسليم:* {prod['delivery_type']}\n"
        f"📊 *المتوفر بالمخزون:* {prod['stock']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اضغط على *شراء الآن* لإتمام الدفع واستلام الطلب:"
    )

    keyboard = [
        [InlineKeyboardButton("🛍️ شراء الآن", callback_data=f"buy_{prod_id}")],
        [InlineKeyboardButton("🎧 استفسار / الدعم الفني", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("🔙 رجوع لقائمة المنتجات", callback_data="back")]
    ]

    await query.edit_message_text(card_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prod_id = query.data.split("_")[1]
    prod = products_cache.get(prod_id)

    if not prod:
        await query.edit_message_text("⚠️ انتهت صلاحية الجلسة، ابدأ من جديد بـ /start")
        return

    user_id = query.from_user.id
    pending_orders[user_id] = {
        "prod_id": prod_id,
        "price_egp": prod["price_egp"],
        "product_name": prod["name"],
        "username": query.from_user.username or query.from_user.first_name,
    }

    msg = (
        f"🛒 *تأكيد طلب الشراء:*\n\n"
        f"📦 *المنتج:* {prod['name']}\n"
        f"💵 *المبلغ المطلوب:* *{prod['price_egp']} جنيه مصري*\n\n"
        f"{PAYMENT_INFO}"
    )
    keyboard = [
        [InlineKeyboardButton("📤 لقد قمت بالتحويل - إرسال الإيصال", callback_data="send_receipt")],
        [InlineKeyboardButton("🔙 رجوع لتفاصيل المنتج", callback_data=f"view_{prod_id}")]
    ]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def ask_for_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in pending_orders:
        await query.edit_message_text("⚠️ انتهت صلاحية الطلب، ابدأ من جديد بـ /start")
        return

    await query.edit_message_text(
        "📸 *من فضلك أرسل صورة إيصال التحويل الآن.*\n\n"
        "بعد إرسال الصورة سيتم مراجعتها من الإدارة، وستصلك البيانات فور الموافقة.",
        parse_mode="Markdown"
    )
    context.user_data["waiting_receipt"] = True


async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.user_data.get("waiting_receipt"):
        return

    if user_id not in pending_orders:
        await update.message.reply_text("⚠️ انتهت صلاحية الطلب، ابدأ من جديد بـ /start")
        context.user_data["waiting_receipt"] = False
        return

    order = pending_orders[user_id]
    context.user_data["waiting_receipt"] = False

    caption = (
        f"🧾 *طلب جديد بانتظار المراجعة*\n\n"
        f"👤 العميل: @{order['username']} (`{user_id}`)\n"
        f"📦 المنتج: {order['product_name']}\n"
        f"💵 المبلغ: *{order['price_egp']} جنيه*\n"
        f"🆔 Product ID: `{order['prod_id']}`\n\n"
        f"اضغط للموافقة أو الرفض:"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ موافقة وإرسال المنتج", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
        ]
    ]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    await update.message.reply_text(
        "✅ تم استلام الإيصال بنجاح.\n"
        "⏳ جاري مراجعة الدفع من الإدارة...\n"
        "هتوصلك البيانات فور الموافقة."
    )


async def approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("غير مصرح لك", show_alert=True)
        return

    user_id = int(query.data.split("_")[1])

    if user_id not in pending_orders:
        await query.edit_message_caption(caption="⚠️ هذا الطلب انتهت صلاحيته أو تم التعامل معه مسبقاً.")
        return

    order = pending_orders[user_id]
    prod_id = order["prod_id"]

    await query.edit_message_caption(caption="⏳ جاري سحب المنتج وإرساله للعميل...")

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

            support_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎧 تواصل مع الدعم الفني", url=f"https://t.me/{SUPPORT_USERNAME}")]
            ])

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 *تم تأكيد الدفع بنجاح!*\n\n"
                    f"📦 المنتج: {order['product_name']}\n\n"
                    f"📋 *البيانات/الكود الخاص بك:*\n`{delivered_key}`\n\n"
                    f"شكراً لتعاملك معنا ❤️"
                ),
                reply_markup=support_btn,
                parse_mode="Markdown"
            )

            await query.edit_message_caption(
                caption=f"✅ تم الموافقة وإرسال المنتج للعميل `{user_id}` بنجاح."
            )
        else:
            support_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎧 تواصل مع الدعم الفني", url=f"https://t.me/{SUPPORT_USERNAME}")]
            ])
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ حدثت مشكلة أثناء سحب المنتج. يرجى الضغط بالأسفل للتواصل مع الدعم.",
                reply_markup=support_btn
            )
            await query.edit_message_caption(
                caption="❌ فشل سحب المنتج من المتجر (تأكد من الرصيد أو الكمية)."
            )
    except Exception:
        logger.exception("Error approving order")
        await query.edit_message_caption(caption="❌ حصل خطأ أثناء تنفيذ الطلب.")

    pending_orders.pop(user_id, None)


async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("غير مصرح لك", show_alert=True)
        return

    user_id = int(query.data.split("_")[1])

    if user_id in pending_orders:
        pending_orders.pop(user_id)

    support_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 تواصل مع الإدارة", url=f"https://t.me/{SUPPORT_USERNAME}")]
    ])

    await context.bot.send_message(
        chat_id=user_id,
        text="❌ عذراً، تم رفض إيصال الدفع.\nإذا كان هناك خطأ تواصل مع الإدارة مباشرة.",
        reply_markup=support_btn
    )

    await query.edit_message_caption(caption=f"❌ تم رفض الطلب الخاص بالعميل `{user_id}`.")


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


def main():
    if not TELEGRAM_TOKEN or not BITE_STORE_API_KEY:
        logger.error("TELEGRAM_TOKEN or BITE_STORE_API_KEY is missing!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(view_product, pattern=r"^view_"))
    application.add_handler(CallbackQueryHandler(buy_product, pattern=r"^buy_"))
    application.add_handler(CallbackQueryHandler(ask_for_receipt, pattern=r"^send_receipt$"))
    application.add_handler(CallbackQueryHandler(approve_order, pattern=r"^approve_"))
    application.add_handler(CallbackQueryHandler(reject_order, pattern=r"^reject_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern=r"^back$"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))

    logger.info("Starting bot with manual approval system...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
