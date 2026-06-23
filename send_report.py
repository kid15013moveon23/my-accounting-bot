"""
每日数据汇报机器人 - AI 分析版
GitHub Actions 每天 11:00 上海时间自动发送
- 先用 Claude API 做 COO 级经营分析
- 失败时自动降级为原始数据日报
"""
import os, json, re, asyncio
from datetime import datetime, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials
import telegram
import anthropic

# ─── Secrets ──────────────────────────────────────────────────────────────────
TG_TOKEN      = os.environ['TG_TOKEN']
TG_CHAT_ID    = os.environ['TG_CHAT_ID']
SA_JSON       = json.loads(os.environ['GSHEET_SA_JSON'])
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')
CLAUDE_MODEL   = os.environ.get('CLAUDE_MODEL', 'claude-haiku-4-5-20251001')

SHANGHAI = pytz.timezone('Asia/Shanghai')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds    = Credentials.from_service_account_info(SA_JSON, scopes=SCOPES)
client   = gspread.authorize(creds)

# ─── Department configs ────────────────────────────────────────────────────────
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
            "注册": 1,  "首存": 2,
            "存款": 8,  "提款": 9,  "存提差": 10,
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
    variants  = date_variants(target_date)
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
        ss       = client.open_by_key(dept["sheet_id"])
        ws       = pick_worksheet(ss, dept["worksheet"])
        all_data = ws.get_all_values()
        if not all_data:
            return f"【{label}】⚠️ 空表", None, None

        row, date_str, exact = find_data_row(
            all_data, dept["direction"], dept["date_col"], yesterday
        )
        if row is None:
            return f"【{label}】⚠️ 无有效数据", None, None

        ymd  = f"{yesterday.month}/{yesterday.day}"
        note = "" if exact else f"⚠️数据截至{date_str} "
        lines = [f"【{label}】{note}{ymd}"]

        data = {}
        raw  = {}
        for name, col in dept["columns"].items():
            val = safe(row, col)
            lines.append(f"  {name}: {val}")
            if name in SUMMARY_FIELDS:
                data[name] = parse_num(val)
            raw[name] = val

        return "\n".join(lines), data, raw

    except Exception as e:
        return f"【{label}】❌ {e}", None, None

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

# ─── Claude AI 分析 ────────────────────────────────────────────────────────────
def build_analysis_payload(yesterday: datetime, dept_raw: dict) -> dict:
    mt_members = ["QY", "TH", "LW", "QM", "RB"]
    rt_members = ["UED", "JX", "TQ"]

    def group_total(members, field):
        total = 0.0
        for m in members:
            raw = dept_raw.get(m) or {}
            val = raw.get(field, "—")
            if val != "—":
                total += parse_num(val)
        return total

    payload = {
        "日期": f"{yesterday.year}年{yesterday.month}月{yesterday.day}日",
        "各部门数据": {},
        "MT汇总": {},
        "RT汇总": {},
    }

    for dept in DEPARTMENTS:
        label = dept["label"]
        raw   = dept_raw.get(label)
        if raw:
            payload["各部门数据"][label] = {"组别": dept["group"], **raw}
        else:
            payload["各部门数据"][label] = {"组别": dept["group"], "状态": "数据缺失"}

    for f in SUMMARY_FIELDS:
        payload["MT汇总"][f] = fmt_num(group_total(mt_members, f))
        payload["RT汇总"][f] = fmt_num(group_total(rt_members, f))

    return payload


def call_claude(payload: dict) -> str:
    if not CLAUDE_API_KEY:
        return ""

    data_json = json.dumps(payload, ensure_ascii=False, indent=2)

    system_prompt = """你是一位在线娱乐／体育综合平台的 COO 数据分析助理。
你每天会收到八个部门（UED、RB、QM、QY、TQ、TH、LW、JX）的经营数据。

分析规则：
1. 不要只看单一指标，要综合看活跃、存款、存提差、首存转化率。
2. 首存转化率 = 首存/注册，低于 10% 要提醒。
3. 存提差为负或远低于存款，可能代表高提现压力或套利风险。
4. 活跃上升但存提差未同步上升，可能是低价值流量或促销依赖。
5. 若某部门注册高但首存极低，代表流量质量差或转化漏斗有问题。
6. 输出使用简体中文，语气简洁专业，适合 Telegram 阅读。
7. 控制总字数在 600 字以内，避免大段文字。"""

    user_prompt = f"""以下是今日各部门经营数据（JSON 格式）：

{data_json}

请按照以下固定格式输出经营简报：

【每日经营重点】
（3-5 句话总结今日整体状况，重点说明好的地方和需要关注的地方）

【部门异常提醒】
（列出 1-3 个最需要关注的部门，每条格式：
▶ [部门名] 指标异常 → 可能原因 → 建议关注点）

【需要跟进事项】
（给出 3-5 条可执行的具体建议，直接交给运营主管执行）

【一句话结论】
（用一句话告诉 COO 今天最需要关注什么）

注意：
- 如果数据正常，不需要强行找异常，可以输出正面总结
- 不要重复数字，分析要有洞察
- 重点突出，控制篇幅"""

    try:
        ai_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message   = ai_client.messages.create(
            model      = CLAUDE_MODEL,
            max_tokens = 1024,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"[Claude API Error] {e}")
        return ""

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    yesterday = datetime.now(SHANGHAI) - timedelta(days=1)

    dept_results = {}
    dept_raw     = {}
    blocks       = []

    for dept in DEPARTMENTS:
        result = fetch(dept, yesterday)
        if len(result) == 3:
            text, data, raw = result
        else:
            text, data = result
            raw = None

        dept_results[dept["label"]] = data
        dept_raw[dept["label"]]     = raw
        blocks.append(text)

    mt_summary = build_summary("MT汇总", ["QY", "TH", "LW", "QM", "RB"], dept_results)
    rt_summary = build_summary("RT汇总", ["UED", "JX", "TQ"], dept_results)

    date_label = f"{yesterday.month}月{yesterday.day}日"

    raw_report = (
        f"📊 {date_label} 各部门原始数据\n\n"
        + "\n\n".join(blocks)
        + f"\n\n{'─'*20}\n\n"
        + mt_summary
        + "\n\n"
        + rt_summary
    )

    bot = telegram.Bot(token=TG_TOKEN)

    ai_report = ""
    if CLAUDE_API_KEY:
        try:
            payload   = build_analysis_payload(yesterday, dept_raw)
            ai_report = call_claude(payload)
        except Exception as e:
            print(f"[AI Analysis Error] {e}")
            ai_report = ""

    if ai_report:
        ai_message = f"🤖 {date_label} COO 经营简报（AI分析）\n\n{ai_report}"
        await bot.send_message(chat_id=TG_CHAT_ID, text=ai_message)
        await bot.send_message(chat_id=TG_CHAT_ID, text=raw_report)
    else:
        await bot.send_message(chat_id=TG_CHAT_ID, text=raw_report)
        if CLAUDE_API_KEY:
            await bot.send_message(
                chat_id=TG_CHAT_ID,
                text="⚠️ AI 分析暂时不可用，已发送原始数据日报。"
            )

if __name__ == "__main__":
    asyncio.run(main())
