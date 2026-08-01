"""
历史数据回填脚本
将指定日期范围内的所有部门数据写入历史 Google Sheet
"""
import os, json, re, time
from datetime import datetime, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials

SA_JSON          = json.loads(os.environ['GSHEET_SA_JSON'])
HISTORY_SHEET_ID = os.environ['HISTORY_SHEET_ID']

def _parse_date(s, fallback):
    s = (s or '').strip()
    if not s:
        return fallback
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise SystemExit(f"❌ 日期格式错误: {s!r}（正确格式如 2026-07-23）")

# 日期由工作流输入决定；留空则用下面的默认值
START_DATE = _parse_date(os.environ.get('BACKFILL_START'), datetime(2026, 7, 23))
END_DATE   = _parse_date(os.environ.get('BACKFILL_END'), START_DATE)
if END_DATE < START_DATE:
    raise SystemExit(f"❌ 结束日期 {END_DATE.date()} 早于开始日期 {START_DATE.date()}")

SHANGHAI = pytz.timezone('Asia/Shanghai')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']
creds    = Credentials.from_service_account_info(SA_JSON, scopes=SCOPES)
client   = gspread.authorize(creds)

DEPARTMENTS = [
    {"label":"UED","group":"RT","sheet_id":"1a7ZBESgUweasFGf2FfDx1TbMvb1onS-knTU7cx2I13g","worksheet":"每日明细","date_col":0,"direction":"top","columns":{"注册":25,"首存":26,"存款":3,"提款":4,"存提差":5,"活跃":18}},
    {"label":"RB","group":"MT","sheet_id":"1iErwKLMSsPEcnYravOzhMGuTiZBBUYedggr84UU8Ilo","worksheet":"每日数据","date_col":0,"direction":"bottom","columns":{"注册":1,"首存":2,"存款":8,"提款":11,"存提差":12,"活跃":9}},
    {"label":"QM","group":"MT","sheet_id":"1drz_NT2aTiPHfvX-xOmJR72q-o9Mk9hucPGTfTfFLmI","worksheet":"每日数据","date_col":0,"direction":"bottom","columns":{"注册":1,"首存":2,"存款":8,"提款":11,"存提差":12,"活跃":9}},
    {"label":"QY","group":"MT","sheet_id":"1NMOTloCNN7lDpa2Wjtehcdx75UU7Rx7HAepXYv5SgB0","worksheet":"每日数据","date_col":0,"direction":"bottom","columns":{"注册":1,"首存":3,"存款":9,"提款":12,"存提差":13,"活跃":10}},
    {"label":"TQ","group":"RT","sheet_id":"1RbcFCX8a-vUwsRKcu2ONzu_IBx0gyUw4Kds7HXwfUNM","worksheet":"每日明细","date_col":0,"direction":"top","columns":{"注册":24,"首存":25,"存款":3,"提款":4,"存提差":5,"活跃":18}},
    {"label":"TH","group":"MT","sheet_id":"1JKgkLj_ltl5wwhB7u4Uy8DBgznKpys75kGdJZF9LBuQ","worksheet":"每日基础数据","date_col":0,"direction":"bottom","columns":{"注册":1,"首存":2,"存款":8,"提款":11,"存提差":12,"活跃":9}},
    {"label":"LW","group":"MT","sheet_id":"1BqU6DF7SReWGZSCeT0vtJH4RoVtc2qMMah5PR9ZF2AI","worksheet":"网站基本日数据","date_col":0,"direction":"bottom","columns":{"注册":1,"首存":2,"存款":8,"提款":9,"存提差":10,"活跃":11}},
    {"label":"JX","group":"RT","sheet_id":"1oCYfkGtDaGeGguS5XkpPjyvGZnzUfC_whVrGdZgbqMM","worksheet":"每日明细","date_col":0,"direction":"top","columns":{"注册":24,"首存":25,"存款":3,"提款":4,"存提差":5,"活跃":18}},
]

HISTORY_FIELDS = ["注册","首存","存款","提款","存提差","活跃"]

def is_summary(val):
    v = val.strip()
    if not v: return True
    if v in ("日均","合计","总计","平均","汇总","小计"): return True
    return not bool(re.search(r'\d', v))

def date_variants(d):
    m, day, y = d.month, d.day, d.year
    return [f"{m}/{day}",f"{m}-{day}",f"{m:02d}/{day:02d}",f"{m:02d}-{day:02d}",
            f"{m}月{day}日",f"{y}/{m}/{day}",f"{y}-{m}-{day}",
            f"{y}/{m:02d}/{day:02d}",f"{y}-{m:02d}-{day:02d}"]

def pick_worksheet(ss, ws_hint):
    for w in ss.worksheets():
        if ws_hint in w.title: return w
    for w in ss.worksheets():
        if "每日" in w.title: return w
    return ss.worksheets()[0]

def safe(row, col):
    try:
        v = row[col].strip()
        return v if v else "—"
    except IndexError:
        return "—"

def find_exact_row(all_data, direction, date_col, target_date):
    variants = date_variants(target_date)
    data_rows = all_data[1:]
    ordered = list(reversed(data_rows)) if direction == "bottom" else data_rows
    for row in ordered:
        if len(row) <= date_col: continue
        cell = row[date_col].strip()
        if is_summary(cell): continue
        if cell in variants: return row
        if any(var in cell for var in variants): return row
    return None

def main():
    print(f"=== 回填：{START_DATE.date()} ~ {END_DATE.date()} ===\n")

    hist_ss = client.open_by_key(HISTORY_SHEET_ID)
    hist_ws = hist_ss.worksheets()[0]
    all_hist = hist_ws.get_all_values()

    if not all_hist or not any(c.strip() for c in all_hist[0]):
        header = ['日期','部门','组别','注册','首存','存款','提款','存提差','活跃']
        hist_ws.update(range_name='A1', values=[header])
        all_hist = [header]
        print("✅ 初始化表头")

    existing_dates = {row[0] for row in all_hist[1:] if row and row[0]}
    print(f"已有 {len(existing_dates)} 个日期\n")

    print("📥 预加载各部门数据...")
    dept_all_data = {}
    for dept in DEPARTMENTS:
        try:
            ss = client.open_by_key(dept["sheet_id"])
            ws = pick_worksheet(ss, dept["worksheet"])
            dept_all_data[dept["label"]] = ws.get_all_values()
            print(f"  ✅ {dept['label']} ({len(dept_all_data[dept['label']])} 行)")
        except Exception as e:
            dept_all_data[dept["label"]] = []
            print(f"  ❌ {dept['label']}: {e}")
        time.sleep(1)

    print()
    target_dates = []
    current = START_DATE
    while current <= END_DATE:
        target_dates.append(current)
        current += timedelta(days=1)

    fresh_rows      = []     # 本次重新抓到的数据
    dates_with_data = set()  # 抓到数据的日期（这些日期的旧记录将被覆盖）
    no_data         = 0

    for current in target_dates:
        date_str = current.strftime('%Y-%m-%d')

        rows = []
        for dept in DEPARTMENTS:
            all_data = dept_all_data.get(dept["label"], [])
            if not all_data: continue
            row = find_exact_row(all_data, dept["direction"], dept["date_col"], current)
            if row:
                raw = {name: safe(row, col) for name, col in dept["columns"].items()}
                rows.append([date_str, dept['label'], dept['group'],
                    raw.get('注册',''), raw.get('首存',''), raw.get('存款',''),
                    raw.get('提款',''), raw.get('存提差',''), raw.get('活跃','')])

        if rows:
            old_n = sum(1 for r in all_hist[1:] if r and r[0] == date_str)
            tag = f"覆盖原有 {old_n} 行" if old_n else "新增"
            print(f"✅ {date_str} → {len(rows)} 部门（{tag}）")
            fresh_rows.extend(rows)
            dates_with_data.add(date_str)
        else:
            print(f"—  {date_str} 源表查无数据，保留原有记录")
            no_data += 1

    if not fresh_rows:
        print("\n=== 未抓到任何数据，历史表保持不变 ===")
        return

    # 重建整张表：剔除被覆盖日期的旧行，再接上新抓到的行
    header = all_hist[0]
    kept   = [r for r in all_hist[1:] if r and r[0] and r[0] not in dates_with_data]
    new_values = [header] + kept + fresh_rows

    # 安全阀：行数异常就中止，绝不把历史表写坏
    if len(new_values) < 1 + len(fresh_rows):
        raise SystemExit("❌ 重建后行数异常，已中止，历史表未改动")

    hist_ws.update(range_name='A1', values=new_values, value_input_option='USER_ENTERED')
    if len(all_hist) > len(new_values):
        hist_ws.batch_clear([f"A{len(new_values)+1}:I{len(all_hist)}"])

    print(f"\n=== 完成：重写 {len(dates_with_data)} 天 / {len(fresh_rows)} 行，"
          f"源表无数据 {no_data} 天，历史表现共 {len(new_values)-1} 行 ===")

if __name__ == "__main__":
    main()
