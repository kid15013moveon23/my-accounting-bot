"""Isolated COO transport; never imports the production accounting bot."""
import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


def retry_delay(value, now=None):
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        try:
            when = parsedate_to_datetime(value)
            return max(0.0, (when - (now or datetime.now(timezone.utc))).total_seconds())
        except (ValueError, TypeError, OverflowError):
            raise RuntimeError('429 has no valid Retry-After; stop rather than retry early') from None


def teams_get(session, url, sleep=time.sleep):
    """One initial request plus at most five retries per URL/page."""
    for retry in range(6):
        response = session.get(url, timeout=60)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        if retry == 5:
            raise RuntimeError('Teams target exhausted five retries')
        sleep(retry_delay(response.headers.get('Retry-After')))


def send_document(path, session, token, chat_id, expected_title='MMTTDAY'):
    """No automatic send retry: a timeout can mean Telegram already accepted it."""
    path = Path(path)
    if path.suffix.lower() not in {'.pdf', '.pptx'} or not path.is_file():
        raise ValueError('Expected an existing PDF or PPTX')
    base = 'https://api.telegram.org/bot' + token
    chat = session.post(base + '/getChat', data={'chat_id': chat_id}, timeout=30)
    chat.raise_for_status()
    payload = chat.json()
    if not payload.get('ok') or payload['result'].get('title') != expected_title:
        raise RuntimeError('Telegram destination verification failed')
    verified_id = payload['result']['id']
    with path.open('rb') as document:
        response = session.post(base + '/sendDocument', data={
            'chat_id': verified_id, 'caption': 'COO 独立流程发送测试｜2026-10-21 已有报告：7/8产品，QY缺失、23:00快照。非新生成完整日报。PDF内“未发送”描述为生成时状态。'
        }, files={'document': (path.name, document)}, timeout=120)
    response.raise_for_status()
    result = response.json()
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected document')
    message = result['result']
    if message['chat']['id'] != verified_id or not message.get('document') or not message.get('message_id'):
        raise RuntimeError('Telegram document receipt invalid')
    return {'status': 'telegram_accepted', 'chat_id': verified_id,
            'message_id': message['message_id'],
            'file_id': message['document']['file_id'],
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'verified_at': datetime.now(timezone.utc).isoformat()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('document')
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    import requests
    try:
        receipt = send_document(args.document, requests.Session(), os.environ['TG_TOKEN'], os.environ['TG_CHAT_ID'])
        Path(args.receipt).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print('Telegram accepted document; receipt saved. This does not prove a human read it.')
    except Exception:
        # HTTP exception strings may contain the bot token in the URL.
        raise SystemExit('COO test failed; do not auto-retry a potentially accepted send.') from None
