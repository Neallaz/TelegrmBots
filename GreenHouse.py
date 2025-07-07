import csv
import re
import os
import pytz
import jdatetime
from datetime import datetime, timedelta
from collections import defaultdict

import asyncio
import nest_asyncio


from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === CONFIG ===
TOKEN = "7505911361:AAHwFC8EaU4feKZnYAVH_JCurArYSaXvsiM"
CSV_FILE = os.path.join(".", "expenses.csv")
INCOME_CATEGORIES = {
    "فروش": ["خیار", "گوجه", "هندوانه"],
    "واریزی": ["سهم", "تسهیلات", "بانک"]
}
OUTCOME_CATEGORIES = {
    "شارژ": ["برق", "گاز", "تلفن"],
    "قبض": ["آب", "اینترنت", "حقوق پرداختی"]
}

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("➕ افزودن هزینه/درآمد"), KeyboardButton("📊 گزارش مالی")],
        [KeyboardButton("🛑 توقف")]
    ],
    resize_keyboard=True
)


# === CSV HELPERS ===
def save_expense(user_id, amount, main_category, sub_category, description="", dt=None, direction="other"):
    if dt is None:
        dt = datetime.now(pytz.timezone("Asia/Amman"))
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow([
            dt.strftime("%Y-%m-%d %H:%M"),
            user_id,
            amount,
            main_category,
            sub_category,
            description,
            direction
        ])

def load_expenses_filtered(period="all"):
    now = datetime.now(pytz.timezone("Asia/Amman"))
    today = now.date()
    category_totals = defaultdict(float)
    income_total = 0.0
    outcome_total = 0.0

    def date_in_period(date):
        if period == "daily":
            return date.date() == today
        elif period == "monthly":
            return date.year == today.year and date.month == today.month
        elif period == "yearly":
            return date.year == today.year
        return True  # all

    try:
        with open(CSV_FILE, mode='r', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) == 7:
                    date_str, _, amount, main_cat, sub_cat, _, direction = row
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                    except ValueError:
                        continue
                    if not date_in_period(dt):
                        continue
                    amount = float(amount)
                    key = f"{main_cat} > {sub_cat}"
                    category_totals[key] += amount
                    if direction == "income":
                        income_total += amount
                    elif direction == "outcome":
                        outcome_total += amount
    except FileNotFoundError:
        pass

    return category_totals, income_total, outcome_total, now

# === PARSER ===
def parse_message_for_amount(text):
    text = text.replace("ي", "ی").replace("ك", "ک")
    income_patterns = [
        r"واریز(?: پایا)?\s*:?[\s ]*([\d,]+)",
    ]
    outcome_patterns = [
        r"(?:برداشت مبلغ|برداشت پایا|برداشت)\s*:?[\s ]*([\d,]+)",
        r"خرید\s*:?[\s ]*([\d,]+)",
        r"کارمزد(?: پایا)?\s*:?[\s ]*([\d,]+)"
    ]
    amount = None
    direction = "other"
    for pattern in income_patterns:
        match = re.search(pattern, text)
        if match:
            amount = float(match.group(1).replace(",", ""))
            direction = "income"
            break
    if amount is None:
        for pattern in outcome_patterns:
            match = re.search(pattern, text)
            if match:
                amount = float(match.group(1).replace(",", ""))
                direction = "outcome"
                break
    time_match = re.search(r"(\d{1,2}:\d{2})", text)
    time_str = time_match.group(1) if time_match else None
    return amount, time_str, direction

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 سلام! خوش آمدید.\nلطفاً یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=main_keyboard
    )
# === REPORTS ===
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 گزارش روزانه", callback_data="report_daily")],
        [InlineKeyboardButton("🗓️ گزارش ماهانه", callback_data="report_monthly")],
        [InlineKeyboardButton("📆 گزارش سالانه", callback_data="report_yearly")],
        [InlineKeyboardButton("📂 همه موارد", callback_data="report_all")],
    ])
    await update.message.reply_text("📊 لطفاً نوع گزارش را انتخاب کنید:", reply_markup=keyboard)

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    period = query.data.replace("report_", "")
    category_totals, income_total, outcome_total, now = load_expenses_filtered(period)

    if not category_totals:
        await query.edit_message_text("📭 هیچ تراکنشی در این بازه یافت نشد.")
        return

    jalali_now = jdatetime.datetime.fromgregorian(datetime=now)
    date_display = f"📅 تاریخ: {now.strftime('%Y/%m/%d')} | {jalali_now.strftime('%Y/%m/%d')} (جلالی)\n"

    message = f"📊 *گزارش {get_period_label(period)}:*\n\n"
    message += date_display + "\n"
    for cat, total in category_totals.items():
        message += f"• {cat}: *{total:,.0f}* ریال\n"
    message += "\n"
    message += f"🟢 درآمد کل: *{income_total:,.0f}* ریال\n"
    message += f"🔴 هزینه کل: *{outcome_total:,.0f}* ریال\n"
    message += f"⚖️ مانده حساب: *{income_total - outcome_total:,.0f}* ریال"

    await query.edit_message_text(message, parse_mode="Markdown")

def get_period_label(period):
    return {
        "daily": "روزانه",
        "monthly": "ماهانه",
        "yearly": "سالانه",
        "all": "کامل"
    }.get(period, "کامل")

# === MAIN MESSAGE HANDLER ===
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    # Start flow
    if text == "➕ افزودن هزینه/درآمد":
        context.user_data.clear()
        context.user_data["step"] = "choose_direction"
        keyboard = [["🟢 درآمد"], ["🔴 هزینه"], ["⬅️ بازگشت"]]
        await update.message.reply_text("📂 لطفاً نوع تراکنش را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if text == "📊 گزارش مالی":
        await report(update, context)
        return

    if text == "🛑 توقف":
        context.user_data.clear()
        await update.message.reply_text("🛑 ربات متوقف شد. برای شروع دوباره /start را بزنید.")
        return

    if text == "⬅️ بازگشت":
        step = context.user_data.get("step")
        if step == "main_category":
            context.user_data["step"] = "choose_direction"
            keyboard = [["🟢 درآمد"], ["🔴 هزینه"], ["⬅️ بازگشت"]]
            await update.message.reply_text("📂 به مرحله قبل بازگشتید. لطفاً نوع تراکنش را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        elif step == "sub_category":
            direction = context.user_data.get("direction")
            categories = list(INCOME_CATEGORIES.keys()) if direction == "income" else list(OUTCOME_CATEGORIES.keys())
            context.user_data["step"] = "main_category"
            keyboard = [[cat] for cat in categories] + [["⬅️ بازگشت"]]
            await update.message.reply_text("📁 به مرحله قبل بازگشتید. لطفاً دسته اصلی را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        elif step == "custom_sub":
            subs = context.user_data.get("available_subs", [])
            context.user_data["step"] = "sub_category"
            keyboard = [[s] for s in subs] + [["سفارشی"], ["⬅️ بازگشت"]]
            await update.message.reply_text("🔘 به مرحله قبل بازگشتید. لطفاً زیر دسته را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        elif step == "enter_description":
            subs = context.user_data.get("available_subs", [])
            context.user_data["step"] = "sub_category"
            keyboard = [[s] for s in subs] + [["سفارشی"], ["⬅️ بازگشت"]]
            await update.message.reply_text("📝 به مرحله قبل بازگشتید. لطفاً زیر دسته را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    # Detect amount and direction automatically
    amount, time_str, direction_detected = parse_message_for_amount(text)
    if amount and "step" not in context.user_data:
        context.user_data.update({
            "amount": amount,
            "direction": direction_detected,
            "time_str": time_str,
            "step": "main_category"
        })
        categories = list(INCOME_CATEGORIES if direction_detected == "income" else OUTCOME_CATEGORIES)
        keyboard = [[cat] for cat in categories] + [["⬅️ بازگشت"]]
        await update.message.reply_text(
            f"💰 مبلغ ثبت شده: *{amount:,.0f}* ریال\n🔖 نوع تراکنش: *{'درآمد' if direction_detected == 'income' else 'هزینه'}*\n\n📁 دسته اصلی را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    if text.isdigit() and "step" not in context.user_data:
        context.user_data["amount_raw"] = int(text)
        context.user_data["step"] = "choose_direction_number"
        keyboard = [["🟢 درآمد"], ["🔴 هزینه"]]
        await update.message.reply_text("📂 آیا این درآمد است یا هزینه؟", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if context.user_data.get("step") == "choose_direction_number":
        if "درآمد" in text:
            context.user_data["direction"] = "income"
        elif "هزینه" in text:
            context.user_data["direction"] = "outcome"
        else:
            await update.message.reply_text("❌ لطفاً یکی از گزینه‌های 🟢 درآمد یا 🔴 هزینه را انتخاب کنید.")
            return
        context.user_data["step"] = "choose_currency"
        keyboard = [["💵 تومان"], ["💶 ریال"]]
        await update.message.reply_text("💱 واحد مبلغ چیست؟", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if context.user_data.get("step") == "choose_currency":
        text_lower = text.lower()
        if "تومان" in text or "toman" in text_lower:
            amount = context.user_data["amount_raw"] * 10
        elif "ریال" in text or "rial" in text_lower:
            amount = context.user_data["amount_raw"]
        else:
            await update.message.reply_text("❌ لطفاً واحد صحیح را انتخاب کنید (تومان یا ریال).")
            return
        context.user_data["amount"] = amount
        context.user_data["step"] = "main_category"
        direction = context.user_data["direction"]
        categories = list(INCOME_CATEGORIES if direction == "income" else OUTCOME_CATEGORIES)
        keyboard = [[cat] for cat in categories] + [["⬅️ بازگشت"]]
        await update.message.reply_text(
            f"💰 مبلغ ثبت شده: *{amount:,.0f}* ریال\n🔖 نوع تراکنش: *{'درآمد' if direction == 'income' else 'هزینه'}*\n\n📁 دسته اصلی را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    if context.user_data.get("step") == "choose_direction":
        if "درآمد" in text:
            context.user_data["direction"] = "income"
        elif "هزینه" in text:
            context.user_data["direction"] = "outcome"
        else:
            await update.message.reply_text("❌ لطفاً یکی از گزینه‌های 🟢 درآمد یا 🔴 هزینه را انتخاب کنید.")
            return
        context.user_data["step"] = "amount_input"
        await update.message.reply_text("💰 لطفاً مبلغ را به ریال وارد کنید:")
        return

    if context.user_data.get("step") == "amount_input":
        if text.isdigit():
            context.user_data["amount"] = float(text)
            context.user_data["step"] = "main_category"
            direction = context.user_data["direction"]
            categories = list(INCOME_CATEGORIES if direction == "income" else OUTCOME_CATEGORIES)
            keyboard = [[cat] for cat in categories] + [["⬅️ بازگشت"]]
            await update.message.reply_text("📁 لطفاً دسته اصلی را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        else:
            await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")
        return

    if context.user_data.get("step") == "main_category":
        direction = context.user_data.get("direction")
        categories = INCOME_CATEGORIES if direction == "income" else OUTCOME_CATEGORIES
        if text == "⬅️ بازگشت":
            context.user_data["step"] = "choose_direction"
            keyboard = [["🟢 درآمد"], ["🔴 هزینه"], ["⬅️ بازگشت"]]
            await update.message.reply_text("📂 به مرحله قبل بازگشتید. لطفاً نوع تراکنش را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return
        if text not in categories:
            await update.message.reply_text("❌ لطفاً یک دسته‌بندی معتبر انتخاب کنید.")
            return
        context.user_data["main_category"] = text
        context.user_data["step"] = "sub_category"
        subs = categories[text]
        context.user_data["available_subs"] = subs
        keyboard = [[s] for s in subs] + [["سفارشی"], ["⬅️ بازگشت"]]
        await update.message.reply_text("🔘 لطفاً زیر دسته را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if context.user_data.get("step") == "sub_category":
        subs = context.user_data.get("available_subs", [])
        if text == "⬅️ بازگشت":
            direction = context.user_data.get("direction")
            categories = list(INCOME_CATEGORIES.keys()) if direction == "income" else list(OUTCOME_CATEGORIES.keys())
            context.user_data["step"] = "main_category"
            keyboard = [[cat] for cat in categories] + [["⬅️ بازگشت"]]
            await update.message.reply_text("📁 به مرحله قبل بازگشتید. لطفاً دسته اصلی را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return
        if text == "سفارشی":
            context.user_data["step"] = "custom_sub"
            await update.message.reply_text("✍️ لطفاً نام زیر دسته سفارشی را وارد کنید:")
            return
        if text not in subs:
            await update.message.reply_text("❌ لطفاً یک زیر دسته‌بندی معتبر انتخاب کنید یا سفارشی را انتخاب کنید.")
            return
        context.user_data["sub_category"] = text
        context.user_data["step"] = "enter_description"
        await update.message.reply_text("📝 لطفاً توضیحی برای این تراکنش وارد کنید یا '-' را برای عدم وجود توضیح تایپ کنید:")
        return

    if context.user_data.get("step") == "custom_sub":
        if text == "⬅️ بازگشت":
            subs = context.user_data.get("available_subs", [])
            context.user_data["step"] = "sub_category"
            keyboard = [[s] for s in subs] + [["سفارشی"], ["⬅️ بازگشت"]]
            await update.message.reply_text("🔘 به مرحله قبل بازگشتید. لطفاً زیر دسته را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return
        if not text:
            await update.message.reply_text("❌ لطفاً نام زیر دسته را وارد کنید.")
            return
        context.user_data["sub_category"] = text
        context.user_data["step"] = "enter_description"
        await update.message.reply_text("📝 لطفاً توضیحی برای این تراکنش وارد کنید یا '-' را برای عدم وجود توضیح تایپ کنید:")
        return

    if context.user_data.get("step") == "enter_description":
        description = text.strip()
        if description == "-":
            description = ""
        context.user_data["description"] = description
        context.user_data["step"] = "confirm_save"
        amount = context.user_data["amount"]
        main_cat = context.user_data["main_category"]
        sub_cat = context.user_data["sub_category"]
        await update.message.reply_text(
            f"✅ مبلغ: *{amount:,.0f}* ریال\n📂 دسته‌بندی: {main_cat} > {sub_cat}\n📝 توضیح: {description or '(ندارد)'}\n\nآیا این تراکنش ذخیره شود؟",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["✅ بله", "❌ خیر"]], resize_keyboard=True)
        )
        return

    if context.user_data.get("step") == "confirm_save":
        if text == "✅ بله":
            amount = context.user_data.get("amount")
            description = context.user_data.get("description", "")
            now = datetime.now(pytz.timezone("Asia/Amman"))
            if context.user_data.get("time_str"):
                try:
                    h, m = map(int, context.user_data["time_str"].split(":"))
                    now = now.replace(hour=h, minute=m)
                except Exception:
                    pass
            save_expense(
                user_id,
                amount,
                context.user_data["main_category"],
                context.user_data["sub_category"],
                description,
                now,
                context.user_data["direction"]
            )
            await update.message.reply_text(
                f"✅ تراکنش ذخیره شد:\n💰 مبلغ: *{amount:,.0f}* ریال\n📁 دسته‌بندی: {context.user_data['main_category']} > {context.user_data['sub_category']}\n📝 توضیح: {description or '(ندارد)'}",
                parse_mode="Markdown",
                reply_markup=main_keyboard
            )
            context.user_data.clear()
            return
        elif text == "❌ خیر":
            await update.message.reply_text("❌ تراکنش لغو شد.", reply_markup=main_keyboard)
            context.user_data.clear()
            return
        else:
            await update.message.reply_text("❓ لطفاً انتخاب کنید: ✅ بله یا ❌ خیر")
            return

    await update.message.reply_text("❓ لطفاً از گزینه‌های موجود استفاده کنید یا /start را بزنید.")

# === SETUP AND RUN ===
async def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CallbackQueryHandler(report_callback, pattern=r"^report_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 Bot is running...")
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())


# import csv
# import re
# from datetime import datetime
# from collections import defaultdict
# import pytz
# import asyncio
# import nest_asyncio
# import os

# from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
# from telegram.ext import (
#     ApplicationBuilder,
#     CommandHandler,
#     MessageHandler,
#     ContextTypes,
#     filters,
# )

# # === CONFIG ===
# TOKEN = "7505911361:AAHwFC8EaU4feKZnYAVH_JCurArYSaXvsiM"
# CSV_FILE = os.path.join(".", "expenses.csv")
# INCOME_CATEGORIES = {
#     "فروش": ["خیار", "گوجه", "هندوانه"],
#     "واریزی": ["سهم", "کمک", "بانک"]
# }
# OUTCOME_CATEGORIES = {
#     "شارژ": ["برق", "گاز", "تلفن"],
#     "قبض": ["آب", "اینترنت", "حقوق پرداختی"]
# }

# main_keyboard = ReplyKeyboardMarkup(
#     keyboard=[
#         [KeyboardButton("➕ Add Expense"), KeyboardButton("📊 Report")],
#         [KeyboardButton("🛑 Stop")]
#     ],
#     resize_keyboard=True
# )

# # === CSV HELPERS ===
# def save_expense(user_id, amount, main_category, sub_category, description="", dt=None, direction="other"):
#     if dt is None:
#         dt = datetime.now(pytz.timezone("Asia/Amman"))
#     with open(CSV_FILE, mode='a', newline='', encoding='utf-8-sig') as file:
#         writer = csv.writer(file)
#         writer.writerow([
#             dt.strftime("%Y-%m-%d %H:%M"),
#             user_id,
#             amount,
#             main_category,
#             sub_category,
#             description,
#             direction
#         ])

# def load_expenses():
#     category_totals = defaultdict(float)
#     income_total = 0.0
#     outcome_total = 0.0
#     try:
#         with open(CSV_FILE, mode='r', encoding='utf-8') as file:
#             reader = csv.reader(file)
#             for row in reader:
#                 if len(row) == 7:
#                     _, _, amount, main_cat, sub_cat, description, direction = row
#                     amount = float(amount)
#                     key = f"{main_cat} > {sub_cat}"
#                     category_totals[key] += amount
#                     if direction == "income":
#                         income_total += amount
#                     elif direction == "outcome":
#                         outcome_total += amount
#     except FileNotFoundError:
#         pass
#     return category_totals, income_total, outcome_total

# # === PARSER ===
# def parse_message_for_amount(text):
#     text = text.replace("ي", "ی").replace("ك", "ک")
#     income_patterns = [
#         r"واریز(?: پایا)?\s*:?[\s ]*([\d,]+)",
#     ]
#     outcome_patterns = [
#         r"(?:برداشت مبلغ|برداشت پایا|برداشت)\s*:?[\s ]*([\d,]+)",
#         r"خرید\s*:?[\s ]*([\d,]+)",
#         r"کارمزد(?: پایا)?\s*:?[\s ]*([\d,]+)"
#     ]
#     amount = None
#     direction = "other"
#     for pattern in income_patterns:
#         match = re.search(pattern, text)
#         if match:
#             amount = float(match.group(1).replace(",", ""))
#             direction = "income"
#             break
#     if amount is None:
#         for pattern in outcome_patterns:
#             match = re.search(pattern, text)
#             if match:
#                 amount = float(match.group(1).replace(",", ""))
#                 direction = "outcome"
#                 break
#     time_match = re.search(r"(\d{1,2}:\d{2})", text)
#     time_str = time_match.group(1) if time_match else None
#     return amount, time_str, direction

# # === COMMANDS ===
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     context.user_data.clear()
#     await update.message.reply_text("👋 Welcome! Choose an action:", reply_markup=main_keyboard)

# async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     category_totals, income_total, outcome_total = load_expenses()
#     if not category_totals:
#         await update.message.reply_text("📭 No records yet.")
#         return
#     message = "📊 *Expense Report:*\n\n"
#     for cat, total in category_totals.items():
#         message += f"• {cat}: {total:,.0f} Rial\n"
#     message += "\n"
#     message += f"🟢 *Total Income:* {income_total:,.0f} Rial\n"
#     message += f"🔴 *Total Outcome:* {outcome_total:,.0f} Rial\n"
#     message += f"⚖️ *Net:* {income_total - outcome_total:,.0f} Rial"
#     await update.message.reply_text(message, parse_mode='Markdown')

# # === MAIN MESSAGE HANDLER ===
# async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = update.message.from_user.id
#     text = update.message.text.strip()

#     # Step: START
#     if text == "➕ Add Expense":
#         context.user_data.clear()
#         context.user_data["step"] = "choose_direction"
#         keyboard = [["🟢 درآمد (Income)"], ["🔴 هزینه (Outcome)"], ["⬅️ Back"]]
#         await update.message.reply_text("📂 Please choose type:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         return

#     if text == "📊 Report":
#         await report(update, context)
#         return

#     if text == "🛑 Stop":
#         context.user_data.clear()
#         await update.message.reply_text("🛑 Bot stopped. Send /start to begin again.")
#         return

#     # Step: BACK
#     if text == "⬅️ Back":
#         step = context.user_data.get("step")
#         if step == "main_category":
#             context.user_data["step"] = "choose_direction"
#             keyboard = [["🟢 درآمد (Income)"], ["🔴 هزینه (Outcome)"], ["⬅️ Back"]]
#             await update.message.reply_text("📂 Back to type selection:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         elif step == "sub_category":
#             direction = context.user_data.get("direction")
#             categories = list(INCOME_CATEGORIES.keys()) if direction == "income" else list(OUTCOME_CATEGORIES.keys())
#             context.user_data["step"] = "main_category"
#             keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
#             await update.message.reply_text("📁 Back to main category:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         elif step == "custom_sub":
#             subs = context.user_data.get("available_subs", [])
#             context.user_data["step"] = "sub_category"
#             keyboard = [[s] for s in subs] + [["Custom"], ["⬅️ Back"]]
#             await update.message.reply_text("🔘 Choose subcategory again:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         elif step == "enter_description":
#             subs = context.user_data.get("available_subs", [])
#             context.user_data["step"] = "sub_category"
#             keyboard = [[s] for s in subs] + [["Custom"], ["⬅️ Back"]]
#             await update.message.reply_text("🔘 Back to subcategory selection:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         return

#     # Step: RAW AMOUNT OR SMS
#     amount, time_str, direction_detected = parse_message_for_amount(text)
#     if amount and "step" not in context.user_data:
#         if amount is None:
#             await update.message.reply_text("❌ Please enter a valid amount.")
#             return
#         context.user_data.update({
#             "amount": amount,
#             "direction": direction_detected,
#             "time_str": time_str,
#             "step": "main_category"
#         })
#         categories = list(INCOME_CATEGORIES if direction_detected == "income" else OUTCOME_CATEGORIES)
#         keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
#         await update.message.reply_text(
#             f"✅ Amount: {amount:,.0f} Rial\nDirection: {direction_detected.upper()}\nChoose main category:",
#             reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
#         )
#         return

#     if text.isdigit() and "step" not in context.user_data:
#         context.user_data["amount_raw"] = int(text)
#         context.user_data["step"] = "choose_direction_number"
#         keyboard = [["🟢 درآمد (Income)"], ["🔴 هزینه (Outcome)"]]
#         await update.message.reply_text("📂 Is this income or outcome?", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         return

#     if context.user_data.get("step") == "choose_direction_number":
#         if "درآمد" in text:
#             context.user_data["direction"] = "income"
#         elif "هزینه" in text:
#             context.user_data["direction"] = "outcome"
#         else:
#             await update.message.reply_text("❌ Invalid type. Choose درآمد or هزینه.")
#             return
#         context.user_data["step"] = "choose_currency"
#         await update.message.reply_text("💱 Is the amount in Toman or Rial?", reply_markup=ReplyKeyboardMarkup([["💵 Toman"], ["💶 Rial"]], resize_keyboard=True))
#         return

#     if context.user_data.get("step") == "choose_currency":
#         text_lower = text.lower()

#         if "تومان" in text or "toman" in text_lower:
#             amount = context.user_data["amount_raw"] * 10
#         elif "ریال" in text or "rial" in text_lower:
#             amount = context.user_data["amount_raw"]
#         else:
#             await update.message.reply_text("❌ Invalid currency. Please choose 'Toman' or 'Rial'.")
#             return
#         context.user_data["amount"] = amount
#         context.user_data["step"] = "main_category"
#         direction = context.user_data["direction"]
#         categories = list(INCOME_CATEGORIES if direction == "income" else OUTCOME_CATEGORIES)
#         keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
#         await update.message.reply_text(
#             f"✅ Amount: {amount:,.0f} Rial\nDirection: {direction.upper()}\nChoose main category:",
#             reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
#         )
#         return

#     if context.user_data.get("step") == "choose_direction":
#         if "درآمد" in text:
#             context.user_data["direction"] = "income"
#         elif "هزینه" in text:
#             context.user_data["direction"] = "outcome"
#         else:
#             await update.message.reply_text("❌ Invalid type. Choose 🟢 درآمد or 🔴 هزینه.")
#             return
#         context.user_data["step"] = "amount_input"
#         await update.message.reply_text("💰 Please enter the amount in Rial:")
#         return

#     if context.user_data.get("step") == "amount_input":
#         if text.isdigit():
#             context.user_data["amount"] = float(text)
#             context.user_data["step"] = "main_category"
#             direction = context.user_data["direction"]
#             categories = list(INCOME_CATEGORIES if direction == "income" else OUTCOME_CATEGORIES)
#             keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
#             await update.message.reply_text("📁 Choose main category:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         else:
#             await update.message.reply_text("❌ Please enter a valid number for amount.")
#         return

#     if context.user_data.get("step") == "main_category":
#         direction = context.user_data.get("direction")
#         categories = INCOME_CATEGORIES if direction == "income" else OUTCOME_CATEGORIES
#         if text == "⬅️ Back":
#             context.user_data["step"] = "choose_direction"
#             keyboard = [["🟢 درآمد (Income)"], ["🔴 هزینه (Outcome)"], ["⬅️ Back"]]
#             await update.message.reply_text("📂 Back to type selection:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#             return
#         if text not in categories:
#             await update.message.reply_text("❌ Please select a valid main category.")
#             return
#         context.user_data["main_category"] = text
#         context.user_data["step"] = "sub_category"
#         subs = categories[text]
#         context.user_data["available_subs"] = subs
#         keyboard = [[s] for s in subs] + [["Custom"], ["⬅️ Back"]]
#         await update.message.reply_text("🔘 Choose subcategory:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#         return

#     if context.user_data.get("step") == "sub_category":
#         subs = context.user_data.get("available_subs", [])
#         if text == "⬅️ Back":
#             direction = context.user_data.get("direction")
#             categories = list(INCOME_CATEGORIES.keys()) if direction == "income" else list(OUTCOME_CATEGORIES.keys())
#             context.user_data["step"] = "main_category"
#             keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
#             await update.message.reply_text("📁 Back to main category:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#             return
#         if text == "Custom":
#             context.user_data["step"] = "custom_sub"
#             await update.message.reply_text("✍️ Please type custom subcategory name:")
#             return
#         if text not in subs:
#             await update.message.reply_text("❌ Please select a valid subcategory or Custom.")
#             return
#         # Save subcategory and ask for description
#         context.user_data["sub_category"] = text
#         context.user_data["step"] = "enter_description"
#         await update.message.reply_text("📝 Please enter a description for this entry (or type '-' for no description):")
#         return

#     if context.user_data.get("step") == "custom_sub":
#         if text == "⬅️ Back":
#             subs = context.user_data.get("available_subs", [])
#             context.user_data["step"] = "sub_category"
#             keyboard = [[s] for s in subs] + [["Custom"], ["⬅️ Back"]]
#             await update.message.reply_text("🔘 Back to subcategory selection:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
#             return
#         if not text:
#             await update.message.reply_text("❌ Please enter a valid subcategory name.")
#             return
#         context.user_data["sub_category"] = text
#         context.user_data["step"] = "enter_description"
#         await update.message.reply_text("📝 Please enter a description for this entry (or type '-' for no description):")
#         return

#     if context.user_data.get("step") == "enter_description":
#         description = text.strip()
#         if description == "-":
#             description = ""
#         context.user_data["description"] = description
#         context.user_data["step"] = "confirm_save"
#         amount = context.user_data["amount"]
#         main_cat = context.user_data["main_category"]
#         sub_cat = context.user_data["sub_category"]
#         await update.message.reply_text(
#             f"✅ Amount: {amount:,.0f} Rial\nCategory: {main_cat} > {sub_cat}\nDescription: {description or '(none)'}\n\nSave this entry?\n✅ Yes / ❌ No",
#             reply_markup=ReplyKeyboardMarkup([["✅ Yes", "❌ No"]], resize_keyboard=True)
#         )
#         return

#     if context.user_data.get("step") == "confirm_save":
#         if text == "✅ Yes":
#             amount = context.user_data.get("amount")
#             description = context.user_data.get("description", "")
#             now = datetime.now(pytz.timezone("Asia/Amman"))
#             if context.user_data.get("time_str"):
#                 try:
#                     h, m = map(int, context.user_data["time_str"].split(":"))
#                     now = now.replace(hour=h, minute=m)
#                 except Exception:
#                     pass
#             save_expense(
#                 user_id,
#                 amount,
#                 context.user_data["main_category"],
#                 context.user_data["sub_category"],
#                 description,
#                 now,
#                 context.user_data["direction"]
#             )
#             await update.message.reply_text(
#                 f"✅ Saved: {amount:,.0f} Rial\n📁 {context.user_data['main_category']} > {context.user_data['sub_category']}\n📝 Description: {description or '(none)'}",
#                 reply_markup=main_keyboard
#             )
#             context.user_data.clear()
#             return
#         elif text == "❌ No":
#             await update.message.reply_text("❌ Entry cancelled.", reply_markup=main_keyboard)
#             context.user_data.clear()
#             return
#         else:
#             await update.message.reply_text("❓ Please confirm: ✅ Yes or ❌ No")
#             return

#     # Catch-all fallback
#     await update.message.reply_text("❓ Please choose a valid option or use /start")

# # === SETUP AND RUN ===
# async def main():
#     application = ApplicationBuilder().token(TOKEN).build()
#     application.add_handler(CommandHandler("start", start))
#     application.add_handler(CommandHandler("report", report))
#     print("🤖 Bot is running...")
#     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
#     await application.run_polling()

# if __name__ == "__main__":
#     nest_asyncio.apply()
#     asyncio.run(main())
