import csv
import re
from datetime import datetime
from collections import defaultdict
import pytz

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
def save_expense(user_id, amount, category, dt=None):
    if dt is None:
        dt = datetime.now(pytz.timezone("Asia/Amman"))
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([dt.strftime("%Y-%m-%d %H:%M"), user_id, amount, category])


def load_expenses():
    data = defaultdict(float)
    try:
        with open(CSV_FILE, mode='r') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) == 4:
                    _, _, amount, category = row
                    data[category] += float(amount)
    except FileNotFoundError:
        pass
    return data

# === PARSING ===
def parse_message_for_amount(text):
    amount_match = re.search(r"برداشت\s*([\d,]+)", text)
    time_match = re.search(r"(\d{1,2}:\d{2})", text)

    amount = None
    time_str = None

    if amount_match:
        amount_str = amount_match.group(1).replace(",", "")
        try:
            amount = float(amount_str)
        except ValueError:
            amount = None

    if time_match:
        time_str = time_match.group(1)

    return amount, time_str

# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Choose an action:",
        reply_markup=main_keyboard
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    # === Handle Main Menu Buttons ===
    if text == "➕ Add Expense":
        await update.message.reply_text("📩 Please forward or type an expense SMS (e.g., برداشت300,000).")
        return
    elif text == "📊 Report":
        await report(update, context)
        return
    elif text == "🛑 Stop":
        await update.message.reply_text("🛑 Bot stopped. Send /start to begin again.")
        return

    # === Step 1: Parse "برداشت..." message ===
    if "برداشت" in text:
        amount, time_str = parse_message_for_amount(text)
        if amount:
            context.user_data["pending_amount"] = amount
            if time_str:
                context.user_data["pending_time"] = time_str

            keyboard = [[cat] for cat in CATEGORIES] + [["Custom"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

            await update.message.reply_text(
                f"Detected amount: {amount:.2f} Rial\nPlease choose a category:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Could not parse the amount. Try again.")
        return

    # === Step 2: Category selected ===
    if "pending_amount" in context.user_data:
        amount = context.user_data.pop("pending_amount")
        category = text

        if category == "Custom":
            context.user_data["custom_pending_amount"] = amount
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
            save_expense(user_id, amount, category, now)
            await update.message.reply_text(f"✅ Saved: {amount:.2f} Rial under {category}")
        return

    # === Step 3: Custom category ===
    if "custom_pending_amount" in context.user_data:
        amount = context.user_data.pop("custom_pending_amount")
        category = text

        time_str = context.user_data.pop("pending_time", None)
        now = datetime.now(pytz.timezone("Asia/Amman"))
        if time_str:
            try:
                hour, minute = map(int, time_str.split(":"))
                now = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except Exception:
                pass

        save_expense(user_id, amount, category, now)
        await update.message.reply_text(f"✅ Saved: {amount:.2f} Rial under custom category '{category}'")
        return

    # === Fallback ===
    await update.message.reply_text("❌ No valid amount or category found. Please send a cost message like 'برداشت300,000'.")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    totals = load_expenses()
    if not totals:
        await update.message.reply_text("📭 No expenses recorded yet.")
        return

    message = "📊 *Expense Report:*\n"
    for cat, total in totals.items():
        message += f"- {cat}: {total:.2f} JD\n"
    await update.message.reply_text(message, parse_mode='Markdown')

# === MAIN ===
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.scheduler.configure(timezone=pytz.timezone("Asia/Amman"))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
