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

START_DATE = datetime(2026, 5, 1)
END_DATE   = datetime(2026, 6, 22)

SHANGHAI = pytz.timezone('Asia/Shanghai')
SCOPES   = ['https://www.googleapis.com/auth/spreadsheets']
creds    = Credentials.from_service_account_info(SA_JSON, scopes=SCOPES)
client   = gspread.authorize(creds)

DEPARTMENTS = [
    {"label":"UED","group":"RT","sheet_id":"1a7ZBESgUweasFGf2FfDx1TbMvb1onS-knTU7cx2I13g","worksheet":"每日明细","date_col":0,"direction":"top","columns":{"注册":25,"首存":26,"存款":3,"提款":4,"存提差":5,"活跃":18}},
    {"label":"RB","group":"MT","sheet_id":"1iErwKLMSsPEcnYravOzhMGuTiZBBUYedggr84UU8Ilo","worksheet":"每日数据","date_col":0,"direction":"bottom","columns":{"注册":1,"首存":2,"存款":8,"提款":11,"存提差":12}},
    {"label":"QM","group":"MT","sheet_id":"1drz_NT2aTiPHfvX-xOmJR72q-o9Mk9hucPGTfTfFLmI","worksheet":"每日数据","date_col":0,"direction":"bottom","columns":{"注册":1,"首存":2,"存款":8,"提款":11,"存提差":12}},
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
    current = START_DATE
    saved = skipped = no_data = 0

    while current <= END_DATE:
        date_str = current.strftime('%Y-%m-%d')

        if date_str in existing_dates:
            print(f"⏭  {date_str} 已存在")
            skipped += 1
            current += timedelta(days=1)
            continue

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
            try:
                hist_ws.append_rows(rows, value_input_option='USER_ENTERED')
                print(f"✅ {date_str} → {len(rows)} 部门")
                saved += 1
                time.sleep(2)
            except Exception as e:
                print(f"❌ {date_str} 写入失败: {e}")
                time.sleep(5)
        else:
            print(f"—  {date_str} 无数据")
            no_data += 1

        current += timedelta(days=1)

    print(f"\n=== 完成：写入{saved}天，跳过{skipped}天，无数据{no_data}天 ===")

if __name__ == "__main__":
    main()
