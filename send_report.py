"""
每日数据汇报机器人 - 全部门版 + MT/RT 汇总
GitHub Actions 每天 11:00 上海时间自动发送
"""
import os, json, re, asyncio
from datetime import datetime, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials
import telegram

# ─── Secrets ──────────────────────────────────────────────────────────────────
TG_TOKEN   = os.environ['TG_TOKEN']
TG_CHAT_ID = os.environ['TG_CHAT_ID']
SA_JSON    = json.loads(os.environ['GSHEET_SA_JSON'])

SHANGHAI = pytz.timezone('Asia/Shanghai')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds  = Credentials.from_service_account_info(SA_JSON, scopes=SCOPES)
client = gspread.authorize(creds)

# ─── Department configs ────────────────────────────────────────────────────────
# MT汇总 = QY / TH / LW / QM / RB
# RT汇总 = UED / JX / TQ
DEPARTMENTS = [
    {
        "label":     "UED",
        "group":     "RT",
        "sheet_id":  "1a7ZBESgUweasFGf2FfDx1TbMvb1onS-knTU7cx2I13g",
        "worksheet": "每日明细",
        "date_col":  0,
        "direction": "top",
        "columns": {
            "注册": 25, "首存": 26,
            "存款": 3,  "提款": 4, "存提差": 5,
            "活跃": 18,
        },
    },
    {
        "label":     "RB",
        "group":     "MT",
        "sheet_id":  "1iErwKLMSsPEcnYravOzhMGuTiZBBUYedggr84UU8Ilo",
        "worksheet": "每日数据",
        "date_col":  0,
        "direction": "bottom",
        "columns": {
            "注册": 1,  "首存": 2,
            "存款": 8,  "提款": 11, "存提差": 12,
        },
    },
    {
        "label":     "QM",
        "group":     "MT",
        "sheet_id":  "1drz_NT2aTiPHfvX-xOmJR72q-o9Mk9hucPGTfTfFLmI",
        "worksheet": "每日数据",
        "date_col":  0,
        "direction": "bottom",
        "columns": {
            "注册": 1,  "首存": 2,
            "存款": 8,  "提款": 11, "存提差": 12,
        },
    },
    {
        "label":     "QY",
        "group":     "MT",
        "sheet_id":  "1NMOTloCNN7lDpa2Wjtehcdx75UU7Rx7HAepXYv5SgB0",
        "worksheet": "每日数据",
        "date_col":  0,
        "direction": "bottom",
        "columns": {
            "注册": 1,  "首存": 3,
            "存款": 9,  "提款": 12, "存提差": 13,
            "活跃": 10,
        },
    },
    {
        "label":     "TQ",
        "group":     "RT",
        "sheet_id":  "1RbcFCX8a-vUwsRKcu2ONzu_IBx0gyUw4Kds7HXwfUNM",
        "worksheet": "每日明细",
        "date_col":  0,
        "direction": "top",
        "columns": {
            "注册": 24, "首存": 25,
            "存款": 3,  "提款": 4, "存提差": 5,
            "活跃": 18,
        },
    },
    {
        "label":     "TH",
        "group":     "MT",
        "sheet_id":  "1JKgkLj_ltl5wwhB7u4Uy8DBgznKpys75kGdJZF9LBuQ",
        "worksheet": "每日基础数据",
        "date_col":  0,
        "direction": "bottom",
        "columns": {
            "注册": 1,  "首存": 2,
            "存款": 8,  "提款": 11, "存提差": 12,
            "活跃": 9,
        },
    },
    {
        "label":     "LW",
        "group":     "MT",
        "sheet_id":  "1BqU6DF7SReWGZSCeT0vtJH4RoVtc2qMMah5PR9ZF2AI",
        "worksheet": "网站基本日数据",
        "date_col":  0,
        "direction": "bottom",
        "columns": {
            "注册": 1,
            "首存": 2,
            "存款": 8,
            "提款": 9,
            "存提差": 10,
            "活跃": 11,
        },
    },
    {
        "label":     "JX",
        "group":     "RT",
        "sheet_id":  "1oCYfkGtDaGeGguS5XkpPjyvGZnzUfC_whVrGdZgbqMM",
        "worksheet": "每日明细",
        "date_col":  0,
        "direction": "top",
        "columns": {
            "注册": 24, "首存": 25,
            "存款": 3,  "提款": 4, "存提差": 5,
            "活跃": 18,
        },
    },
]

SUMMARY_FIELDS = ["注册", "首存", "存款", "提款", "存提差"]

# ─── Helpers ───────────────────────────────────────────────────────────────────
def is_summary(val: str) -> bool:
    v = val.strip()
    if not v: return True
    if v in ("日均", "合计", "总计", "平均", "汇总", "小计"): return True
    return not bool(re.search(r'\d', v))

def date_variants(d: datetime):
    m, day, y = d.month, d.day, d.year
    return [
        f"{m}/{day}", f"{m}-{day}",
        f"{m:02d}/{day:02d}", f"{m:02d}-{day:02d}",
        f"{m}月{day}日",
        f"{y}/{m}/{day}", f"{y}-{m}-{day}",
        f"{y}/{m:02d}/{day:02d}", f"{y}-{m:02d}-{day:02d}",
    ]

def pick_worksheet(ss, ws_hint: str):
    for w in ss.worksheets():
        if ws_hint in w.title:
            return w
    for w in ss.worksheets():
        if "每日" in w.title:
            return w
    return ss.worksheets()[0]

def find_data_row(all_data, direction, date_col, target_date):
    variants = date_variants(target_date)
    data_rows = all_data[1:]
    ordered   = list(reversed(data_rows)) if direction == "bottom" else data_rows

    def valid(row):
        if len(row) <= date_col: return False
        return not is_summary(row[date_col].strip())

    for row in ordered:
        if not valid(row): continue
        if row[date_col].strip() in variants:
            return row, row[date_col].strip(), True

    for row in ordered:
        if not valid(row): continue
        v = row[date_col].strip()
        if any(var in v for var in variants):
            return row, v, True

    for row in ordered:
        if not valid(row): continue
        if sum(1 for c in row if c.strip()) > 3:
            return row, row[date_col].strip(), False

    return None, None, False

def safe(row, col):
    try:
        v = row[col].strip()
        return v if v else "—"
    except IndexError:
        return "—"

def parse_num(s: str) -> float:
    s = re.sub(r'[￥¥,$\s]', '', s)
    s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return 0.0

def fmt_num(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"

# ─── Fetch ────────────────────────────────────────────────────────────────────
def fetch(dept, yesterday):
    label = dept["label"]
    try:
        ss = client.open_by_key(dept["sheet_id"])
        ws = pick_worksheet(ss, dept["worksheet"])
        all_data = ws.get_all_values()
        if not all_data:
            return f"【{label}】⚠️ 空表", None

        row, date_str, exact = find_data_row(
            all_data, dept["direction"], dept["date_col"], yesterday
        )
        if row is None:
            return f"【{label}】⚠️ 无有效数据", None

        ymd  = f"{yesterday.month}/{yesterday.day}"
        note = "" if exact else f"⚠️数据截至{date_str} "
        lines = [f"【{label}】{note}{ymd}"]

        data = {}
        for name, col in dept["columns"].items():
            val = safe(row, col)
            lines.append(f"  {name}: {val}")
            if name in SUMMARY_FIELDS:
                data[name] = parse_num(val)

        return "\n".join(lines), data

    except Exception as e:
        return f"【{label}】❌ {e}", None

# ─── Summary ──────────────────────────────────────────────────────────────────
def build_summary(label: str, members: list, results: dict) -> str:
    totals  = {f: 0.0 for f in SUMMARY_FIELDS}
    missing = []
    for m in members:
        d = results.get(m)
        if d is None:
            missing.append(m)
            continue
        for f in SUMMARY_FIELDS:
            totals[f] += d.get(f, 0.0)

    lines = [f"【{label}】({'、'.join(members)})"]
    for f in SUMMARY_FIELDS:
        lines.append(f"  {f}: {fmt_num(totals[f])}")
    if missing:
        lines.append(f"  ⚠️ 缺失: {' '.join(missing)}")
    return "\n".join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    yesterday = datetime.now(SHANGHAI) - timedelta(days=1)

    dept_results = {}
    blocks = []

    for dept in DEPARTMENTS:
        text, data = fetch(dept, yesterday)
        dept_results[dept["label"]] = data
        blocks.append(text)

    mt_summary = build_summary("MT汇总", ["QY", "TH", "LW", "QM", "RB"], dept_results)
    rt_summary = build_summary("RT汇总", ["UED", "JX", "TQ"], dept_results)

    date_label = f"{yesterday.month}月{yesterday.day}日"
    message = (
        f"📊 {date_label} 各部门日报\n\n"
        + "\n\n".join(blocks)
        + f"\n\n{'─'*20}\n\n"
        + mt_summary
        + "\n\n"
        + rt_summary
    )

    bot = telegram.Bot(token=TG_TOKEN)
    await bot.send_message(chat_id=TG_CHAT_ID, text=message)

if __name__ == "__main__":
    asyncio.run(main())
