import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8384224470:AAEFO7BQGyViHUKDP2dQav3BKRPq8sIq2tU")
DB_PATH = os.environ.get("DB_PATH", "accounts.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'TWD',
        note TEXT,
        date TEXT NOT NULL,
        type TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS rates (
        currency TEXT PRIMARY KEY,
        rate REAL NOT NULL
    )""")
    c.execute("INSERT OR IGNORE INTO rates VALUES ('CNY', 4.65)")
    c.execute("INSERT OR IGNORE INTO rates VALUES ('USDT', 33.0)")
    conn.commit()
    try:
        c.execute("ALTER TABLE records ADD COLUMN currency TEXT DEFAULT 'TWD'")
        conn.commit()
    except Exception:
        pass
    # creditor: '' = personal mode (owes YOU); 'Name' = group expense mode (owes that person)
    try:
        c.execute("ALTER TABLE records ADD COLUMN creditor TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    conn.close()

def add_expense_record(debtor, creditor, amount, currency, note):
    """Group expense: debtor owes creditor the amount."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = datetime.now().strftime("%Y/%m/%d")
    c.execute(
        "INSERT INTO records (person, creditor, amount, currency, note, date, type) VALUES (?, ?, ?, ?, ?, ?, 'owe')",
        (debtor.strip(), creditor.strip(), amount, (currency or "TWD").upper(), note, date)
    )
    conn.commit()
    conn.close()

def get_group_balances():
    """Net balance for group expenses (creditor != '')."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Get all group expense records
    c.execute("""
        SELECT person, creditor, currency,
               SUM(CASE WHEN type='owe' THEN amount ELSE -amount END) AS amount
        FROM records
        WHERE creditor != '' AND creditor IS NOT NULL
        GROUP BY person, creditor, currency
        HAVING amount != 0
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def get_rate(currency):
    currency = (currency or "TWD").upper()
    if currency == "TWD":
        return 1.0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rate FROM rates WHERE currency=?", (currency,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_rate(currency, rate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO rates VALUES (?, ?)", (currency.upper(), rate))
    conn.commit()
    conn.close()

def get_all_rates():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT currency, rate FROM rates ORDER BY currency")
    rows = c.fetchall()
    conn.close()
    return rows

def add_record(person, amount, currency, note, record_type):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date = datetime.now().strftime("%Y/%m/%d")
    c.execute(
        "INSERT INTO records (person, amount, currency, note, date, type) VALUES (?, ?, ?, ?, ?, ?)",
        (person.strip(), amount, (currency or "TWD").upper(), note, date, record_type)
    )
    conn.commit()
    conn.close()

def get_person_records(person):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT date, amount, currency, type, note FROM records WHERE person=? ORDER BY id", (person,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_balances():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT person,
               COALESCE(currency, 'TWD') as currency,
               SUM(CASE WHEN type='owe' THEN amount ELSE -amount END) AS balance
        FROM records
        GROUP BY person, COALESCE(currency, 'TWD')
        HAVING balance != 0
        ORDER BY person, currency
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def clear_person(person):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM records WHERE person=?", (person,))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n

def fmt(amount, currency):
    currency = (currency or "TWD").upper()
    if currency == "USDT":
        return f"{amount:,.2f} {currency}"
    return f"{amount:,.0f} {currency}"

def twd_equiv(amount, currency):
    currency = (currency or "TWD").upper()
    if currency == "TWD":
        return None
    rate = get_rate(currency)
    if not rate:
        return None
    return f"~{amount * rate:,.0f} TWD"

def parse_amount_currency(text, default_currency="TWD"):
    text = text.strip().upper()
    m = re.match(r"^(\d+(?:\.\d+)?)(CNY|TWD|USDT)?$", text)
    if m:
        return float(m.group(1)), m.group(2) or default_currency
    return None, None

QUICK_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("查账"), KeyboardButton("汇率")]],
    resize_keyboard=True,
    is_persistent=True
)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "*[-- 记账机器人指令 --]*\n\n"
        "*记欠款：*\n"
        "`/owe A 500` - A 欠你 500 TWD\n"
        "`/owe A 500 cny 备注` - 指定货币+备注\n"
        "`/owe A 500 B 300 C 200` - 多人一次记\n\n"
        "*分摊账单：*\n"
        "`/split 备注 总额 A份额 B份额 C份额` - 不等分\n"
        "  `/split 晚餐 3000 A 1000 B 1000 C 1000`\n"
        "`/split 备注 总额 [货币] A B C` - 等分\n"
        "  `/split 晚餐 3000 cny A B C`\n\n"
        "*还款：*\n"
        "`/paid A 500` - A 还了 500 TWD\n"
        "`/paid A 200 cny` - 指定货币\n\n"
        "*查询：*\n"
        "`/check` - 所有人欠款总览\n"
        "`/bill A` - 查某人所有明细\n\n"
        "*多人分账（旅行/聚餐）：*\n"
        "`/expense A 10000 cny A B C` - A付款，三人等分\n"
        "`/expense A 10000 cny B 3000 C 7000` - 不等分\n"
        "`/settle` - 计算最终谁付谁多少\n\n"
        "*删除：*\n"
        "`/clear A` - 删除某人所有记录\n"
        "`/clearall` - 清空全部记录\n\n"
        "*汇率：*\n"
        "`/rate` - 查看当前汇率\n"
        "`/rate cny 4.65` - 设 1 CNY = 4.65 TWD\n"
        "`/rate usdt 33` - 设 1 USDT = 33 TWD\n\n"
        "_默认货币：TWD_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=QUICK_KEYBOARD)

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    await update.message.reply_text(f"你的 Telegram ID 是：`{uid}`\n名字：{name}", parse_mode="Markdown")

async def cmd_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        rates = get_all_rates()
        msg = "*Exchange rates (to TWD):*\n\n"
        for cur, rate in rates:
            msg += f"1 {cur} = {rate} TWD\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    if len(args) != 2:
        await update.message.reply_text("Format: `/rate cny 4.65`", parse_mode="Markdown")
        return
    currency = args[0].upper()
    if currency not in ("CNY", "USDT"):
        await update.message.reply_text("Supported: CNY, USDT")
        return
    try:
        rate = float(args[1])
    except ValueError:
        await update.message.reply_text("Rate must be a number")
        return
    set_rate(currency, rate)
    await update.message.reply_text(f"OK: 1 {currency} = {rate} TWD")

async def cmd_owe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = list(context.args)
    if len(args) < 2:
        await update.message.reply_text("Format: `/owe A 500 cny note` or `/owe A 500 B 300`", parse_mode="Markdown")
        return
    global_currency = "TWD"
    if args[-1].upper() in ("CNY", "TWD", "USDT"):
        global_currency = args[-1].upper()
        args = args[:-1]
    pairs = []
    i = 0
    while i < len(args) - 1:
        name = args[i]
        num_str = args[i + 1].upper()
        m = re.match(r"^(\d+(?:\.\d+)?)(CNY|TWD|USDT)?$", num_str)
        if m and not re.match(r"^\d", name):
            pairs.append((name, float(m.group(1)), m.group(2) or global_currency))
            i += 2
        else:
            break
    if len(pairs) > 1 and i >= len(args):
        saved = []
        for person, amount, currency in pairs:
            add_record(person, amount, currency, "", "owe")
            line = f"  {person}: {fmt(amount, currency)}"
            eq = twd_equiv(amount, currency)
            if eq:
                line += f" ({eq})"
            saved.append(line)
        await update.message.reply_text("OK recorded:\n" + "\n".join(saved), parse_mode="Markdown")
        return
    person = args[0]
    amount, currency = parse_amount_currency(args[1], global_currency)
    if amount is None:
        await update.message.reply_text("Invalid amount", parse_mode="Markdown")
        return
    note_parts = args[2:]
    if note_parts and note_parts[0].upper() in ("CNY", "TWD", "USDT"):
        currency = note_parts[0].upper()
        note_parts = note_parts[1:]
    note = " ".join(note_parts)
    add_record(person, amount, currency, note, "owe")
    msg = f"OK: *{person}* owes *{fmt(amount, currency)}*"
    eq = twd_equiv(amount, currency)
    if eq:
        msg += f" ({eq})"
    if note:
        msg += f"\n{note}"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = list(context.args)
    if len(args) < 3:
        await update.message.reply_text(
            "Format:\n`/split dinner 3000 A 1000 B 1000 C 1000`\n`/split dinner 3000 cny A B C`",
            parse_mode="Markdown"
        )
        return
    note = args[0]
    total, currency = parse_amount_currency(args[1])
    if total is None:
        await update.message.reply_text("Invalid total amount", parse_mode="Markdown")
        return
    rest = args[2:]
    if rest and rest[0].upper() in ("CNY", "TWD", "USDT"):
        currency = rest[0].upper()
        rest = rest[1:]
    if not rest:
        await update.message.reply_text("Please add names", parse_mode="Markdown")
        return
    splits = {}
    all_names = all(not re.match(r"^\d", r) for r in rest)
    if all_names:
        per = total / len(rest)
        for name in rest:
            splits[name] = per
    else:
        i = 0
        while i < len(rest):
            name = rest[i]
            if i + 1 < len(rest):
                amt, _ = parse_amount_currency(rest[i + 1], currency)
                if amt is not None:
                    splits[name] = amt
                    i += 2
                    continue
            splits[name] = None
            i += 1
        assigned = sum(v for v in splits.values() if v is not None)
        no_amt = [k for k, v in splits.items() if v is None]
        if no_amt:
            per = (total - assigned) / len(no_amt)
            for name in no_amt:
                splits[name] = per
    saved = []
    for person, amount in splits.items():
        add_record(person, amount, currency, note, "owe")
        line = f"  {person}: {fmt(amount, currency)}"
        eq = twd_equiv(amount, currency)
        if eq:
            line += f" ({eq})"
        saved.append(line)
    msg = f"OK [{note}] split done\nTotal: {fmt(total, currency)}"
    eq = twd_equiv(total, currency)
    if eq:
        msg += f" ({eq})"
    msg += "\n" + "\n".join(saved)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Format: `/paid A 500 cny`", parse_mode="Markdown")
        return
    person = args[0]
    amount, currency = parse_amount_currency(args[1])
    if amount is None:
        await update.message.reply_text("Invalid amount", parse_mode="Markdown")
        return
    if len(args) >= 3 and args[2].upper() in ("CNY", "TWD", "USDT"):
        currency = args[2].upper()
    add_record(person, amount, currency, "", "pay")
    msg = f"OK: *{person}* paid *{fmt(amount, currency)}*"
    eq = twd_equiv(amount, currency)
    if eq:
        msg += f" ({eq})"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    balances = get_all_balances()
    if not balances:
        await update.message.reply_text("No records yet")
        return
    by_person = defaultdict(list)
    for person, currency, balance in balances:
        by_person[person].append((currency or "TWD", balance))
    msg = "*Balance Overview*\n\n"
    for person, items in sorted(by_person.items()):
        parts = []
        twd_total = 0
        has_non_twd = False
        for currency, balance in items:
            parts.append(fmt(abs(balance), currency))
            rate = get_rate(currency)
            if rate:
                twd_total += abs(balance) * rate * (1 if balance > 0 else -1)
            if currency != "TWD":
                has_non_twd = True
        msg += f"*{person}*: {' + '.join(parts)}"
        if has_non_twd:
            msg += f"\n  (~{twd_total:,.0f} TWD)"
        msg += "\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: `/bill A`", parse_mode="Markdown")
        return
    person = " ".join(context.args)
    records = get_person_records(person)
    if not records:
        await update.message.reply_text(f"No records for {person}")
        r