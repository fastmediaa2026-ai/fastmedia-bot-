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
    "⚠️ بعد التحويل اضغط على الزر بالأسفل وأرسل صورة الإيصال."
)

# تخزين الطلبات المؤقتة
pending_orders = {}


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
                    # زر أقصر عشان ما يتقصش
                    short_name = name[:32] + "..." if len(name) > 32 else name
                    btn_text = f"{short_name} | {price_egp} ج.م"
                    # بنبعت الاسم الكامل في الـ callback_data
                    keyboard.append([
                        InlineKeyboardButton(
                            btn_text,
                            callback_data=f"sel_{prod_id}_{price_egp}_{name}"
                        )
                    ])

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

    # نقسم الـ callback_data
    parts = query.data.split("_", 3)
    prod_id = parts[1]
    price_egp = parts[2]
    product_name = parts[3] if len(parts) > 3 else "المنتج"

    user_id = query.from_user.id
    pending_orders[user_id] = {
        "prod_id": prod_id,
        "price_egp": price_egp,
        "product_name": product_name,
        "username": query.from_user.username or query.from_user.first_name,
    }

    msg = (
        f"🛒 *تفاصيل الطلب:*\n\n"
        f"📦 *المنتج:* {product_name}\n"
        f"💵 *المبلغ المطلوب:* {price_egp} جنيه مصري\n\n"
        f"{PAYMENT_INFO}"
    )
    keyboard = [
        [InlineKeyboardButton("📤 لقد قمت بالتحويل - إرسال الإيصال", callback_data="send_receipt")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back")]
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

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 *تم تأكيد الدفع بنجاح!*\n\n"
                    f"📦 المنتج: {order['product_name']}\n\n"
                    f"📋 *البيانات/الكود الخاص بك:*\n`{delivered_key}`\n\n"
                    f"شكراً لتعاملك معنا ❤️"
                ),
                parse_mode="Markdown"
            )

            await query.edit_message_caption(
                caption=f"✅ تم الموافقة وإرسال المنتج للعميل `{user_id}` بنجاح."
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ حدثت مشكلة أثناء سحب المنتج. تواصل مع الدعم."
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

    await context.bot.send_message(
        chat_id=user_id,
        text="❌ عذراً، تم رفض إيصال الدفع.\nلو فيه مشكلة تواصل مع الإدارة."
    )

    await query.edit_message_caption(caption=f"❌ تم رفض الطلب الخاص بالعميل `{user_id}`.")


async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ جاري الرجوع للقائمة...")

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
    application.add_handler(CallbackQueryHandler(ask_for_receipt, pattern=r"^send_receipt$"))
    application.add_handler(CallbackQueryHandler(approve_order, pattern=r"^approve_"))
    application.add_handler(CallbackQueryHandler(reject_order, pattern=r"^reject_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern=r"^back$"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))

    logger.info("Starting bot with manual approval system...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
