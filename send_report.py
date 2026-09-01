"""
每日数据汇报机器人 - AI 分析版（含历史趋势对比）
GitHub Actions 每天 11:00 上海时间自动发送
- 数据存入历史 Sheet（日/周/月对比）
- Claude API 做 COO 级趋势分析
- 失败时自动降级为原始数据日报
"""
import os, json, re, asyncio, time
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

# 单平台更新模式：只抓一个部门、只更新历史表该行、不跑 AI
ONLY_DEPT        = os.environ.get('ONLY_DEPT', '').strip().upper()
ONLY_DATE        = os.environ.get('ONLY_DATE', '').strip()

# 月度对比模式：'YYYY-MM' 指定要总结的月份；留空则在「昨天=1号」时自动启用
MONTHLY_REVIEW   = os.environ.get('MONTHLY_REVIEW', '').strip()

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
        "date_no_year": True,   # 日期只显示「8/1」不含年份，且按月倒序堆叠，须用原始日期比对
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
            "活跃": 9,   # 存款人数（内部口径：活跃人数=存款人数）
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
            "活跃": 9,   # 存款人数（内部口径：活跃人数=存款人数）
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

# 日报显示名（内部字段名保持不变，仅影响输出文字）
DISPLAY_NAMES  = {"活跃": "活跃人数"}

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

def serial_to_date(v):
    """Google Sheets 日期序列号 → date；非日期返回 None"""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return (datetime(1899, 12, 30) + timedelta(days=int(n))).date()

def load_real_dates(ws, date_col, n_rows):
    """读取日期列的未格式化原始值，得到带年份的真实日期 {行索引: date}"""
    try:
        letter = chr(ord('A') + date_col)
        raw = ws.get(f"{letter}1:{letter}{n_rows}",
                     value_render_option='UNFORMATTED_VALUE')
        out = {}
        for i, cell in enumerate(raw):
            d = serial_to_date(cell[0] if cell else None)
            if d:
                out[i] = d
        return out or None
    except Exception as e:
        print(f"[RealDate] 原始日期读取失败，回退文本匹配: {e}")
        return None

def find_data_row(all_data, direction, date_col, target_date, real_dates=None):
    variants  = date_variants(target_date)
    data_rows = all_data[1:]
    ordered   = list(reversed(data_rows)) if direction == "bottom" else data_rows

    def valid(row):
        if len(row) <= date_col: return False
        return not is_summary(row[date_col].strip())

    # 有带年份的真实日期时：精确比对年月日，避免跨年误匹配
    # 匹配不到宁可返回无数据，也不静默取到别的年份
    if real_dates:
        target = target_date.date() if hasattr(target_date, 'date') else target_date
        idxs = list(range(1, len(all_data)))
        if direction == "bottom":
            idxs.reverse()
        for i in idxs:
            row = all_data[i]
            if not valid(row): continue
            if real_dates.get(i) == target:
                return row, row[date_col].strip(), True
        return None, None, False

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
def fetch(dept, yesterday, max_retries=3):
    label = dept["label"]
    for attempt in range(max_retries):
        try:
            ss       = client.open_by_key(dept["sheet_id"])
            ws       = pick_worksheet(ss, dept["worksheet"])
            all_data = ws.get_all_values()
            if not all_data:
                return f"【{label}】⚠️ 空表", None, None

            real_dates = None
            if dept.get("date_no_year"):
                real_dates = load_real_dates(ws, dept["date_col"], len(all_data))

            row, date_str, exact = find_data_row(
                all_data, dept["direction"], dept["date_col"], yesterday, real_dates
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
                lines.append(f"  {DISPLAY_NAMES.get(name, name)}: {val}")
                if name in SUMMARY_FIELDS:
                    data[name] = parse_num(val)
                raw[name] = val

            return "\n".join(lines), data, raw

        except Exception as e:
            err_str = str(e)
            # 503 / 429 / 500 是临时错误，自动重试
            if attempt < max_retries - 1 and any(code in err_str for code in ('503', '429', '500')):
                wait = 15 * (2 ** attempt)   # 15s → 30s → 60s
                print(f"[{label}] 临时错误，{wait}s 后重试 ({attempt+1}/{max_retries}): {e}")
                time.sleep(wait)
            else:
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

# ─── Monthly Summary ──────────────────────────────────────────────────────────
def build_monthly_summary(label: str, members: list, results: dict, month_hist: dict, days_count: int = 1) -> str:
    """结合历史月累计 + 今日数据，生成本月汇总（含日均）"""
    totals  = {f: 0.0 for f in SUMMARY_FIELDS}
    missing = []
    for m in members:
        today = results.get(m)
        if today is None:
            missing.append(m)
        else:
            for f in SUMMARY_FIELDS:
                totals[f] += today.get(f, 0.0)
        hist = month_hist.get(m) or {}
        for f in SUMMARY_FIELDS:
            totals[f] += parse_num(hist.get(f, '0'))

    days = days_count if days_count and days_count > 0 else 1
    lines = [f"【{label}】({'、'.join(members)})"]
    for f in SUMMARY_FIELDS:
        lines.append(f"  {f}: {fmt_num(totals[f])}（日均 {fmt_num(totals[f] / days)}）")
    if missing:
        lines.append(f"  ⚠️ 缺失: {' '.join(missing)}")
    return "\n".join(lines)

# ─── History: Save ────────────────────────────────────────────────────────────
def save_to_history(yesterday: datetime, dept_raw: dict):
    """保存当日数据到历史 Google Sheet"""
    if not HISTORY_SHEET_ID:
        print("[History] 未设置 HISTORY_SHEET_ID，跳过保存")
        return
    try:
        ss = client.open_by_key(HISTORY_SHEET_ID)
        ws = ss.worksheets()[0]
        all_data = ws.get_all_values()

        # 初始化表头
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

def save_one_dept(target: datetime, dept: dict, raw: dict) -> str:
    """只覆盖历史表中 (日期, 部门) 这一行，不动其他部门"""
    if not HISTORY_SHEET_ID:
        return "未设置 HISTORY_SHEET_ID，跳过"
    try:
        ws       = client.open_by_key(HISTORY_SHEET_ID).worksheets()[0]
        all_hist = ws.get_all_values()
        date_str = target.strftime('%Y-%m-%d')
        raw      = raw or {}
        new_row  = [date_str, dept['label'], dept['group'],
                    raw.get('注册', ''), raw.get('首存', ''), raw.get('存款', ''),
                    raw.get('提款', ''), raw.get('存提差', ''), raw.get('活跃', '')]

        for i in range(1, len(all_hist)):
            r = all_hist[i]
            if len(r) >= 2 and r[0] == date_str and r[1] == dept['label']:
                ws.update(range_name=f'A{i+1}:I{i+1}', values=[new_row],
                          value_input_option='USER_ENTERED')
                return f"已覆盖历史表第 {i+1} 行"

        ws.append_row(new_row, value_input_option='USER_ENTERED')
        return "历史表原无该记录，已新增"
    except Exception as e:
        return f"历史表写入失败: {e}"

def history_snapshot(target: datetime) -> dict:
    """从历史表读回：目标日各部门数据 + 本月1日~目标日累计（含目标日）"""
    out = {'day': {}, 'month': {}, 'days': 0}
    if not HISTORY_SHEET_ID:
        return out
    try:
        ws    = client.open_by_key(HISTORY_SHEET_ID).worksheets()[0]
        rows  = ws.get_all_values()[1:]
        d_str = target.strftime('%Y-%m-%d')
        m_str = target.replace(day=1).strftime('%Y-%m-%d')
        dates = set()
        for r in rows:
            if len(r) < 8 or not r[0]:
                continue
            date_s, label = r[0].strip(), r[1].strip()
            if not label:
                continue
            vals = {'注册': r[3], '首存': r[4], '存款': r[5], '提款': r[6], '存提差': r[7]}
            if date_s == d_str:
                out['day'][label] = {f: parse_num(vals[f]) for f in SUMMARY_FIELDS}
            if m_str <= date_s <= d_str:
                dates.add(date_s)
                acc = out['month'].setdefault(label, {f: 0.0 for f in SUMMARY_FIELDS})
                for f in SUMMARY_FIELDS:
                    acc[f] += parse_num(vals[f])
        out['days'] = len(dates)
        return out
    except Exception as e:
        print(f"[Snapshot] 历史表读取失败: {e}")
        return out

def month_bounds(ym: str):
    """'2026-08' → (2026-08-01, 2026-08-31)"""
    y, m  = map(int, ym.split('-'))
    first = datetime(y, m, 1)
    nxt   = datetime(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
    return first, nxt - timedelta(days=1)

def prev_month(ym: str) -> str:
    y, m = map(int, ym.split('-'))
    return f"{y-1}-12" if m == 1 else f"{y}-{m-1:02d}"

def history_range_totals(start: datetime, end: datetime) -> dict:
    """历史表中 [start, end] 区间各部门累计与实际天数"""
    out = {'dept': {}, 'days': 0}
    if not HISTORY_SHEET_ID:
        return out
    try:
        ws   = client.open_by_key(HISTORY_SHEET_ID).worksheets()[0]
        rows = ws.get_all_values()[1:]
        s, e = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
        dates = set()
        for r in rows:
            if len(r) < 8 or not r[0]:
                continue
            ds, label = r[0].strip(), r[1].strip()
            if not label or not (s <= ds <= e):
                continue
            dates.add(ds)
            acc  = out['dept'].setdefault(label, {f: 0.0 for f in SUMMARY_FIELDS})
            vals = {'注册': r[3], '首存': r[4], '存款': r[5], '提款': r[6], '存提差': r[7]}
            for f in SUMMARY_FIELDS:
                acc[f] += parse_num(vals[f])
        out['days'] = len(dates)
        return out
    except Exception as e:
        print(f"[RangeTotals] 历史表读取失败: {e}")
        return out

def group_sum_of(members: list, per_dept: dict, field: str) -> float:
    return sum((per_dept.get(m) or {}).get(field, 0.0) for m in members)

def group_block(title: str, members: list, per_dept: dict, days: int = 0) -> str:
    """按组汇总；days>0 时附带日均"""
    totals = {f: 0.0 for f in SUMMARY_FIELDS}
    for m in members:
        d = per_dept.get(m) or {}
        for f in SUMMARY_FIELDS:
            totals[f] += d.get(f, 0.0)
    lines = [f"【{title}】({'、'.join(members)})"]
    for f in SUMMARY_FIELDS:
        if days > 0:
            lines.append(f"  {f}: {fmt_num(totals[f])}（日均 {fmt_num(totals[f] / days)}）")
        else:
            lines.append(f"  {f}: {fmt_num(totals[f])}")
    return "\n".join(lines)

# ─── History: Load & Compare ──────────────────────────────────────────────────
def load_history(yesterday: datetime) -> dict:
    """读取历史数据，返回对比所需结构（不含今日）"""
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

        # 月对比（历史部分，不含今日）
        month_start     = yesterday.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_elapsed    = yesterday.day - 1   # 本月1日到昨日的天数（不含昨日，因今日才抓）
        last_month_end  = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        last_month_same  = last_month_start + timedelta(days=days_elapsed - 1)

        history_month = period_totals(month_start, day_before) if days_elapsed > 0 else {}
        last_month    = period_totals(last_month_start, last_month_same) if days_elapsed > 0 else {}

        return {
            '前日数据':     day_data(day_before),
            '7天前数据':    day_data(week_ago),
            '本月历史累计': history_month,   # 本月 1 日到前日（不含今日）
            '上月同期累计': last_month,
            '本月天数':     yesterday.day,    # 含今日
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

    # 今日各部门
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

    # 历史对比
    if history:
        prev = history.get('前日数据', {})
        w7   = history.get('7天前数据', {})

        if prev:
            payload["前日汇总"] = {
                "MT": {f: fmt_num(group_sum(mt_members, f, prev)) for f in SUMMARY_FIELDS},
                "RT": {f: fmt_num(group_sum(rt_members, f, prev)) for f in SUMMARY_FIELDS},
            }
            payload["日环比（今日 vs 前日）"] = {
                "MT存款": pct_change(
                    group_sum(mt_members, '存款', dept_raw),
                    group_sum(mt_members, '存款', prev)),
                "RT存款": pct_change(
                    group_sum(rt_members, '存款', dept_raw),
                    group_sum(rt_members, '存款', prev)),
                "MT注册": pct_change(
                    group_sum(mt_members, '注册', dept_raw),
                    group_sum(mt_members, '注册', prev)),
                "RT注册": pct_change(
                    group_sum(rt_members, '注册', dept_raw),
                    group_sum(rt_members, '注册', prev)),
                "各部门存款": {
                    dept["label"]: pct_change(
                        parse_num((dept_raw.get(dept["label"]) or {}).get('存款', '0')),
                        parse_num((prev.get(dept["label"]) or {}).get('存款', '0'))
                    ) for dept in DEPARTMENTS
                }
            }

        if w7:
            payload["周同比（今日 vs 7天前）"] = {
                "MT存款": pct_change(
                    group_sum(mt_members, '存款', dept_raw),
                    group_sum(mt_members, '存款', w7)),
                "RT存款": pct_change(
                    group_sum(rt_members, '存款', dept_raw),
                    group_sum(rt_members, '存款', w7)),
                "MT注册": pct_change(
                    group_sum(mt_members, '注册', dept_raw),
                    group_sum(mt_members, '注册', w7)),
            }

        # 月累计对比（含今日）
        month_hist = history.get('本月历史累计', {})
        last_month = history.get('上月同期累计', {})
        days_count = history.get('本月天数', yesterday.day)

        if month_hist or last_month:
            # 今月累计 = 历史累计 + 今日
            def month_total(field, group_members):
                hist_sum = group_sum(group_members, field, month_hist)
                today_sum = group_sum(group_members, field, dept_raw)
                return hist_sum + today_sum

            def last_total(field, group_members):
                return group_sum(group_members, field, last_month)

            payload["本月累计（含今日）"] = {
                "天数": f"本月共{days_count}天",
                "MT": {f: fmt_num(month_total(f, mt_members)) for f in SUMMARY_FIELDS},
                "RT": {f: fmt_num(month_total(f, rt_members)) for f in SUMMARY_FIELDS},
            }
            def daily_avg(field, group_members):
                return month_total(field, group_members) / max(days_count, 1)

            payload["本月日均"] = {
                "说明": f"本月累计 ÷ {days_count} 天",
                "MT": {f: fmt_num(daily_avg(f, mt_members)) for f in SUMMARY_FIELDS},
                "RT": {f: fmt_num(daily_avg(f, rt_members)) for f in SUMMARY_FIELDS},
            }
            payload["日均环比（今日 vs 本月日均）"] = {
                "MT": {f: pct_change(group_sum(mt_members, f, dept_raw), daily_avg(f, mt_members)) for f in SUMMARY_FIELDS},
                "RT": {f: pct_change(group_sum(rt_members, f, dept_raw), daily_avg(f, rt_members)) for f in SUMMARY_FIELDS},
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
8. 日均环比（今日 vs 本月日均）是衡量今日表现的基准线：高于日均说明今日好于本月平均水平，低于则相反；偏离超过±15%需重点说明原因。
9. 如数据正常，输出正面总结，不强行找异常。
10. 输出简体中文，语气简洁专业，适合 Telegram 阅读，总字数控制在 700 字以内。"""

    user_prompt = f"""以下是今日经营数据与历史对比（JSON 格式）：

{data_json}

请按以下固定格式输出经营简报：

【每日经营重点】
（3-4 句话总结今日整体状况，点出亮点与隐患）

【趋势对比速览】
日环比：（MT/RT 存款、注册的日变化，标注显著变化部门）
日均环比：（今日 vs 本月日均，判断今日处于本月什么水平）
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

def call_claude_month(payload: dict) -> str:
    if not CLAUDE_API_KEY:
        return ""
    data_json = json.dumps(payload, ensure_ascii=False, indent=2)

    system_prompt = """你是一位在线娱乐／体育综合平台的 COO 数据分析助理，现在做的是**月度经营复盘**，不是日报。
八个部门：MT组 QY、TH、LW、QM、RB；RT组 UED、JX、TQ。

分析要求：
1. 以「上月 vs 上上月」的整月数据做对比，关注月度趋势而非单日波动。
2. 重点看：存款规模、存提差（留存利润）、注册与首存转化、各部门贡献占比变化。
3. 明确指出哪些部门是本月增长引擎、哪些在拖后腿，用数字说话。
4. 首存转化率（首存/注册）低于10%要点名。
5. 存提差占存款比例下降，代表利润率恶化，须预警。
6. 注意两个月天数可能不同（如31天 vs 30天），比较总量时要提示日均口径更公平。
7. 给出下个月可执行的经营重点，不要空泛。
8. 输出简体中文，专业简洁，适合 Telegram 阅读，总字数控制在 900 字以内。"""

    user_prompt = f"""以下是两个整月的经营数据对比（JSON）：

{data_json}

请按以下格式输出月度复盘：

【月度总览】
（3-4 句话概括上月整体表现与最关键的变化）

【核心指标环比】
（存款、存提差、注册、首存的月环比，标注幅度与方向）

【部门贡献分析】
（哪些部门增长、哪些下滑，各自对大盘的影响，点名具体数字）

【风险提示】
（最多3条，格式：▶ [部门/指标] 问题 → 影响 → 建议）

【下月经营重点】
（3-5 条可执行建议）

【一句话结论】"""

    try:
        ai_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message   = ai_client.messages.create(
            model      = CLAUDE_MODEL,
            max_tokens = 1600,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"[Claude Monthly Error] {e}")
        return ""

async def send_monthly_review(bot, cur_ym: str):
    """发送整月对比：数据块 + 月度 AI 复盘"""
    prv_ym = prev_month(cur_ym)
    c1, c2 = month_bounds(cur_ym)
    p1, p2 = month_bounds(prv_ym)
    cur = history_range_totals(SHANGHAI.localize(c1), SHANGHAI.localize(c2))
    prv = history_range_totals(SHANGHAI.localize(p1), SHANGHAI.localize(p2))

    if not cur['dept']:
        await bot.send_message(chat_id=TG_CHAT_ID,
                               text=f"⚠️ 历史表中查无 {cur_ym} 的数据，月度复盘跳过。")
        return

    MT = ["QY", "TH", "LW", "QM", "RB"]
    RT = ["UED", "JX", "TQ"]

    lines = [f"📈 {cur_ym} 月度总结（对比 {prv_ym}）", "",
             f"统计天数：{cur_ym} {cur['days']}天　|　{prv_ym} {prv['days']}天", "",
             group_block(f"MT {cur_ym}", MT, cur['dept'], cur['days']), "",
             group_block(f"RT {cur_ym}", RT, cur['dept'], cur['days']),
             "", "─" * 20, "",
             group_block(f"MT {prv_ym}", MT, prv['dept'], prv['days']), "",
             group_block(f"RT {prv_ym}", RT, prv['dept'], prv['days'])]
    await bot.send_message(chat_id=TG_CHAT_ID, text="\n".join(lines))

    def grp(members, src_):
        return {f: fmt_num(group_sum_of(members, src_, f)) for f in SUMMARY_FIELDS}

    def mom(members, field):
        return pct_change(group_sum_of(members, cur['dept'], field),
                          group_sum_of(members, prv['dept'], field))

    payload = {
        "本月": cur_ym, "上月": prv_ym,
        "天数": {cur_ym: cur['days'], prv_ym: prv['days']},
        f"MT合计_{cur_ym}": grp(MT, cur['dept']),
        f"MT合计_{prv_ym}": grp(MT, prv['dept']),
        f"RT合计_{cur_ym}": grp(RT, cur['dept']),
        f"RT合计_{prv_ym}": grp(RT, prv['dept']),
        "月环比": {
            "MT存款": mom(MT, '存款'), "MT存提差": mom(MT, '存提差'), "MT注册": mom(MT, '注册'),
            "RT存款": mom(RT, '存款'), "RT存提差": mom(RT, '存提差'), "RT注册": mom(RT, '注册'),
        },
        f"各部门_{cur_ym}": {k: {f: fmt_num(v[f]) for f in SUMMARY_FIELDS}
                            for k, v in cur['dept'].items()},
        f"各部门_{prv_ym}": {k: {f: fmt_num(v[f]) for f in SUMMARY_FIELDS}
                            for k, v in prv['dept'].items()},
    }

    ai = call_claude_month(payload)
    if ai:
        await bot.send_message(chat_id=TG_CHAT_ID,
                               text=f"🤖 {cur_ym} 月度经营复盘（vs {prv_ym}）\n\n{ai}")
    elif CLAUDE_API_KEY:
        await bot.send_message(chat_id=TG_CHAT_ID, text="⚠️ 月度 AI 复盘暂时不可用，已发送对比数据。")

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    yesterday = datetime.now(SHANGHAI) - timedelta(days=1)

    # ── 单平台更新模式：只抓一个部门，不做汇总与 AI 分析 ──
    if ONLY_DEPT:
        if ONLY_DATE:
            try:
                yesterday = SHANGHAI.localize(datetime.strptime(ONLY_DATE, '%Y-%m-%d'))
            except ValueError:
                print(f"[单平台] 日期格式错误: {ONLY_DATE}")
                raise SystemExit(1)

        dept = next((d for d in DEPARTMENTS if d["label"].upper() == ONLY_DEPT), None)
        if not dept:
            names = " / ".join(d["label"] for d in DEPARTMENTS)
            print(f"[单平台] 未知平台 {ONLY_DEPT}，可用：{names}")
            raise SystemExit(1)

        date_label = f"{yesterday.month}月{yesterday.day}日"
        text, data, raw = fetch(dept, yesterday)
        note = save_one_dept(yesterday, dept, raw)
        print(f"[单平台] {dept['label']} {date_label} → {note}")

        MT = ["QY", "TH", "LW", "QM", "RB"]
        RT = ["UED", "JX", "TQ"]
        snap  = history_snapshot(yesterday)
        parts = [f"🔄 {date_label} {dept['label']} 数据已重新抓取", "", text]

        if snap['day']:
            parts += ["", "─" * 20, "",
                      group_block("MT汇总", MT, snap['day']), "",
                      group_block("RT汇总", RT, snap['day'])]
        if snap['month']:
            parts += ["", "─" * 20, "",
                      f"📅 本月累计（1日－{yesterday.day}日，共{snap['days']}天）", "",
                      group_block("MT本月汇总", MT, snap['month'], snap['days']), "",
                      group_block("RT本月汇总", RT, snap['month'], snap['days'])]

        bot = telegram.Bot(token=TG_TOKEN)
        await bot.send_message(chat_id=TG_CHAT_ID, text="\n".join(parts))
        return

    # 1. 加载历史数据（今日之前）
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

    # 4. 构建原始数据日报（备用）
    mt_summary = build_summary("MT汇总", ["QY", "TH", "LW", "QM", "RB"], dept_results)
    rt_summary = build_summary("RT汇总", ["UED", "JX", "TQ"], dept_results)
    date_label = f"{yesterday.month}月{yesterday.day}日"

    # 本月累计汇总（历史月累计 + 今日）
    month_hist  = history.get('本月历史累计', {})
    days_count  = history.get('本月天数', yesterday.day)
    mt_month    = build_monthly_summary("MT本月汇总", ["QY", "TH", "LW", "QM", "RB"], dept_results, month_hist, days_count)
    rt_month    = build_monthly_summary("RT本月汇总", ["UED", "JX", "TQ"], dept_results, month_hist, days_count)

    raw_report = (
        f"📊 {date_label} 各部门原始数据\n\n"
        + "\n\n".join(blocks)
        + f"\n\n{'─'*20}\n\n"
        + mt_summary + "\n\n" + rt_summary
        + f"\n\n{'─'*20}\n\n"
        + f"📅 本月累计（1日－{yesterday.day}日，共{days_count}天）\n\n"
        + mt_month + "\n\n" + rt_month
    )

    bot = telegram.Bot(token=TG_TOKEN)

    # 5. 判断走「月度复盘」还是「每日分析」
    #    昨天 = 某月1号 → 上个月刚结束，改出月度对比
    review_ym = MONTHLY_REVIEW
    if not review_ym and yesterday.day == 1:
        review_ym = (yesterday.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')

    if review_ym:
        await bot.send_message(chat_id=TG_CHAT_ID, text=raw_report)
        await send_monthly_review(bot, review_ym)
        return

    # 6. 每日 AI 分析
    ai_report = ""
    if CLAUDE_API_KEY:
        try:
            payload   = build_analysis_payload(yesterday, dept_raw, history)
            ai_report = call_claude(payload)
        except Exception as e:
            print(f"[AI Analysis Error] {e}")

    # 7. 发送消息（先发原始数据，再发 AI 分析）
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
