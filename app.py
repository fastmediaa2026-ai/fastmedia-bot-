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
# MANUAL PRICES STORAGE
# ============================================================

MANUAL_PRICES_FILE = "manual_prices.json"


def load_manual_prices():
    try:
        if not os.path.exists(MANUAL_PRICES_FILE):
            return {}

        with open(
            MANUAL_PRICES_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

            if isinstance(data, dict):
                return data

    except Exception:
        logger.exception("Failed to load manual prices")

    return {}


def save_manual_prices():
    try:

        with open(
            MANUAL_PRICES_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                manual_prices,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception:
        logger.exception("Failed to save manual prices")


manual_prices = load_manual_prices()


# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "X-API-Key": BITE_STORE_API_KEY,
    "Content-Type": "application/json"
}


# ============================================================
# PAYMENT
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

def calculate_automatic_price(price_usd):
    """
    السعر التلقائي:
    USD × PROFIT_MARGIN × USD_TO_EGP
    """

    return round(
        float(price_usd)
        * PROFIT_MARGIN
        * USD_TO_EGP
    )


def get_product_price(prod_id, price_usd):
    """
    إذا كان هناك سعر يدوي يستخدمه.
    غير ذلك يستخدم المعادلة التلقائية.
    """

    prod_id = str(prod_id)

    if prod_id in manual_prices:

        return int(
            manual_prices[prod_id]
        )

    return calculate_automatic_price(
        price_usd
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

        if res.status_code != 200:

            await status_msg.edit_text(
                "❌ تعذر الاتصال بالمتجر، يرجى المحاولة لاحقاً."
            )

            return

        data = res.json()

        products = (
            data
            if isinstance(data, list)
            else data.get("products", [])
        )

        keyboard = []

        products_cache.clear()

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

            stock = prod.get(
                "stock",
                0
            )

            price_egp = get_product_price(
                prod_id,
                price_usd
            )

            if stock > 0:

                products_cache[prod_id] = {
                    "name": name,
                    "price_egp": price_egp,
                    "price_usd": price_usd,
                    "stock": stock
                }

                short_name = (
                    name[:28] + "..."
                    if len(name) > 28
                    else name
                )

                keyboard.append([
                    InlineKeyboardButton(
                        f"✨ {short_name} | {price_egp} ج.م",
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

            await status_msg.edit_text(
                "🛍️ *أهلاً بك في متجر Fastmedia Store*\n\n"
                "اختر المنتج المطلوب لعرض التفاصيل والمواصفات 👇",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
                parse_mode="Markdown"
            )

        else:

            await status_msg.edit_text(
                "⚠️ لا توجد منتجات متوفرة حالياً."
            )

    except Exception:

        logger.exception(
            "Error in /start"
        )

        await status_msg.edit_text(
            "❌ حدث خطأ أثناء الاتصال بالخادم."
        )


# ============================================================
# VIEW PRODUCT
# ============================================================

async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        prod_id = int(query.data.split(":")[-1])
        # جلب المنتج من الكاش بدل طلب /v1/products/{id}
        product = next(
            (p for p in products_cache if int(p.get("id", -1)) == prod_id), None
        )
        if not product:
            await query.message.reply_text(
                "❌ تعذر العثور على المنتج."
            )
            return
        name = product.get("name", "بدون اسم")
        description = product.get("description", "")
        price = product.get("price", 0)
        text = (
            f"📦 <b>{name}</b>\n\n"
            f"{description}\n\n"
            f"💰 السعر: {price}"
        )
        await query.message.reply_text(
            text, parse_mode="HTML"
        )
    except Exception as e:
        logger.exception("Error viewing product")
        await query.message.reply_text(
            "❌ حدث خطأ أثناء جلب المنتج."
        )


# ============================================================
# BUY PRODUCT
# ============================================================

async def buy_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    prod_id = query.data.split(
        "_",
        1
    )[1]

    prod = products_cache.get(
        prod_id
    )

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
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode="Markdown"
    )


# ============================================================
# ASK FOR RECEIPT
# ============================================================

async def ask_for_receipt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

    context.user_data[
        "waiting_receipt"
    ] = True


# ============================================================
# SUPPORT
# ============================================================

async def request_support(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    context.user_data[
        "waiting_support_msg"
    ] = True

    await query.edit_message_text(
        "✍️ *أهلاً بك في الدعم الفني!*\n\n"
        "اكتب رسالتك أو استفسارك هنا في الشات، "
        "وسيتم إرسالها للإدارة للرد عليك مباشرة.",
        parse_mode="Markdown"
    )


# ============================================================
# ADMIN REPLY / USER TEXT
# ============================================================

async def handle_user_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    text = update.message.text

    # --------------------------------------------------------
    # ADMIN REPLY
    # --------------------------------------------------------

    if (
        user_id == ADMIN_ID
        and context.user_data.get(
            "replying_to_user"
        )
    ):

        target_client_id = context.user_data.pop(
            "replying_to_user"
        )

        try:

            await context.bot.send_message(
                chat_id=target_client_id,
                text=(
                    "💬 *رد الدعم الفني:*\n\n"
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

    # --------------------------------------------------------
    # ADMIN MANUAL PRICE
    # --------------------------------------------------------

    if (
        user_id == ADMIN_ID
        and context.user_data.get(
            "editing_price"
        )
    ):

        prod_id = context.user_data.pop(
            "editing_price"
        )

        try:

            new_price_text = text.strip().replace(
                ",",
                "."
            )

            new_price = float(
                new_price_text
            )

            if new_price <= 0:

                context.user_data[
                    "editing_price"
                ] = prod_id

                await update.message.reply_text(
                    "❌ السعر يجب أن يكون أكبر من صفر.\n\n"
                    "أرسل السعر مرة أخرى، مثال:\n"
                    "`250`",
                    parse_mode="Markdown"
                )

                return

            new_price = int(
                round(new_price)
            )

            manual_prices[
                str(prod_id)
            ] = new_price

            save_manual_prices()

            if prod_id in products_cache:

                products_cache[
                    prod_id
                ]["price_egp"] = new_price

            await update.message.reply_text(
                "✅ *تم تعديل السعر بنجاح*\n\n"
                f"🆔 Product ID: `{prod_id}`\n"
                f"💰 السعر الجديد: *{new_price} جنيه*\n\n"
                "📌 هذا المنتج أصبح يستخدم السعر اليدوي.\n"
                "باقي المنتجات ستظل على السعر التلقائي.",
                parse_mode="Markdown"
            )

        except ValueError:

            context.user_data[
                "editing_price"
            ] = prod_id

            await update.message.reply_text(
                "❌ السعر غير صحيح.\n\n"
                "أرسل رقم السعر فقط، مثال:\n"
                "`250`",
                parse_mode="Markdown"
            )

        return

    # --------------------------------------------------------
    # SUPPORT MESSAGE
    # --------------------------------------------------------

    if context.user_data.get(
        "waiting_support_msg"
    ):

        context.user_data[
            "waiting_support_msg"
        ] = False

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

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer()

    client_id = int(
        query.data.split("_")[2]
    )

    context.user_data[
        "replying_to_user"
    ] = client_id

    await query.message.reply_text(
        f"✍️ اكتب الآن نص الرد الذي تريد إرساله "
        f"للعميل `{client_id}`:",
        parse_mode="Markdown"
    )


# ============================================================
# RECEIPT
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
            "⚠️ انتهت صلاحية الطلب، ابدأ من جديد بـ /start"
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
        f"👤 العميل: @{order['username']} (`{user_id}`)\n"
        f"📦 المنتج: {order['product_name']}\n"
        f"💵 المبلغ: *{order['price_egp']} جنيه*\n"
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
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
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

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer()

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
                    "🎉 *تم تأكيد الدفع بنجاح!*\n\n"
                    f"📦 المنتج: {order['product_name']}\n\n"
                    "📋 *البيانات/الكود الخاص بك:*\n"
                    f"`{delivered_key}`\n\n"
                    "شكراً لتعاملك معنا ❤️"
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

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer()

    user_id = int(
        query.data.split("_")[1]
    )

    pending_orders.pop(
        user_id,
        None
    )

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

    await send_price_panel(
        update.message
    )


async def send_price_panel(
    message
):

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products",
            headers=HEADERS,
            timeout=12
        )

        if res.status_code != 200:

            await message.reply_text(
                "❌ تعذر جلب المنتجات من المتجر."
            )

            return

        data = res.json()

        products = (
            data
            if isinstance(data, list)
            else data.get("products", [])
        )

        if not products:

            await message.reply_text(
                "⚠️ لا توجد منتجات."
            )

            return

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

            automatic_price = calculate_automatic_price(
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
                name[:24] + "..."
                if len(name) > 24
                else name
            )

            keyboard.append([
                InlineKeyboardButton(
                    (
                        f"📦 {short_name} | "
                        f"{current_price} ج.م {mode}"
                    ),
                    callback_data=f"manageprice_{prod_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "❌ إغلاق",
                callback_data="price_close"
            )
        ])

        await message.reply_text(
            "⚙️ *إدارة أسعار المنتجات*\n\n"
            f"💱 المعادلة الحالية:\n"
            f"`USD × {PROFIT_MARGIN} × {USD_TO_EGP}`\n\n"
            "🔄 تلقائي = السعر محسوب بالمعادلة\n"
            "✏️ يدوي = أنت حددت سعرًا خاصًا لهذا المنتج\n\n"
            "اضغط على المنتج الذي تريد تعديل سعره:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode="Markdown"
        )

    except Exception:

        logger.exception(
            "Error in send_price_panel"
        )

        await message.reply_text(
            "❌ حدث خطأ أثناء جلب قائمة الأسعار."
        )


# ============================================================
# OPEN PRICE PRODUCT
# ============================================================

async def manage_price_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer()

    prod_id = query.data.replace(
        "manageprice_",
        "",
        1
    )

    logger.info(
        "Admin opened price manager | product_id=%s",
        prod_id
    )

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products/{prod_id}",
            headers=HEADERS,
            timeout=10
        )

        if res.status_code != 200:

            await query.message.reply_text(
                f"❌ تعذر جلب المنتج.\n"
                f"HTTP {res.status_code}"
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

        automatic_price = calculate_automatic_price(
            price_usd
        )

        if prod_id in manual_prices:

            current_price = manual_prices[
                prod_id
            ]

            mode = "✏️ سعر يدوي"

        else:

            current_price = automatic_price

            mode = "🔄 سعر تلقائي"

        text = (
            "⚙️ *إدارة سعر المنتج*\n\n"
            f"📦 *المنتج:* {name}\n"
            f"🆔 Product ID: `{prod_id}`\n\n"
            f"💵 سعر API: `${price_usd}`\n"
            f"🔄 السعر بالمعادلة: "
            f"*{automatic_price} جنيه*\n"
            f"💰 السعر الحالي: "
            f"*{current_price} جنيه*\n"
            f"📌 الوضع: *{mode}*\n\n"
            "اختر الإجراء:"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "✏️ تعديل السعر",
                    callback_data=f"editmanual_{prod_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 استخدام السعر التلقائي",
                    callback_data=f"resetmanual_{prod_id}"
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
            "Error in manage_price_product"
        )

        await query.message.reply_text(
            "❌ حدث خطأ أثناء فتح إعدادات السعر."
        )


# ============================================================
# EDIT MANUAL PRICE
# ============================================================

async def edit_manual_price(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer()

    prod_id = query.data.replace(
        "editmanual_",
        "",
        1
    )

    context.user_data[
        "editing_price"
    ] = prod_id

    await query.message.reply_text(
        "✏️ *تعديل سعر المنتج*\n\n"
        f"🆔 Product ID: `{prod_id}`\n\n"
        "أرسل الآن السعر الجديد بالجنيه المصري.\n\n"
        "مثال:\n"
        "`250`",
        parse_mode="Markdown"
    )


# ============================================================
# RESET MANUAL PRICE
# ============================================================

async def reset_manual_price(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer(
        "✅ تم إرجاع السعر التلقائي"
    )

    prod_id = query.data.replace(
        "resetmanual_",
        "",
        1
    )

    manual_prices.pop(
        prod_id,
        None
    )

    save_manual_prices()

    try:

        res = requests.get(
            f"{BASE_URL}/v1/products/{prod_id}",
            headers=HEADERS,
            timeout=10
        )

        if res.status_code != 200:

            await query.edit_message_text(
                "✅ تم إلغاء السعر اليدوي.\n"
                "🔄 المنتج الآن يستخدم السعر التلقائي."
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

        automatic_price = calculate_automatic_price(
            price_usd
        )

        text = (
            "⚙️ *إدارة سعر المنتج*\n\n"
            f"📦 *المنتج:* {name}\n"
            f"🆔 Product ID: `{prod_id}`\n\n"
            f"💵 سعر API: `${price_usd}`\n"
            f"🔄 السعر بالمعادلة: "
            f"*{automatic_price} جنيه*\n"
            f"💰 السعر الحالي: "
            f"*{automatic_price} جنيه*\n"
            f"📌 الوضع: *🔄 سعر تلقائي*\n\n"
            "اختر الإجراء:"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "✏️ تعديل السعر",
                    callback_data=f"editmanual_{prod_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 استخدام السعر التلقائي",
                    callback_data=f"resetmanual_{prod_id}"
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
            "Error in reset_manual_price"
        )


# ============================================================
# BACK TO PRICE LIST
# ============================================================

async def prices_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer()

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

            automatic_price = calculate_automatic_price(
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
                name[:24] + "..."
                if len(name) > 24
                else name
            )

            keyboard.append([
                InlineKeyboardButton(
                    (
                        f"📦 {short_name} | "
                        f"{current_price} ج.م {mode}"
                    ),
                    callback_data=f"manageprice_{prod_id}"
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
            "اضغط على المنتج الذي تريد تعديله:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode="Markdown"
        )

    except Exception:

        logger.exception(
            "Error returning to price list"
        )

        await query.message.reply_text(
            "❌ حدث خطأ أثناء الرجوع لقائمة الأسعار."
        )


# ============================================================
# CLOSE PRICE PANEL
# ============================================================

async def price_close(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "غير مصرح لك",
            show_alert=True
        )

        return

    await query.answer()

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
    # PRICE MANAGEMENT CALLBACKS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            manage_price_product,
            pattern=r"^manageprice_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            edit_manual_price,
            pattern=r"^editmanual_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            reset_manual_price,
            pattern=r"^resetmanual_"
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
    # ORDER / SUPPORT CALLBACKS
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
    # MESSAGE HANDLERS
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
        "Starting FastMedia bot..."
    )

    logger.info(
        "Automatic pricing enabled: USD x %.2f x %.2f",
        PROFIT_MARGIN,
        USD_TO_EGP
    )

    logger.info(
        "Manual prices loaded: %d",
        len(manual_prices)
    )

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
