import logging
import os
import json
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

# ============================================================
# MANUAL PRICES
# ============================================================
# الأسعار اليدوية للمنتجات.
#
# إذا كان المنتج غير موجود هنا:
# سيتم استخدام المعادلة التلقائية.
#
# مثال:
# {
#     "123": 250,
#     "456": 180
# }
#
# يتم حفظ الأسعار في ملف JSON حتى لا تضيع بعد Restart.
# ============================================================

MANUAL_PRICES_FILE = "manual_prices.json"


def load_manual_prices():
    """تحميل الأسعار اليدوية من الملف."""
    try:
        if os.path.exists(MANUAL_PRICES_FILE):
            with open(MANUAL_PRICES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

                if isinstance(data, dict):
                    return data

    except Exception:
        logger.exception("Error loading manual prices")

    return {}


def save_manual_prices():
    """حفظ الأسعار اليدوية."""
    try:
        with open(MANUAL_PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump(
                manual_prices,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception:
        logger.exception("Error saving manual prices")


manual_prices = load_manual_prices()

# ============================================================
# HEADERS
# ============================================================
HEADERS = {
    "X-API-Key": BITE_STORE_API_KEY,
    "Content-Type": "application/json"
}

# ============================================================
# PAYMENT INFO
# ============================================================
PAYMENT_INFO = (
    "💳 *طرق الدفع المتاحة:*\n\n"
    "📱 *فودافون كاش:* `01096056061`\n"
    "⚡ *إنستاباي:* `01559740555`\n\n"
    "⚠️ بعد التحويل اضغط على زر إرسال الإيصال بالأسفل وأرسل صورة التحويل."
)

# ============================================================
# MEMORY
# ============================================================
pending_orders = {}
products_cache = {}

# ============================================================
# PRICE FUNCTIONS
# ============================================================


def calculate_price(price_usd):
    """
    السعر التلقائي حسب المعادلة الحالية.
    """
    return round(
        float(price_usd) * PROFIT_MARGIN * USD_TO_EGP
    )


def get_product_price(prod_id, price_usd):
    """
    الحصول على سعر المنتج.

    إذا كان هناك سعر يدوي:
        يستخدم السعر اليدوي.

    إذا لم يوجد:
        يستخدم المعادلة التلقائية.
    """

    prod_id = str(prod_id)

    if prod_id in manual_prices:
        return int(manual_prices[prod_id])

    return calculate_price(price_usd)


# ============================================================
# START
# ============================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_target = (
        update.message
        if update.message
        else update.callback_query.message
    )

    status_msg = await msg_target.reply_text(
        "⏳ جاري جلب المنتجات والأسعار..."
    )

    try:
        res = requests.get(
            f"{BASE_URL}/v1/products",
            headers=HEADERS,
            timeout=12
        )

        if res.status_code == 200:

            data = res.json()

            products = (
                data
                if isinstance(data, list)
                else data.get("products", [])
            )

            keyboard = []

            products_cache.clear()

            for prod in products:

                price_usd = float(prod.get("price", 0))

                prod_id = str(prod.get("id"))

                price_egp = get_product_price(
                    prod_id,
                    price_usd
                )

                stock = prod.get("stock", 0)

                name = prod.get(
                    "name",
                    "Product"
                )

                if stock > 0:

                    products_cache[prod_id] = {
                        "name": name,
                        "price_egp": price_egp,
                        "stock": stock,
                        "price_usd": price_usd
                    }

                    short_name = (
                        name[:28] + "..."
                        if len(name) > 28
                        else name
                    )

                    btn_text = (
                        f"✨ {short_name} | "
                        f"{price_egp} ج.م"
                    )

                    keyboard.append([
                        InlineKeyboardButton(
                            btn_text,
                            callback_data=f"view_{prod_id}"
                        )
                    ])

            keyboard.append([
                InlineKeyboardButton(
                    "🎧 تواصل مع الدعم الفني",
                    callback_data="contact_support"
                )
            ])

            if len(keyboard) > 1:

                reply_markup = InlineKeyboardMarkup(
                    keyboard
                )

                await status_msg.edit_text(
                    "🛍️ *أهلاً بك في متجر Fastmedia Store*\n\n"
                    "اختر المنتج المطلوب لعرض التفاصيل والمواصفات 👇",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )

            else:

                await status_msg.edit_text(
                    "⚠️ لا توجد منتجات متوفرة حالياً."
                )

        else:

            await status_msg.edit_text(
                "❌ تعذر الاتصال بالمتجر، يرجى المحاولة لاحقاً."
            )

    except Exception:

        logger.exception("Error in /start")

        await status_msg.edit_text(
            "❌ حدث خطأ أثناء الاتصال بالخادم."
        )


# ============================================================
# VIEW PRODUCT
# ============================================================


async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    prod_id = query.data.split("_", 1)[1]

    cached = products_cache.get(
        prod_id,
        {}
    )

    name = cached.get(
        "name",
        "منتج رقمي"
    )

    price_egp = cached.get(
        "price_egp",
        0
    )

    stock_count = cached.get(
        "stock",
        1
    )

    description = (
        "تسليم فوري وبيانات رسمية ومضمونة بأعلى جودة."
    )

    delivery_type = "توصيل تلقائي 🤖"

    format_type = "بيانات مباشرة 📎"

    sold_count = "0"

    price_usd = cached.get(
        "price_usd",
        0
    )

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products/{prod_id}",
            headers=HEADERS,
            timeout=10
        )

        if res.status_code == 200:

            p_data = res.json()

            description = (
                p_data.get("description")
                or p_data.get("desc")
                or description
            )

            delivery_type = (
                p_data.get("delivery_type")
                or p_data.get("type")
                or delivery_type
            )

            format_type = (
                p_data.get("format")
                or format_type
            )

            sold_count = str(
                p_data.get(
                    "sold",
                    p_data.get(
                        "sold_count",
                        "0"
                    )
                )
            )

            stock_count = p_data.get(
                "stock",
                stock_count
            )

            name = p_data.get(
                "name",
                name
            )

            price_usd = float(
                p_data.get(
                    "price",
                    price_usd
                )
            )

            # مهم:
            # إعادة حساب السعر هنا أيضًا
            # مع احترام السعر اليدوي.
            price_egp = get_product_price(
                prod_id,
                price_usd
            )

    except Exception:

        logger.exception(
            "Error loading product details"
        )

    products_cache[prod_id] = {
        "name": name,
        "price_egp": price_egp,
        "stock": stock_count,
        "desc": description,
        "price_usd": price_usd
    }

    # ========================================================
    # PRODUCT CARD
    # ========================================================

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
        [
            InlineKeyboardButton(
                "🛍️ شراء الآن | Buy Now",
                callback_data=f"buy_{prod_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🎧 استفسار / الدعم الفني",
                callback_data="contact_support"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع للقائمة",
                callback_data="back"
            )
        ]
    ]

    await query.edit_message_text(
        card_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ============================================================
# BUY PRODUCT
# ============================================================


async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    prod_id = query.data.split("_", 1)[1]

    prod = products_cache.get(prod_id)

    if not prod:

        await query.edit_message_text(
            "⚠️ انتهت صلاحية الجلسة، ابدأ من جديد بـ /start"
        )

        return

    user_id = query.from_user.id

    pending_orders[user_id] = {
        "prod_id": prod_id,
        "price_egp": prod["price_egp"],
        "product_name": prod["name"],
        "username": (
            query.from_user.username
            or query.from_user.first_name
        ),
    }

    msg = (
        f"🛒 *تأكيد طلب الشراء:*\n\n"
        f"📦 *المنتج:* {prod['name']}\n"
        f"💵 *المبلغ المطلوب:* "
        f"*{prod['price_egp']} جنيه مصري*\n\n"
        f"{PAYMENT_INFO}"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📤 لقد قمت بالتحويل - إرسال الإيصال",
                callback_data="send_receipt"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع لتفاصيل المنتج",
                callback_data=f"view_{prod_id}"
            )
        ]
    ]

    await query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ============================================================
# ASK FOR RECEIPT
# ============================================================


async def ask_for_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    if user_id not in pending_orders:

        await query.edit_message_text(
            "⚠️ انتهت صلاحية الطلب، ابدأ من جديد بـ /start"
        )

        return

    await query.edit_message_text(
        "📸 *من فضلك أرسل صورة إيصال التحويل الآن.*\n\n"
        "بعد إرسال الصورة سيتم مراجعتها من الإدارة، "
        "وستصلك البيانات فور الموافقة.",
        parse_mode="Markdown"
    )

    context.user_data["waiting_receipt"] = True


# ============================================================
# SUPPORT
# ============================================================


async def request_support(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    context.user_data["waiting_support_msg"] = True

    await query.edit_message_text(
        "✍️ *أهلاً بك في الدعم الفني!*\n\n"
        "اكتب رسالتك أو استفسارك هنا في الشات، "
        "وسيتم إرسالها للإدارة للرد عليك مباشرة.",
        parse_mode="Markdown"
    )


# ============================================================
# USER TEXT
# ============================================================


async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    text = update.message.text

    # ========================================================
    # ADMIN REPLY
    # ========================================================

    if (
        user_id == ADMIN_ID
        and context.user_data.get("replying_to_user")
    ):

        target_client_id = context.user_data.pop(
            "replying_to_user"
        )

        try:

            await context.bot.send_message(
                chat_id=target_client_id,
                text=(
                    f"💬 *رد الدعم الفني:*\n\n"
                    f"{text}"
                ),
                parse_mode="Markdown"
            )

            await update.message.reply_text(
                "✅ تم إرسال ردك إلى العميل بنجاح."
            )

        except Exception:

            await update.message.reply_text(
                "❌ تعذر إرسال الرد، ربما قام العميل بحظر البوت."
            )

        return

    # ========================================================
    # MANUAL PRICE INPUT
    # ========================================================

    if (
        user_id == ADMIN_ID
        and context.user_data.get("editing_price")
    ):

        prod_id = context.user_data.pop(
            "editing_price"
        )

        try:

            # السماح بأرقام صحيحة أو عشرية
            new_price = float(
                text.replace(",", ".").strip()
            )

            if new_price <= 0:

                await update.message.reply_text(
                    "❌ السعر يجب أن يكون أكبر من صفر."
                )

                return

            # نحفظ السعر اليدوي
            manual_prices[str(prod_id)] = int(
                round(new_price)
            )

            save_manual_prices()

            # تحديث الكاش لو المنتج موجود
            if prod_id in products_cache:

                products_cache[prod_id][
                    "price_egp"
                ] = manual_prices[str(prod_id)]

            await update.message.reply_text(
                f"✅ تم تعديل سعر المنتج.\n\n"
                f"🆔 Product ID: `{prod_id}`\n"
                f"💰 السعر الجديد: "
                f"*{manual_prices[str(prod_id)]} جنيه*",
                parse_mode="Markdown"
            )

        except ValueError:

            # إعادة الحالة حتى يستطيع المحاولة مرة أخرى
            context.user_data["editing_price"] = prod_id

            await update.message.reply_text(
                "❌ من فضلك أرسل السعر كرقم فقط.\n\n"
                "مثال:\n"
                "`250`",
                parse_mode="Markdown"
            )

        return

    # ========================================================
    # SUPPORT MESSAGE
    # ========================================================

    if context.user_data.get("waiting_support_msg"):

        context.user_data["waiting_support_msg"] = False

        username = (
            update.effective_user.username
            or update.effective_user.first_name
        )

        admin_msg = (
            f"📩 *رسالة دعم فني جديدة*\n\n"
            f"👤 العميل: @{username} (`{user_id}`)\n"
            f"💬 نص الرسالة:\n{text}"
        )

        reply_btn = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "↩️ الرد على العميل",
                    callback_data=f"reply_to_{user_id}"
                )
            ]
        ])

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_msg,
            reply_markup=reply_btn,
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            "✅ تم إرسال استفسارك إلى الدعم الفني، "
            "وسيصلك الرد هنا مباشرة."
        )


# ============================================================
# ADMIN REPLY
# ============================================================


async def start_admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    client_id = int(
        query.data.split("_")[2]
    )

    context.user_data[
        "replying_to_user"
    ] = client_id

    await query.message.reply_text(
        f"✍️ اكتب الآن نص الرد الذي تريد إرساله "
        f"للعميل `{client_id}`:"
    )


# ============================================================
# HANDLE RECEIPT
# ============================================================


async def handle_receipt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not context.user_data.get(
        "waiting_receipt"
    ):

        return

    if user_id not in pending_orders:

        await update.message.reply_text(
            "⚠️ انتهت صلاحية الطلب، "
            "ابدأ من جديد بـ /start"
        )

        context.user_data[
            "waiting_receipt"
        ] = False

        return

    order = pending_orders[user_id]

    context.user_data[
        "waiting_receipt"
    ] = False

    caption = (
        f"🧾 *طلب جديد بانتظار المراجعة*\n\n"
        f"👤 العميل: @{order['username']} "
        f"(`{user_id}`)\n"
        f"📦 المنتج: {order['product_name']}\n"
        f"💵 المبلغ: "
        f"*{order['price_egp']} جنيه*\n"
        f"🆔 Product ID: `{order['prod_id']}`\n\n"
        f"اضغط للموافقة أو الرفض:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ موافقة وإرسال المنتج",
                callback_data=f"approve_{user_id}"
            ),
            InlineKeyboardButton(
                "❌ رفض",
                callback_data=f"reject_{user_id}"
            )
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


# ============================================================
# APPROVE ORDER
# ============================================================


async def approve_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    user_id = int(
        query.data.split("_")[1]
    )

    if user_id not in pending_orders:

        await query.edit_message_caption(
            caption=(
                "⚠️ هذا الطلب انتهت صلاحيته "
                "أو تم التعامل معه مسبقاً."
            )
        )

        return

    order = pending_orders[user_id]

    prod_id = order["prod_id"]

    await query.edit_message_caption(
        caption="⏳ جاري سحب المنتج وإرساله للعميل..."
    )

    try:

        payload = {
            "product_id": (
                int(prod_id)
                if str(prod_id).isdigit()
                else prod_id
            )
        }

        res = requests.post(
            f"{BASE_URL}/v1/orders",
            json=payload,
            headers=HEADERS,
            timeout=15
        )

        if res.status_code == 200:

            order_data = res.json()

            delivered_key = (
                order_data.get("delivered_data")
                or order_data.get("key")
                or order_data.get("item")
                or "تم تنفيذ طلبك بنجاح!"
            )

            support_btn = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🎧 تواصل مع الدعم الفني",
                        callback_data="contact_support"
                    )
                ]
            ])

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 *تم تأكيد الدفع بنجاح!*\n\n"
                    f"📦 المنتج: {order['product_name']}\n\n"
                    f"📋 *البيانات/الكود الخاص بك:*\n"
                    f"`{delivered_key}`\n\n"
                    f"شكراً لتعاملك معنا ❤️"
                ),
                reply_markup=support_btn,
                parse_mode="Markdown"
            )

            await query.edit_message_caption(
                caption=(
                    f"✅ تم الموافقة وإرسال المنتج "
                    f"للعميل `{user_id}` بنجاح."
                )
            )

        else:

            support_btn = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🎧 تواصل مع الدعم الفني",
                        callback_data="contact_support"
                    )
                ]
            ])

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "❌ حدثت مشكلة أثناء سحب المنتج. "
                    "يرجى الضغط بالأسفل للتواصل مع الدعم."
                ),
                reply_markup=support_btn
            )

            await query.edit_message_caption(
                caption=(
                    "❌ فشل سحب المنتج من المتجر "
                    "(تأكد من الرصيد أو الكمية)."
                )
            )

    except Exception:

        logger.exception(
            "Error approving order"
        )

        await query.edit_message_caption(
            caption="❌ حصل خطأ أثناء تنفيذ الطلب."
        )

    pending_orders.pop(
        user_id,
        None
    )


# ============================================================
# REJECT ORDER
# ============================================================


async def reject_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    user_id = int(
        query.data.split("_")[1]
    )

    if user_id in pending_orders:

        pending_orders.pop(user_id)

    support_btn = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎧 تواصل مع الإدارة",
                callback_data="contact_support"
            )
        ]
    ])

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "❌ عذراً، تم رفض إيصال الدفع.\n"
            "إذا كان هناك خطأ تواصل مع الإدارة مباشرة."
        ),
        reply_markup=support_btn
    )

    await query.edit_message_caption(
        caption=(
            f"❌ تم رفض الطلب الخاص بالعميل "
            f"`{user_id}`."
        )
    )


# ============================================================
# ADMIN PRICE PANEL
# ============================================================


async def prices_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ غير مصرح لك."
        )

        return

    await show_price_panel(
        update.message,
        context
    )


async def show_price_panel(
    target,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products",
            headers=HEADERS,
            timeout=12
        )

        if res.status_code != 200:

            await target.reply_text(
                "❌ تعذر جلب المنتجات من المتجر."
            )

            return

        data = res.json()

        products = (
            data
            if isinstance(data, list)
            else data.get("products", [])
        )

        keyboard = []

        for prod in products:

            prod_id = str(
                prod.get("id")
            )

            name = prod.get(
                "name",
                "Product"
            )

            price_usd = float(
                prod.get(
                    "price",
                    0
                )
            )

            automatic_price = calculate_price(
                price_usd
            )

            if prod_id in manual_prices:

                current_price = manual_prices[
                    prod_id
                ]

                mode = "✏️ يدوي"

            else:

                current_price = automatic_price

                mode = "🔄 تلقائي"

            short_name = (
                name[:25] + "..."
                if len(name) > 25
                else name
            )

            keyboard.append([
                InlineKeyboardButton(
                    (
                        f"📦 {short_name}\n"
                        f"💰 {current_price} ج.م "
                        f"| {mode}"
                    ),
                    callback_data=f"price_{prod_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "❌ إغلاق",
                callback_data="price_close"
            )
        ])

        await target.reply_text(
            "⚙️ *إدارة أسعار المنتجات*\n\n"
            "السعر التلقائي يعتمد على:\n"
            f"`USD × {PROFIT_MARGIN} × {USD_TO_EGP}`\n\n"
            "اضغط على المنتج لتعديل سعره أو إعادته للسعر التلقائي:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode="Markdown"
        )

    except Exception:

        logger.exception(
            "Error showing price panel"
        )

        await target.reply_text(
            "❌ حدث خطأ أثناء جلب الأسعار."
        )


# ============================================================
# PRICE PRODUCT
# ============================================================


async def price_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    prod_id = query.data.split(
        "_",
        1
    )[1]

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products/{prod_id}",
            headers=HEADERS,
            timeout=10
        )

        if res.status_code != 200:

            await query.answer(
                "تعذر جلب بيانات المنتج",
                show_alert=True
            )

            return

        p_data = res.json()

        name = p_data.get(
            "name",
            "منتج"
        )

        price_usd = float(
            p_data.get(
                "price",
                0
            )
        )

        automatic_price = calculate_price(
            price_usd
        )

        if prod_id in manual_prices:

            current_price = manual_prices[
                prod_id
            ]

            current_mode = "✏️ سعر يدوي"

        else:

            current_price = automatic_price

            current_mode = "🔄 سعر تلقائي"

        text = (
            f"⚙️ *إدارة سعر المنتج*\n\n"
            f"📦 *المنتج:* {name}\n"
            f"🆔 Product ID: `{prod_id}`\n\n"
            f"💵 سعر API: `${price_usd}`\n"
            f"🔄 السعر بالمعادلة: "
            f"*{automatic_price} جنيه*\n"
            f"💰 السعر الحالي: "
            f"*{current_price} جنيه*\n"
            f"📌 الوضع: *{current_mode}*\n\n"
            f"اختر ما تريد:"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "✏️ تعديل السعر",
                    callback_data=f"editprice_{prod_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 استخدام السعر التلقائي",
                    callback_data=f"autoprice_{prod_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data="prices_back"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode="Markdown"
        )

    except Exception:

        logger.exception(
            "Error opening price product"
        )

        await query.answer(
            "حدث خطأ",
            show_alert=True
        )


# ============================================================
# EDIT PRICE
# ============================================================


async def edit_price(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    prod_id = query.data.split(
        "_",
        1
    )[1]

    context.user_data[
        "editing_price"
    ] = prod_id

    await query.message.reply_text(
        f"✏️ *تعديل سعر المنتج*\n\n"
        f"🆔 Product ID: `{prod_id}`\n\n"
        f"أرسل الآن السعر الذي تريده بالجنيه المصري.\n\n"
        f"مثال:\n"
        f"`250`",
        parse_mode="Markdown"
    )


# ============================================================
# RESET TO AUTOMATIC
# ============================================================


async def reset_auto_price(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    prod_id = query.data.split(
        "_",
        1
    )[1]

    if prod_id in manual_prices:

        manual_prices.pop(
            prod_id,
            None
        )

        save_manual_prices()

    if prod_id in products_cache:

        try:

            price_usd = products_cache[
                prod_id
            ].get(
                "price_usd",
                0
            )

            products_cache[
                prod_id
            ]["price_egp"] = calculate_price(
                price_usd
            )

        except Exception:

            pass

    await query.answer(
        "✅ تم الرجوع للسعر التلقائي"
    )

    # إعادة فتح بطاقة السعر
    fake_update = None

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products/{prod_id}",
            headers=HEADERS,
            timeout=10
        )

        if res.status_code == 200:

            p_data = res.json()

            name = p_data.get(
                "name",
                "منتج"
            )

            price_usd = float(
                p_data.get(
                    "price",
                    0
                )
            )

            automatic_price = calculate_price(
                price_usd
            )

            text = (
                f"⚙️ *إدارة سعر المنتج*\n\n"
                f"📦 *المنتج:* {name}\n"
                f"🆔 Product ID: `{prod_id}`\n\n"
                f"💵 سعر API: `${price_usd}`\n"
                f"🔄 السعر بالمعادلة: "
                f"*{automatic_price} جنيه*\n"
                f"💰 السعر الحالي: "
                f"*{automatic_price} جنيه*\n"
                f"📌 الوضع: *🔄 سعر تلقائي*\n\n"
                f"اختر ما تريد:"
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ تعديل السعر",
                        callback_data=f"editprice_{prod_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔄 استخدام السعر التلقائي",
                        callback_data=f"autoprice_{prod_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 رجوع",
                        callback_data="prices_back"
                    )
                ]
            ]

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
                parse_mode="Markdown"
            )

    except Exception:

        logger.exception(
            "Error resetting price"
        )


# ============================================================
# PRICE PANEL CALLBACKS
# ============================================================


async def prices_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products",
            headers=HEADERS,
            timeout=12
        )

        if res.status_code != 200:

            await query.edit_message_text(
                "❌ تعذر جلب المنتجات."
            )

            return

        data = res.json()

        products = (
            data
            if isinstance(data, list)
            else data.get("products", [])
        )

        keyboard = []

        for prod in products:

            prod_id = str(
                prod.get("id")
            )

            name = prod.get(
                "name",
                "Product"
            )

            price_usd = float(
                prod.get(
                    "price",
                    0
                )
            )

            automatic_price = calculate_price(
                price_usd
            )

            if prod_id in manual_prices:

                current_price = manual_prices[
                    prod_id
                ]

                mode = "✏️ يدوي"

            else:

                current_price = automatic_price

                mode = "🔄 تلقائي"

            short_name = (
                name[:25] + "..."
                if len(name) > 25
                else name
            )

            keyboard.append([
                InlineKeyboardButton(
                    (
                        f"📦 {short_name}\n"
                        f"💰 {current_price} ج.م "
                        f"| {mode}"
                    ),
                    callback_data=f"price_{prod_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "❌ إغلاق",
                callback_data="price_close"
            )
        ])

        await query.edit_message_text(
            "⚙️ *إدارة أسعار المنتجات*\n\n"
            "اضغط على المنتج لتعديل سعره أو إعادته للسعر التلقائي:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode="Markdown"
        )

    except Exception:

        logger.exception(
            "Error returning to prices"
        )


async def price_close(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.edit_message_text(
        "✅ تم إغلاق إدارة الأسعار."
    )


# ============================================================
# BACK TO START
# ============================================================


async def back_to_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await start(
        update,
        context
    )


# ============================================================
# MAIN
# ============================================================


def main():

    if not TELEGRAM_TOKEN or not BITE_STORE_API_KEY:

        logger.error(
            "TELEGRAM_TOKEN or BITE_STORE_API_KEY is missing!"
        )

        return

    application = (
        Application
        .builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # ========================================================
    # COMMANDS
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "prices",
            prices_command
        )
    )

    # ========================================================
    # PRODUCT CALLBACKS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            view_product,
            pattern=r"^view_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            buy_product,
            pattern=r"^buy_"
        )
    )

    # ========================================================
    # PRICE CALLBACKS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            price_product,
            pattern=r"^price_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            edit_price,
            pattern=r"^editprice_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            reset_auto_price,
            pattern=r"^autoprice_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            prices_back,
            pattern=r"^prices_back$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            price_close,
            pattern=r"^price_close$"
        )
    )

    # ========================================================
    # ORDERS / SUPPORT
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            ask_for_receipt,
            pattern=r"^send_receipt$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            request_support,
            pattern=r"^contact_support$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            start_admin_reply,
            pattern=r"^reply_to_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            approve_order,
            pattern=r"^approve_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            reject_order,
            pattern=r"^reject_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            back_to_start,
            pattern=r"^back$"
        )
    )

    # ========================================================
    # MESSAGES
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_receipt
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_user_text
        )
    )

    logger.info(
        "Starting bot with automatic + manual product pricing..."
    )

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
