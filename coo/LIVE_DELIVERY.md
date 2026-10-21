# COO live image delivery

The COO scheduler uses the user's existing connected Teams app to read sources and prepare source-grounded highlight-card JSON. It encrypts each report locally to coo/recipient.json, then appends only ciphertext to this branch's inbox. The branch-only GitHub workflow decrypts on the runner using the existing TG_TOKEN, renders Chinese image cards, verifies destination MMTTDAY💰, sends inline Telegram photos, and records message IDs.

Production main and legacy 11:00 daily, /chart, /update and Cloudflare Worker are unchanged. No extra Teams credentials or report plaintext are stored in this public repository. The sender never receives the bot secret. The recipient public key is derived through a separate cryptographic domain; rotation of TG_TOKEN requires refreshing recipient.json via the bootstrap workflow before reports can be decrypted again.

## Schedule

The existing COO automation is enabled for daily 09:30 and 17:00 in Asia/Singapore (UTC+8). Morning generates operating and management cards; afternoon generates fee cards; Friday afternoon additionally generates PD execution cards. These are three report outputs handled within one task because the account's five active automation slots are already in use. No unrelated automation was disabled.

Expected first scheduled execution after setup: 2026-10-22 09:30 UTC+8. Friday PD starts 2026-10-23 17:00 UTC+8. The exact RRULE was evaluated locally and produces 09:30 / 17:00 daily, with no accidental 09:00 or 17:30 executions.

## Data and quality

Eight product channel/team mappings and the core COO management chat were verified read-only during setup. Replies must be read with parent-message context or include_replies=true: a reply incorrectly fetched as a root message can return 404 even when the source is available. QY now reads successfully with its actual team/channel pairing. The scheduler preserves original business dates, full-day versus snapshot distinctions, RT/MT completeness, and bounded Retry-After handling. Partial data is labeled; missing data is never estimated.

## Send-once controls

Use one deterministic report ID per type and local day: YYYY-MM-DD-morning, YYYY-MM-DD-fees or YYYY-MM-DD-pd. Create exactly one encrypted inbox file per commit. Check for an existing path before creating. Do not overwrite or create alternate IDs to bypass duplicate protection.

A delivery ledger artifact is written as attempted before the send and updated to accepted only after all photo message receipts are verified. Ledger presence prevents automatic replay of either accepted or uncertain attempts. Failed/ambiguous requests require inspection before a manual resend. Artifact retention is 90 days. Source plaintext, raw chat ID, Telegram file IDs and bot token are never emitted in logs.

## Verified tests

Fourteen encryption and transport unit tests passed on GitHub. Fresh Teams-source end-to-end test run 39587590378 succeeded and returned Telegram photo message ID 763. Ledger artifact coo-delivery-75639869299ddbfe1815eaa552a6aa57 was created. Test data explicitly identifies the available business date and missing reporting window.

The native automation's first manual execution is being checked separately; an enabled schedule or a run request is not itself proof of report delivery.
