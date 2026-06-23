"""
每日数据汇报机器人 - AI 分析版（含历史趋势对比）
GitHub Actions 每天 11:00 上海时间自动发送
- 数据存入历史 Sheet（日/周/月对比）
- Claude API 做 COO 级趋势分析
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
TG_TOKEN         = os.environ['TG_TOKEN']
TG_CHAT_ID       = os.environ['TG_CHAT_ID']
SA_JSON          = json.loads(os.environ['GSHEET_SA_JSON'])
CLAUDE_API_KEY   = os.environ.get('CLAUDE_API_KEY', '')
CLAUDE_MODEL     = os.environ.get('CLAUDE_MODEL', 'claude-haiku-4-5-20251001')
HISTORY_SHEET_ID = os.environ.get('HISTORY_SHEET_ID', '')

SHANGHAI = pytz.timezone('Asia/Shanghai')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']   # 需要写权限
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
HISTORY_FIELDS = ["注册", "首存", "存款", "提款", "存提差", "活跃"]

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
    if not s or s == "—": return 0.0
    s = re.sub(r'[￥¥,$\s,]', '', str(s))
    try:
        return float(s)
    except ValueError:
        return 0.0

def fmt_num(n: float) -> str:
    if n == 0: return "0"
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"

def pct_change(new: float, old: float) -> str:
    if old == 0:
        return "N/A"
    change = (new - old) / abs(old) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"

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

# ─── History: Save ────────────────────────────────────────────────────────────
def save_to_history(yesterday: datetime, dept_raw: dict):
    if not HISTORY_SHEET_ID:
        print("[History] 未设置 HISTORY_SHEET_ID，跳过保存")
        return
    try:
        ss = client.open_by_key(HISTORY_SHEET_ID)
        ws = ss.worksheets()[0]
        all_data = ws.get_all_values()

        if not all_data or not any(cell.strip() for cell in all_data[0]):
            header = ['日期', '部门', '组别', '注册', '首存', '存款', '提款', '存提差', '活跃']
            ws.update(range_name='A1', values=[header])
            all_data = [header]

        date_str = yesterday.strftime('%Y-%m-%d')
        existing = {row[0] for row in all_data[1:] if row and row[0]}
        if date_str in existing:
            print(f"[History] {date_str} 已存在，跳过写入")
            return

        rows = []
        for dept in DEPARTMENTS:
            raw = dept_raw.get(dept['label']) or {}
            rows.append([
                date_str, dept['label'], dept['group'],
                raw.get('注册', ''), raw.get('首存', ''),
                raw.get('存款', ''), raw.get('提款', ''),
                raw.get('存提差', ''), raw.get('活跃', ''),
            ])

        ws.append_rows(rows, value_input_option='USER_ENTERED')
        print(f"[History] 已保存 {date_str}，{len(rows)} 部门")
    except Exception as e:
        print(f"[History Save Error] {e}")

# ─── History: Load & Compare ──────────────────────────────────────────────────
def load_history(yesterday: datetime) -> dict:
    if not HISTORY_SHEET_ID:
        return {}
    try:
        ss = client.open_by_key(HISTORY_SHEET_ID)
        ws = ss.worksheets()[0]
        all_data = ws.get_all_values()
        if len(all_data) <= 1:
            return {}

        parsed = []
        for row in all_data[1:]:
            if len(row) < 3 or not row[0]:
                continue
            try:
                d = datetime.strptime(row[0], '%Y-%m-%d')
            except:
                continue
            parsed.append({
                'date_str': row[0],
                'dept':     row[1] if len(row) > 1 else '',
                '注册':     row[3] if len(row) > 3 else '',
                '首存':     row[4] if len(row) > 4 else '',
                '存款':     row[5] if len(row) > 5 else '',
                '提款':     row[6] if len(row) > 6 else '',
                '存提差':   row[7] if len(row) > 7 else '',
                '活跃':     row[8] if len(row) > 8 else '',
            })

        def day_data(target: datetime) -> dict:
            ts = target.strftime('%Y-%m-%d')
            result = {}
            for r in parsed:
                if r['date_str'] == ts and r['dept']:
                    result[r['dept']] = {f: r[f] for f in HISTORY_FIELDS}
            return result

        def period_totals(start: datetime, end: datetime) -> dict:
            s = start.strftime('%Y-%m-%d')
            e = end.strftime('%Y-%m-%d')
            totals = {}
            for r in parsed:
                if r['date_str'] < s or r['date_str'] > e or not r['dept']:
                    continue
                dept = r['dept']
                if dept not in totals:
                    totals[dept] = {f: 0.0 for f in HISTORY_FIELDS}
                for f in HISTORY_FIELDS:
                    totals[dept][f] += parse_num(r[f])
            return {dept: {f: fmt_num(v) for f, v in fields.items()}
                    for dept, fields in totals.items()}

        day_before = yesterday - timedelta(days=1)
        week_ago   = yesterday - timedelta(days=7)

        month_start      = yesterday.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_elapsed     = yesterday.day - 1
        last_month_end   = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        last_month_same  = last_month_start + timedelta(days=days_elapsed - 1)

        history_month = period_totals(month_start, day_before) if days_elapsed > 0 else {}
        last_month    = period_totals(last_month_start, last_month_same) if days_elapsed > 0 else {}

        return {
            '前日数据':     day_data(day_before),
            '7天前数据':    day_data(week_ago),
            '本月历史累计': history_month,
            '上月同期累计': last_month,
            '本月天数':     yesterday.day,
        }
    except Exception as e:
        print(f"[History Load Error] {e}")
        return {}

# ─── Build Analysis Payload ───────────────────────────────────────────────────
def build_analysis_payload(yesterday: datetime, dept_raw: dict, history: dict) -> dict:
    mt_members = ["QY", "TH", "LW", "QM", "RB"]
    rt_members = ["UED", "JX", "TQ"]

    def group_sum(members: list, field: str, source: dict) -> float:
        return sum(parse_num((source.get(m) or {}).get(field, '0')) for m in members)

    today_depts = {}
    for dept in DEPARTMENTS:
        label = dept["label"]
        raw   = dept_raw.get(label)
        today_depts[label] = {"组别": dept["group"], **(raw or {"状态": "数据缺失"})}

    payload = {
        "日期":       f"{yesterday.year}年{yesterday.month}月{yesterday.day}日",
        "今日数据":   today_depts,
        "今日汇总": {
            "MT": {f: fmt_num(group_sum(mt_members, f, dept_raw)) for f in SUMMARY_FIELDS},
            "RT": {f: fmt_num(group_sum(rt_members, f, dept_raw)) for f in SUMMARY_FIELDS},
        },
    }

    if history:
        prev = history.get('前日数据', {})
        w7   = history.get('7天前数据', {})

        if prev:
            payload["前日汇总"] = {
                "MT": {f: fmt_num(group_sum(mt_members, f, prev)) for f in SUMMARY_FIELDS},
                "RT": {f: fmt_num(group_sum(rt_members, f, prev)) for f in SUMMARY_FIELDS},
            }
            payload["日环比（今日 vs 前日）"] = {
                "MT存款": pct_change(group_sum(mt_members, '存款', dept_raw), group_sum(mt_members, '存款', prev)),
                "RT存款": pct_change(group_sum(rt_members, '存款', dept_raw), group_sum(rt_members, '存款', prev)),
                "MT注册": pct_change(group_sum(mt_members, '注册', dept_raw), group_sum(mt_members, '注册', prev)),
                "RT注册": pct_change(group_sum(rt_members, '注册', dept_raw), group_sum(rt_members, '注册', prev)),
                "各部门存款": {
                    dept["label"]: pct_change(
                        parse_num((dept_raw.get(dept["label"]) or {}).get('存款', '0')),
                        parse_num((prev.get(dept["label"]) or {}).get('存款', '0'))
                    ) for dept in DEPARTMENTS
                }
            }

        if w7:
            payload["周同比（今日 vs 7天前）"] = {
                "MT存款": pct_change(group_sum(mt_members, '存款', dept_raw), group_sum(mt_members, '存款', w7)),
                "RT存款": pct_change(group_sum(rt_members, '存款', dept_raw), group_sum(rt_members, '存款', w7)),
                "MT注册": pct_change(group_sum(mt_members, '注册', dept_raw), group_sum(mt_members, '注册', w7)),
            }

        month_hist = history.get('本月历史累计', {})
        last_month = history.get('上月同期累计', {})
        days_count = history.get('本月天数', yesterday.day)

        if month_hist or last_month:
            def month_total(field, group_members):
                return group_sum(group_members, field, month_hist) + group_sum(group_members, field, dept_raw)

            def last_total(field, group_members):
                return group_sum(group_members, field, last_month)

            payload["本月累计（含今日）"] = {
                "天数": f"本月共{days_count}天",
                "MT": {f: fmt_num(month_total(f, mt_members)) for f in SUMMARY_FIELDS},
                "RT": {f: fmt_num(month_total(f, rt_members)) for f in SUMMARY_FIELDS},
            }
            if last_month:
                payload["上月同期累计"] = {
                    "MT": {f: fmt_num(last_total(f, mt_members)) for f in SUMMARY_FIELDS},
                    "RT": {f: fmt_num(last_total(f, rt_members)) for f in SUMMARY_FIELDS},
                }
                payload["月同比（本月 vs 上月同期）"] = {
                    "MT存款": pct_change(month_total('存款', mt_members), last_total('存款', mt_members)),
                    "RT存款": pct_change(month_total('存款', rt_members), last_total('存款', rt_members)),
                    "MT注册": pct_change(month_total('注册', mt_members), last_total('注册', mt_members)),
                }

    return payload

# ─── Claude AI 分析 ────────────────────────────────────────────────────────────
def call_claude(payload: dict) -> str:
    if not CLAUDE_API_KEY:
        return ""

    data_json = json.dumps(payload, ensure_ascii=False, indent=2)

    system_prompt = """你是一位在线娱乐／体育综合平台的 COO 数据分析助理。
你每天收到八个部门（UED、RB、QM、QY、TQ、TH、LW、JX）的经营数据，以及历史对比数据。
MT组：QY、TH、LW、QM、RB；RT组：UED、JX、TQ。

分析规则：
1. 综合看活跃、存款、存提差、首存转化率（首存/注册）。
2. 首存转化率低于10%需提醒。
3. 存提差为负或远低于存款，代表高提现压力或套利风险。
4. 活跃上升但存提差未同步，可能是低价值流量或促销依赖。
5. 日环比变化超过±20%需特别标注，并分析原因。
6. 周同比下滑连续两周需预警。
7. 月同比数据体现月度经营趋势，是判断整体走势的最重要指标。
8. 如数据正常，输出正面总结，不强行找异常。
9. 输出简体中文，语气简洁专业，适合 Telegram 阅读，总字数控制在 700 字以内。"""

    user_prompt = f"""以下是今日经营数据与历史对比（JSON 格式）：

{data_json}

请按以下固定格式输出经营简报：

【每日经营重点】
（3-4 句话总结今日整体状况，点出亮点与隐患）

【趋势对比速览】
日环比：（MT/RT 存款、注册的日变化，标注显著变化部门）
周同比：（本日 vs 7天前，整体走势判断）
月累计：（本月 vs 上月同期，月度进展评估）

【部门异常提醒】
（最多3条，格式：▶ [部门] 异常指标 → 可能原因 → 建议）

【需要跟进事项】
（3-5 条可执行建议，直接给运营主管执行）

【一句话结论】
（COO 最需要关注的一件事）"""

    try:
        ai_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message   = ai_client.messages.create(
            model      = CLAUDE_MODEL,
            max_tokens = 1200,
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

    # 1. 加载历史数据
    print(f"[History] 加载历史数据...")
    history = load_history(yesterday)
    has_history = bool(history.get('前日数据') or history.get('7天前数据'))
    print(f"[History] 前日数据: {'有' if history.get('前日数据') else '无'}, "
          f"7天前: {'有' if history.get('7天前数据') else '无'}, "
          f"月累计: {'有' if history.get('本月历史累计') else '无'}")

    # 2. 抓取今日各部门数据
    dept_results = {}
    dept_raw     = {}
    blocks       = []

    for dept in DEPARTMENTS:
        result = fetch(dept, yesterday)
        text, data, raw = result if len(result) == 3 else (*result, None)
        dept_results[dept["label"]] = data
        dept_raw[dept["label"]]     = raw
        blocks.append(text)

    # 3. 保存今日数据到历史 Sheet
    save_to_history(yesterday, dept_raw)

    # 4. 构建原始数据日报
    mt_summary = build_summary("MT汇总", ["QY", "TH", "LW", "QM", "RB"], dept_results)
    rt_summary = build_summary("RT汇总", ["UED", "JX", "TQ"], dept_results)
    date_label = f"{yesterday.month}月{yesterday.day}日"

    raw_report = (
        f"📊 {date_label} 各部门原始数据\n\n"
        + "\n\n".join(blocks)
        + f"\n\n{'─'*20}\n\n"
        + mt_summary + "\n\n" + rt_summary
    )

    bot = telegram.Bot(token=TG_TOKEN)

    # 5. 尝试 Claude AI 分析
    ai_report = ""
    if CLAUDE_API_KEY:
        try:
            payload   = build_analysis_payload(yesterday, dept_raw, history)
            ai_report = call_claude(payload)
        except Exception as e:
            print(f"[AI Analysis Error] {e}")

    # 6. 发送消息：先发原始数据，再发 AI 分析
    await bot.send_message(chat_id=TG_CHAT_ID, text=raw_report)
    if ai_report:
        trend_note = "（含日/周/月趋势对比）" if has_history else "（历史数据积累中，趋势对比将在明日起生效）"
        ai_message = f"🤖 {date_label} COO 经营简报 {trend_note}\n\n{ai_report}"
        await bot.send_message(chat_id=TG_CHAT_ID, text=ai_message)
    elif CLAUDE_API_KEY:
        await bot.send_message(
            chat_id=TG_CHAT_ID,
            text="⚠️ AI 分析暂时不可用，已发送原始数据日报。"
        )

if __name__ == "__main__":
    asyncio.run(main())
