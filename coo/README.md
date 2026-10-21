# COO isolated preflight

Status: NOT deployed; no Telegram test send has occurred. Production files are unchanged.

Required schedules (Asia/Singapore, UTC+8):
- Daily 09:30: Teams eight-product performance and management-work PDF (UTC 01:30).
- Daily 17:00: fee PDF (UTC 09:00).
- Friday 17:00: PD execution weekly PPTX (UTC Friday 09:00).

Keep existing 11:00 daily report, /chart and /update. Do not import send_report.py: it initializes Google Sheets and production credentials. COO must use Teams only; missing sources must be disclosed, never estimated.

## Verified 2026-10-21

Main commit inspected: e4ff772d850207ed8d18753ba974654d340d347c.
Daily run 39536137004 / job 119013112772 succeeded at 11:00 UTC+8. Logs record history saved for eight departments and two trend charts sent. No COO document receipt exists in those logs.
Existing daily_report.yml, chart.yml and update_dept.yml use workflow_dispatch. No Worker source or wrangler configuration exists in the inspected repository tree. Worker scheduling and command routing remain unverified.

## Available preflight

Run `python -m unittest discover -s coo -v`. Four local retry tests passed. Teams requests support Retry-After seconds and HTTP dates, with one initial attempt and at most five retries per target. Invalid Retry-After fails closed. Pagination/source collection is not implemented yet.

A trusted runner with an existing local report can run:
`python coo/transport.py /private/path/report.pdf --receipt /private/path/receipt.json`
It requires existing TG_TOKEN and TG_CHAT_ID environment variables, verifies the destination title MMTTDAY through getChat, sends the document once, and saves Telegram chat/message/file IDs plus SHA-256. Network timeouts must be investigated before another send to avoid duplicates. Receipt means Telegram accepted the document, not human read confirmation. Never commit reports, receipts, tokens or signed download URLs to this public repository.

## Remaining before deployment

1. Obtain authorized access to tg-daily-bot Worker source/config/logs; verify existing cron and /chart, /update routes.
2. Use a trusted execution environment with existing repository secrets or authorized Worker access to send the existing private COO PDF; current GitHub connector has no workflow dispatch operation and local runtime has no Telegram credentials.
3. Verify receipt and delivery in MMTTDAY before enabling schedules.
4. Configure a deployable Teams authentication method and all eight product, management, fee and PD source mappings. Interactive ChatGPT Teams access does not provide runtime Graph credentials to Actions.
5. Implement and validate all report generators and missing-data handling, then enable isolated schedules. This branch does not claim that these collectors/generators exist.
