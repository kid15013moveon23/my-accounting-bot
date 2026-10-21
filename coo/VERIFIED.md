# COO PDF transport verified

Verified on 2026-10-21 at 17:59:08 UTC+8.

- Run: https://github.com/kid15013moveon23/my-accounting-bot/actions/runs/39581150359
- Job: 119158793729; all steps succeeded.
- Telegram destination title verified by getChat: MMTTDAY💰.
- Bot confirmed by getMe: MMTTDAY_bot.
- Telegram sendDocument result: accepted, message_id 760.
- Original PDF SHA-256: a411143f149d5ccf50631e279da5b446c54955a44e6919a0dc2b0e3893c3ee22.
- Sent the existing 2026-10-21 7/8-product report; no data were regenerated or invented. Caption discloses QY missing and 23:00 snapshots.
- The first failed test stopped at exact title comparison (expected MMTTDAY, actual MMTTDAY💰); it did not call sendDocument. A read-only diagnostic established the cause before the successful send.
- Seven transport tests passed on both the local runtime and GitHub runner.
- Temporary PDF secret removed after the test; automatic branch push trigger retired. No PDF contents, token, raw chat ID or Telegram file ID were published.

## Production preserved

Main remains e4ff772d850207ed8d18753ba974654d340d347c. No Worker deployment or production workflow file was changed.
Uploaded Worker was inspected locally with mocked network tests: /report → daily_report.yml, /chart 60 → chart.yml, /update 2026-10-20 → backfill.yml; other groups ignored; scheduled daily dispatch retained.
Worker scheduled() does not distinguish cron expressions. Adding COO cron triggers to the existing Worker would trigger the legacy daily/monthly report. Use an independent scheduler instead.

## Not deployed

09:30 Teams eight-product + management PDF, 17:00 fee PDF, and Friday 17:00 PD execution PPTX are not deployed to GitHub. The repository has no configured runtime Teams authentication or source mappings/report generators. Connected ChatGPT Teams access was checked successfully but is not automatically available as Graph credentials inside GitHub Actions.
An existing ChatGPT task named COO AI 秘书双时段报告 is enabled, but its prompt explicitly prohibits automatic Telegram sends and it is not a verified PDF/PPT-to-Telegram deployment. It was not silently changed or duplicated.

No claim of human reading or full scheduled deployment is made from sendDocument acceptance.
