# COO inline highlight images

User decision 2026-10-21: replace default PDF/PPT deliveries for all three report types with mobile-readable inline photos. Do not send image files as documents.

| UTC+8 schedule | Image contents |
| --- | --- |
| Daily 09:30 | 1 performance card + 1 management/decision card |
| Daily 17:00 | 1 fee trend card + optional exception/action card |
| Friday 17:00 | 2-3 PD execution highlights cards: completed, late, blocked, owner/deadline, decisions and next-week priorities |

Prefer 1080px width, readable large text, restrained layout, source/date/cutoff/completeness notes. Put original source URLs in accompanying text. Split dense content rather than shrinking it. Only report verified source facts; never infer missing products or claim unaccepted work is done.

## Verified image delivery

Run https://github.com/kid15013moveon23/my-accounting-bot/actions/runs/39586231517 successfully called Telegram sendMediaGroup with two photo items for verified MMTTDAY💰. Telegram returned photo message IDs 761 and 762 at 2026-10-21 18:40 UTC+8. Ten unit tests passed.

Test cards summarize the previously generated report. They explicitly disclose 7/8 products, QY missing, 23:00 snapshots and no fresh retrieval. The private card payload was stored only in a temporary encrypted secret, removed after testing. Automatic test triggers were retired. No source data, image bytes or credentials were committed publicly.

The existing ChatGPT task COO 重点图片报告 was updated in place to these formats; its two daily time slots and Friday extra report were preserved. No duplicate schedule was created. Production main, legacy 11:00 report, /chart, /update and Worker were not modified.

## Remaining deployment boundary

This verifies inline-photo transport, not a complete unattended Teams-to-Telegram deployment. The GitHub runner still needs runtime Teams access/source mapping and report generation before a full automatic production schedule can be claimed. The existing ChatGPT task must clearly report any unavailable delivery route rather than claim delivery.
