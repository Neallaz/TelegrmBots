import csv
import re
from datetime import datetime
from collections import defaultdict
import pytz
import asyncio
import nest_asyncio
import os

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === CONFIG ===
TOKEN = "7505911361:AAHwFC8EaU4feKZnYAVH_JCurArYSaXvsiM"
# CSV_FILE = "expenses.csv"
CSV_FILE = os.path.join(".", "expenses.csv")
INCOME_CATEGORIES = {
    "فروش": ["خیار", "گوجه", "هندوانه"],
    "واریزی": ["سهم", "کمک", "بانک"]
}
OUTCOME_CATEGORIES = {
    "شارژ": ["برق", "گاز", "تلفن"],
    "قبض": ["آب", "اینترنت", "حقوق پرداختی"]
}

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("➕ Add Expense"), KeyboardButton("📊 Report")],
        [KeyboardButton("🛑 Stop")]
    ],
    resize_keyboard=True
)

# === CSV HELPERS ===
def save_expense(user_id, amount, main_category, sub_category, dt=None, direction="other"):
    if dt is None:
        dt = datetime.now(pytz.timezone("Asia/Amman"))
    # with open(CSV_FILE, mode='a', newline='') as file:
    print(type(main_category), main_category)
    print(type(sub_category), sub_category)
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([
            dt.strftime("%Y-%m-%d %H:%M"),
            user_id,
            amount,
            main_category,
            sub_category,
            direction
        ])

def load_expenses():
    category_totals = defaultdict(float)
    income_total = 0.0
    outcome_total = 0.0
    try:
        # with open(CSV_FILE, mode='r') as file:
        with open(CSV_FILE, mode='r', encoding='utf-8') as file:

            reader = csv.reader(file)
            for row in reader:
                if len(row) == 6:
                    _, _, amount, main_cat, sub_cat, direction = row
                    amount = float(amount)
                    key = f"{main_cat} > {sub_cat}"
                    category_totals[key] += amount
                    if direction == "income":
                        income_total += amount
                    elif direction == "outcome":
                        outcome_total += amount
    except FileNotFoundError:
        pass
    return category_totals, income_total, outcome_total

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
    await update.message.reply_text("👋 Welcome! Choose an action:", reply_markup=main_keyboard)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category_totals, income_total, outcome_total = load_expenses()
    if not category_totals:
        await update.message.reply_text("📭 No records yet.")
        return
    message = "📊 *Expense Report:*\n\n"
    for cat, total in category_totals.items():
        message += f"• {cat}: {total:,.0f} Rial\n"
    message += "\n"
    message += f"🟢 *Total Income:* {income_total:,.0f} Rial\n"
    message += f"🔴 *Total Outcome:* {outcome_total:,.0f} Rial\n"
    message += f"⚖️ *Net:* {income_total - outcome_total:,.0f} Rial"
    await update.message.reply_text(message, parse_mode='Markdown')

# === MAIN MESSAGE HANDLER ===
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    

    # Step: START
    if text == "➕ Add Expense":
        context.user_data.clear()
        context.user_data["step"] = "choose_direction"
        keyboard = [["🟢 درآمد (Income)"], ["🔴 هزینه (Outcome)"], ["⬅️ Back"]]
        await update.message.reply_text("📂 Please choose type:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if text == "📊 Report":
        await report(update, context)
        return

    if text == "🛑 Stop":
        context.user_data.clear()
        await update.message.reply_text("🛑 Bot stopped. Send /start to begin again.")
        return

    # Step: BACK
    if text == "⬅️ Back":
        step = context.user_data.get("step")
        if step == "main_category":
            context.user_data["step"] = "choose_direction"
            keyboard = [["🟢 درآمد (Income)"], ["🔴 هزینه (Outcome)"], ["⬅️ Back"]]
            await update.message.reply_text("📂 Back to type selection:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        elif step == "sub_category":
            direction = context.user_data.get("direction")
            categories = list(INCOME_CATEGORIES.keys()) if direction == "income" else list(OUTCOME_CATEGORIES.keys())
            context.user_data["step"] = "main_category"
            keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
            await update.message.reply_text("📁 Back to main category:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        elif step == "custom_sub":
            subs = context.user_data.get("available_subs", [])
            context.user_data["step"] = "sub_category"
            keyboard = [[s] for s in subs] + [["Custom"], ["⬅️ Back"]]
            await update.message.reply_text("🔘 Choose subcategory again:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    # Step: RAW AMOUNT OR SMS
    amount, time_str, direction_detected = parse_message_for_amount(text)
    if amount and "step" not in context.user_data:
        if amount is None:
            await update.message.reply_text("❌ Please enter a valid amount.")
            return
        context.user_data.update({
            "amount": amount,
            "direction": direction_detected,
            "time_str": time_str,
            "step": "main_category"
        })
        categories = list(INCOME_CATEGORIES if direction_detected == "income" else OUTCOME_CATEGORIES)
        keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
        await update.message.reply_text(
            f"✅ Amount: {amount:,.0f} Rial\nDirection: {direction_detected.upper()}\nChoose main category:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    if text.isdigit() and "step" not in context.user_data:
        context.user_data["amount_raw"] = int(text)
        context.user_data["step"] = "choose_direction_number"
        keyboard = [["🟢 درآمد (Income)"], ["🔴 هزینه (Outcome)"]]
        await update.message.reply_text("📂 Is this income or outcome?", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if context.user_data.get("step") == "choose_direction_number":
        if "درآمد" in text:
            context.user_data["direction"] = "income"
        elif "هزینه" in text:
            context.user_data["direction"] = "outcome"
        else:
            await update.message.reply_text("❌ Invalid type. Choose درآمد or هزینه.")
            return
        context.user_data["step"] = "choose_currency"
        await update.message.reply_text("💱 Is the amount in Toman or Rial?", reply_markup=ReplyKeyboardMarkup([["💵 Toman"], ["💶 Rial"]], resize_keyboard=True))
        return

    if context.user_data.get("step") == "choose_currency":
        text_lower = text.lower()

        if "تومان" in text or "toman" in text_lower:
            amount = context.user_data["amount_raw"] * 10
        elif "ریال" in text or "rial" in text_lower:
            amount = context.user_data["amount_raw"]
        else:
            await update.message.reply_text("❌ Invalid currency. Please choose 'Toman' or 'Rial'.")
            return
        context.user_data["amount"] = amount
        context.user_data["step"] = "main_category"
        direction = context.user_data["direction"]
        categories = list(INCOME_CATEGORIES if direction == "income" else OUTCOME_CATEGORIES)
        keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
        await update.message.reply_text(
            f"✅ Amount: {amount:,.0f} Rial\nDirection: {direction.upper()}\nChoose main category:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    if context.user_data.get("step") == "choose_direction":
        if "درآمد" in text:
            context.user_data["direction"] = "income"
        elif "هزینه" in text:
            context.user_data["direction"] = "outcome"
        else:
            await update.message.reply_text("❌ Invalid type. Choose درآمد or هزینه.")
            return
        context.user_data["step"] = "main_category"
        categories = list(INCOME_CATEGORIES if context.user_data["direction"] == "income" else OUTCOME_CATEGORIES)
        keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
        await update.message.reply_text("📁 Choose main category:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if context.user_data.get("step") == "main_category":
        context.user_data["main_category"] = text
        subs = INCOME_CATEGORIES.get(text, []) if context.user_data["direction"] == "income" else OUTCOME_CATEGORIES.get(text, [])
        context.user_data["available_subs"] = subs
        context.user_data["step"] = "sub_category"
        keyboard = [[s] for s in subs] + [["Custom"], ["⬅️ Back"]]
        await update.message.reply_text("📄 Choose subcategory:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return
# /////////////////////////
    if context.user_data.get("step") == "sub_category":
        if text == "⬅️ Back":
            direction = context.user_data.get("direction")
            categories = list(INCOME_CATEGORIES.keys()) if direction == "income" else list(OUTCOME_CATEGORIES.keys())
            context.user_data["step"] = "main_category"
            keyboard = [[cat] for cat in categories] + [["⬅️ Back"]]
            await update.message.reply_text("📁 Back to main category:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return
        if text == "Custom":
            context.user_data["step"] = "custom_sub"
            await update.message.reply_text("✍️ Please type custom subcategory name:")
            return
        if text not in context.user_data.get("available_subs", []):
            await update.message.reply_text("❌ Please select a valid subcategory or Custom.")
            return

        # Save the selected subcategory and ask for confirmation
        context.user_data["sub_category"] = text
        context.user_data["step"] = "confirm_save"
        amount = context.user_data["amount"]
        main_cat = context.user_data["main_category"]
        sub_cat = context.user_data["sub_category"]
        await update.message.reply_text(
            f"✅ Amount: {amount:,.0f} Rial\nCategory: {main_cat} > {sub_cat}\n\nSave this entry?\n✅ Yes / ❌ No",
            reply_markup=ReplyKeyboardMarkup([["✅ Yes", "❌ No"]], resize_keyboard=True)
        )
        return

    if context.user_data.get("step") == "custom_sub":
        if len(text) > 30:
            await update.message.reply_text("❌ Subcategory name too long. Please limit to 30 characters.")
            return
        context.user_data["sub_category"] = text
        context.user_data["step"] = "confirm_save"
        amount = context.user_data["amount"]
        main_cat = context.user_data["main_category"]
        sub_cat = context.user_data["sub_category"]
        await update.message.reply_text(
            f"✅ Amount: {amount:,.0f} Rial\nCategory: {main_cat} > {sub_cat}\n\nSave this entry?\n✅ Yes / ❌ No",
            reply_markup=ReplyKeyboardMarkup([["✅ Yes", "❌ No"]], resize_keyboard=True)
        )
        return

    if context.user_data.get("step") == "confirm_save":
        if text == "✅ Yes":
            amount = context.user_data.get("amount")
            user_id = update.message.from_user.id
            now = datetime.now(pytz.timezone("Asia/Amman"))
            if context.user_data.get("time_str"):
                try:
                    h, m = map(int, context.user_data["time_str"].split(":"))
                    now = now.replace(hour=h, minute=m)
                except:
                    pass
            save_expense(
                user_id,
                amount,
                context.user_data["main_category"],
                context.user_data["sub_category"],
                now,
                context.user_data["direction"]
            )
            await update.message.reply_text(
                f"✅ Saved: {amount:,.0f} Rial\n📁 {context.user_data['main_category']} > {context.user_data['sub_category']}",
                reply_markup=main_keyboard
            )
            context.user_data.clear()
            return
        elif text == "❌ No":
            await update.message.reply_text("❌ Entry cancelled.", reply_markup=main_keyboard)
            context.user_data.clear()
            return
        else:
            await update.message.reply_text("❓ Please confirm: ✅ Yes or ❌ No")
            return




# === MAIN ===
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.job_queue.scheduler.configure(timezone=pytz.timezone("Asia/Amman"))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 Bot is running...")
 
    await app.run_polling()

nest_asyncio.apply()

if __name__ == "__main__":
    asyncio.run(main())
