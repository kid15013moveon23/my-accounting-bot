"""COO document builder and optional Telegram sender.

Reads a validated JSON snapshot; does not scrape Teams or edit the existing 11:00 bot.
Usage: python coo_reports.py --kind morning --input snapshot.json --output reports/
       python coo_reports.py --kind weekly --input snapshot.json --output reports/ --send
Sending requires TG_TOKEN and TG_CHAT_ID environment variables.
"""
import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

KINDS = {"morning": "COO经营与执行晨报", "fees": "COO充值手续费日报", "weekly": "COO PD执行周报"}
FIELDS = ("优先级", "部门", "任务", "来源", "负责人", "期限", "状态", "进展", "下一步", "链接")
GROUPS = {"RT": ("UED", "TQ", "JXF"), "MT": ("QY", "LW", "龙8", "AE", "RB88")}


def load_snapshot(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("输入必须为 JSON 对象")
    if "as_of" not in raw:
        raise ValueError("缺少 as_of 日期，拒绝生成无法核实日期的报告")
    if not isinstance(raw.get("sources", []), list):
        raise ValueError("sources 必须是列表")
    return raw


def safe_text(value):
    return str(value if value is not None else "待确认").replace("\x00", "").strip() or "待确认"


def content_lines(kind, data):
    date = safe_text(data["as_of"])
    lines = [KINDS[kind], "数据截止：" + date, "数据来源：" + "、".join(map(safe_text, data.get("sources", [])))]
    if data.get("limitations"):
        lines.append("数据限制：" + safe_text(data["limitations"]))
    if kind == "morning":
        lines.append("【八产品两日业绩】")
        metrics = data.get("business", [])
        if not metrics:
            lines.append("数据尚未取得，未进行合计。")
        for m in metrics:
            lines.append(" / ".join(safe_text(m.get(k)) for k in ("产品", "前日", "昨日", "变动", "变动比例")))
        lines.append("【COO任务跟踪】")
        for task in data.get("tasks", []):
            lines.append("｜".join(safe_text(task.get(f)) for f in FIELDS))
        if not data.get("tasks"):
            lines.append("暂无可核实的任务快照。")
    elif kind == "fees":
        lines.append("【近七日充值与手续费】")
        daily = data.get("fees", [])
        if not daily:
            lines.append("手续费数据尚未取得，不能计算费率。")
        for d in daily:
            amount, fee = d.get("成功充值金额"), d.get("手续费")
            try:
                rate = float(fee) / float(amount) * 100 if float(amount) > 0 else None
            except (ValueError, TypeError):
                rate = None
            lines.append("｜".join((safe_text(d.get("日期")), "充值 " + safe_text(amount),
                                     "手续费 " + safe_text(fee), "费率 " + (f"{rate:.2f}%" if rate is not None else "不可计算"))))
    else:
        lines.append("【本周PD执行回顾】")
        for task in data.get("tasks", []):
            lines.append("｜".join(safe_text(task.get(f)) for f in FIELDS))
        if not data.get("tasks"):
            lines.append("暂无可核实的任务快照。")
    for x in data.get("insights", []):
        lines.append("关注：" + safe_text(x))
    return lines


def build_pdf(kind, data, output):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from xml.sax.saxutils import escape
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    style = ParagraphStyle("body", fontName="STSong-Light", fontSize=10, leading=17, textColor=colors.HexColor("#203047"), spaceAfter=8, wordWrap="CJK")
    heading = ParagraphStyle("title", parent=style, fontSize=18, leading=24, spaceAfter=18)
    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=38, rightMargin=38, topMargin=42, bottomMargin=42)
    lines = content_lines(kind, data)
    story = [Paragraph(escape(lines[0]), heading), Spacer(1, 4)]
    story.extend(Paragraph(escape(line), style) for line in lines[1:])
    doc.build(story)


def build_ppt(kind, data, output):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    lines = content_lines(kind, data)
    title = prs.slides.add_slide(prs.slide_layouts[0])
    title.shapes.title.text = lines[0]
    title.placeholders[1].text = "数据截止：" + safe_text(data["as_of"])
    # Fixed amount of text per slide; no invisible overflow from one giant textbox.
    per_slide = 10
    for index in range(1, len(lines), per_slide):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = f"{KINDS[kind]}｜{(index - 1) // per_slide + 1}"
        tf = slide.placeholders[1].text_frame
        tf.clear()
        for i, line in enumerate(lines[index:index + per_slide]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line[:270]
            p.font.size = Pt(15)
    prs.save(str(output))


async def send_file(path, kind, date):
    token = os.environ["TG_TOKEN"]
    chat = os.environ["TG_CHAT_ID"]
    import telegram
    bot = telegram.Bot(token=token)
    async with bot:
        with path.open("rb") as f:
            await bot.send_document(chat_id=chat, document=f, filename=path.name,
                                    caption=f"{KINDS[kind]}｜{date}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=sorted(KINDS), required=True)
    parser.add_argument("--input", required=True, help="由授权的上游程序提供的 JSON 快照")
    parser.add_argument("--output", default="reports")
    parser.add_argument("--send", action="store_true", help="显式允许发送到TG群")
    args = parser.parse_args()
    data = load_snapshot(args.input)
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    date = "".join(c for c in safe_text(data["as_of"]) if c.isdigit() or c == "-")
    suffix = "pptx" if args.kind == "weekly" else "pdf"
    path = outdir / f"COO_{args.kind}_{date}.{suffix}"
    if args.kind == "weekly":
        build_ppt(args.kind, data, path)
    else:
        build_pdf(args.kind, data, path)
    print("Generated:", path)
    if args.send:
        asyncio.run(send_file(path, args.kind, data["as_of"]))


if __name__ == "__main__":
    main()
