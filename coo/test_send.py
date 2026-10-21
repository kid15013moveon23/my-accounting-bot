"""Send the previously generated private report once; no production imports."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zlib
from transport import send_document

EXPECTED_HASH = 'a411143f149d5ccf50631e279da5b446c54955a44e6919a0dc2b0e3893c3ee22'


def main():
    import requests
    required = ('TG_TOKEN', 'TG_CHAT_ID', 'COO_TEST_PDF_ZLIB_B64')
    if any(not os.environ.get(k, '').strip() for k in required):
        raise RuntimeError('Required private test configuration is missing')
    pdf = zlib.decompress(base64.b64decode(os.environ['COO_TEST_PDF_ZLIB_B64'], validate=True))
    if not pdf.startswith(b'%PDF-') or hashlib.sha256(pdf).hexdigest() != EXPECTED_HASH:
        raise RuntimeError('Test PDF integrity check failed')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'COO_2026-10-21_7of8_TEST.pdf'
        path.write_bytes(pdf)
        receipt = send_document(path, requests.Session(), os.environ['TG_TOKEN'].strip(), os.environ['TG_CHAT_ID'].strip())
    # No document contents, bot token, file ID, or raw chat ID in public logs/artifacts.
    safe = {k: receipt[k] for k in ('status', 'message_id', 'sha256', 'verified_at')}
    print(json.dumps(safe))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write('### COO PDF test receipt\n\nDestination verified: **MMTTDAY**\n\n')
            summary.write('```json\n' + json.dumps(safe, indent=2) + '\n```\n')
            summary.write('Telegram accepted the existing 7/8-product report. This is not a fresh full eight-product report or proof of human reading.\n')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('COO test failed. Inspect delivery before retrying; a timeout may follow an accepted send.') from None
