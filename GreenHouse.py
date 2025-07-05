import csv
import re
from datetime import datetime
from collections import defaultdict
import pytz
import asyncio
import nest_asyncio


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
CSV_FILE = "expenses.csv"
CATEGORIES = ["Electricity", "Water", "Fertilizer", "Maintenance", "Other"]

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("➕ Add Expense"), KeyboardButton("📊 Report")],
        [KeyboardButton("🛑 Stop")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# === CSV HELPERS ===
def save_expense(user_id, amount, category, dt=None, direction="other"):
    if dt is None:
        dt = datetime.now(pytz.timezone("Asia/Amman"))
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([dt.strftime("%Y-%m-%d %H:%M"), user_id, amount, category, direction])

def load_expenses():
    category_totals = defaultdict(float)
    income_total = 0.0
    outcome_total = 0.0
    try:
        with open(CSV_FILE, mode='r') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) == 5:
                    _, _, amount, category, direction = row
                    amount = float(amount)
                    category_totals[category] += amount
                    if direction == "income":
                        income_total += amount
                    elif direction == "outcome":
                        outcome_total += amount
    except FileNotFoundError:
        pass
    return category_totals, income_total, outcome_total

# === PARSING ===
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

    # Optional time
    time_match = re.search(r"(\d{1,2}:\d{2})", text)
    time_str = time_match.group(1) if time_match else None

    return amount, time_str, direction

# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Choose an action:",
        reply_markup=main_keyboard
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🟡 Received:", update.message.text, flush=True)
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if text == "➕ Add Expense":
        await update.message.reply_text("📩 Please forward or type an expense SMS (e.g., برداشت300,000).")
        return
    elif text == "📊 Report":
        await report(update, context)
        return
    elif text == "🛑 Stop":
        await update.message.reply_text("🛑 Bot stopped. Send /start to begin again.")
        return

    # Step 1: Parse message
    amount, time_str, direction = parse_message_for_amount(text)
    if amount:
        context.user_data["pending_amount"] = amount
        context.user_data["pending_direction"] = direction
        if time_str:
            context.user_data["pending_time"] = time_str

        keyboard = [[cat] for cat in CATEGORIES] + [["Custom"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            f"✅ Detected amount: {amount:,.0f} Rial\nTransaction type: {direction.upper()}\nPlease choose a category:",
            reply_markup=reply_markup
        )
        return

    # Step 2: Choose category
    if "pending_amount" in context.user_data:
        amount = context.user_data.pop("pending_amount")
        direction = context.user_data.pop("pending_direction", "other")
        category = text

        if category == "Custom":
            context.user_data["custom_pending_amount"] = amount
            context.user_data["pending_direction"] = direction
            await update.message.reply_text("✍️ Please type your custom category name:")
        else:
            time_str = context.user_data.pop("pending_time", None)
            now = datetime.now(pytz.timezone("Asia/Amman"))
            if time_str:
                try:
                    hour, minute = map(int, time_str.split(":"))
                    now = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                except Exception:
                    pass
            save_expense(user_id, amount, category, now, direction)
            await update.message.reply_text(f"✅ Saved: {amount:,.0f} Rial under {category}")
        return

    # Step 3: Handle custom category name
    if "custom_pending_amount" in context.user_data:
        amount = context.user_data.pop("custom_pending_amount")
        direction = context.user_data.pop("pending_direction", "other")
        category = text
        time_str = context.user_data.pop("pending_time", None)

        now = datetime.now(pytz.timezone("Asia/Amman"))
        if time_str:
            try:
                hour, minute = map(int, time_str.split(":"))
                now = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except Exception:
                pass

        save_expense(user_id, amount, category, now, direction)
        await update.message.reply_text(f"✅ Saved: {amount:,.0f} Rial under custom category '{category}'")
        return

    await update.message.reply_text("❌ No valid amount or category found. Please send a cost message like 'برداشت300,000'.")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category_totals, income_total, outcome_total = load_expenses()
    if not category_totals:
        await update.message.reply_text("📭 No expenses recorded yet.")
        return

    message = "📊 *Expense Report:*\n\n"
    for cat, total in category_totals.items():
        message += f"• {cat}: {total:,.0f} Rial\n"

    message += "\n"
    message += f"🟢 *Total Income:* {income_total:,.0f} Rial\n"
    message += f"🔴 *Total Outcome:* {outcome_total:,.0f} Rial\n"
    message += f"⚖️ *Net Balance:* {income_total - outcome_total:,.0f} Rial"

    await update.message.reply_text(message, parse_mode='Markdown')

# === MAIN ===
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.job_queue.scheduler.configure(timezone=pytz.timezone("Asia/Amman"))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🤖 Bot is running...")
    # app.run_polling()
    
    await app.run_polling() 

nest_asyncio.apply()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

