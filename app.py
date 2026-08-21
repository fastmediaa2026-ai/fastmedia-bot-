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
    "⚠️ بعد التحويل اضغط على زر إرسال الإيصال بالأسفل وأرسل صورة التحويل."
)

pending_orders = {}
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

                if stock > 0:
                    products_cache[prod_id] = {
                        "name": name,
                        "price_egp": price_egp,
                        "stock": stock
                    }
                    short_name = name[:28] + "..." if len(name) > 28 else name
                    btn_text = f"✨ {short_name} | {price_egp} ج.م"
                    keyboard.append([
                        InlineKeyboardButton(
                            btn_text,
                            callback_data=f"view_{prod_id}"
                        )
                    ])

            keyboard.append([
                InlineKeyboardButton("🎧 تواصل مع الدعم الفني", callback_data="contact_support")
            ])

            if len(keyboard) > 1:
                reply_markup = InlineKeyboardMarkup(keyboard)
                await status_msg.edit_text(
                    "🛍️ *أهلاً بك في متجر Fastmedia Store*\n\n"
                    "اختر المنتج المطلوب لعرض التفاصيل والمواصفات 👇",
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
    cached = products_cache.get(prod_id, {})

    name = cached.get("name", "منتج رقمي")
    price_egp = cached.get("price_egp", 0)
    stock_count = cached.get("stock", 1)
    description = "تسليم فوري وبيانات رسمية ومضمونة بأعلى جودة."
    delivery_type = "توصيل تلقائي 🤖"
    format_type = "بيانات مباشرة 📎"
    sold_count = "0"

    try:
        res = requests.get(f"{BASE_URL}/v1/products/{prod_id}", headers=HEADERS, timeout=10)
        if res.status_code == 200:
            p_data = res.json()
            description = p_data.get("description") or p_data.get("desc") or description
            delivery_type = p_data.get("delivery_type") or p_data.get("type") or delivery_type
            format_type = p_data.get("format") or format_type
            sold_count = str(p_data.get("sold", p_data.get("sold_count", "0")))
            stock_count = p_data.get("stock", stock_count)
            name = p_data.get("name", name)
            if not price_egp:
                price_usd = float(p_data.get("price", 0))
                price_egp = round(price_usd * PROFIT_MARGIN * USD_TO_EGP)
    except Exception:
        pass

    products_cache[prod_id] = {
        "name": name,
        "price_egp": price_egp,
        "stock": stock_count,
        "desc": description
    }

    # تصميم الكارت باسم المنتج وسعرك بالجنيه فقط
    card_text = (
        f"📦 *{name}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {description}\n\n"
        f"💰 *السعر:* *{price_egp} جنيه مصري*\n"
        f"🚦 *الحالة:* ✅ متوفر للتسليم الفوري\n"
        f"📦 *نوع التسليم:* {delivery_type}\n"
        f"🧩 *طريقة الاستلام:* {format_type}\n"
        f"📊 *المتوفر بالمخزون:* {stock_count}\n"
        f"🔥 *عدد مرات البيع:* {sold_count}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [
        [InlineKeyboardButton("🛍️ شراء الآن | Buy Now", callback_data=f"buy_{prod_id}")],
        [InlineKeyboardButton("🎧 استفسار / الدعم الفني", callback_data="contact_support")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back")]
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


async def request_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["waiting_support_msg"] = True
    await query.edit_message_text(
        "✍️ *أهلاً بك في الدعم الفني!*\n\n"
        "اكتب رسالتك أو استفسارك هنا في الشات، وسيتم إرسالها للإدارة للرد عليك مباشرة.",
        parse_mode="Markdown"
    )


async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # رد الأدمن على العميل
    if user_id == ADMIN_ID and context.user_data.get("replying_to_user"):
        target_client_id = context.user_data.pop("replying_to_user")
        try:
            await context.bot.send_message(
                chat_id=target_client_id,
                text=f"💬 *رد الدعم الفني:*\n\n{text}",
                parse_mode="Markdown"
            )
            await update.message.reply_text("✅ تم إرسال ردك إلى العميل بنجاح.")
        except Exception:
            await update.message.reply_text("❌ تعذر إرسال الرد، ربما قام العميل بحظر البوت.")
        return

    # إرسال رسالة العميل إلى الأدمن
    if context.user_data.get("waiting_support_msg"):
        context.user_data["waiting_support_msg"] = False
        username = update.effective_user.username or update.effective_user.first_name

        admin_msg = (
            f"📩 *رسالة دعم فني جديدة*\n\n"
            f"👤 العميل: @{username} (`{user_id}`)\n"
            f"💬 نص الرسالة:\n{text}"
        )
        reply_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ الرد على العميل", callback_data=f"reply_to_{user_id}")]
        ])

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_msg,
            reply_markup=reply_btn,
            parse_mode="Markdown"
        )
        await update.message.reply_text("✅ تم إرسال استفسارك إلى الدعم الفني، وسيصلك الرد هنا مباشرة.")


async def start_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("غير مصرح لك", show_alert=True)
        return

    client_id = int(query.data.split("_")[2])
    context.user_data["replying_to_user"] = client_id

    await query.message.reply_text(f"✍️ اكتب الآن نص الرد الذي تريد إرساله للعميل `{client_id}`:")


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
                [InlineKeyboardButton("🎧 تواصل مع الدعم الفني", callback_data="contact_support")]
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
                [InlineKeyboardButton("🎧 تواصل مع الدعم الفني", callback_data="contact_support")]
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
        [InlineKeyboardButton("🎧 تواصل مع الإدارة", callback_data="contact_support")]
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
    application.add_handler(CallbackQueryHandler(request_support, pattern=r"^contact_support$"))
    application.add_handler(CallbackQueryHandler(start_admin_reply, pattern=r"^reply_to_"))
    application.add_handler(CallbackQueryHandler(approve_order, pattern=r"^approve_"))
    application.add_handler(CallbackQueryHandler(reject_order, pattern=r"^reject_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern=r"^back$"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text))

    logger.info("Starting bot with perfected product card and live support...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
