# COO Reports – isolated beta

This folder adds PDF/PPT rendering to the existing Telegram bot repository, **without changing send_report.py, 11:00 scheduling, Worker commands, or accounting_bot.py**.

## Generate (no Telegram messages are sent)
Install `reportlab`, `python-pptx`, and the existing `python-telegram-bot==20.7` separately from the production environment.

```bash
python coo_reports.py --kind morning --input sample_coo_snapshot.json
python coo_reports.py --kind fees --input sample_coo_snapshot.json
python coo_reports.py --kind weekly --input sample_coo_snapshot.json
```

Pass `--send` **only after approval**, and set `TG_TOKEN` and `TG_CHAT_ID` as protected secrets. Existing TG group can be reused if approved.

## Data contract
The snapshot is supplied by a **separately authorized** Microsoft Teams + Google Sheets exporter. The ChatGPT Teams connector does not automatically grant GitHub Actions read permissions. No exporter, recurring schedule or automatic delivery is deployed by this branch.

Expected top-level fields: `as_of` (required, ISO date); `sources` (list); `limitations` (string); `business` (list of 产品/前日/昨日/变动/变动比例); `fees` (list of 日期/成功充值金额/手续费); `tasks` (list with 优先级/部门/任务/来源/负责人/期限/状态/进展/下一步/链接); `insights` (list).

Source hierarchy: 「星期八」 = COO and all PD managers' management group; 「MT管理群」 = management escalations. Distinguish COO directives, PD promises, and unapproved discussions. RT = UED + TQ + JXF; MT = QY + LW + 龙8 + AE + RB88. **Existing production report uses different aliases (JX/RB/TH/QM); verify them before changing its mapping.**

Never commit Telegram tokens, Google service-account JSON, or Teams permissions. Only publish aggregates and authorized work-status data to the group.
