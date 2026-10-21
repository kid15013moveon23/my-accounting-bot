import os,json,zlib,base64,tempfile
from pathlib import Path
import requests
from render_cards import render_cards
from send_images import send_images

def main():
    payload=json.loads(zlib.decompress(base64.b64decode(os.environ['COO_TEST_CARDS_ZLIB_B64'],validate=True)))
    with tempfile.TemporaryDirectory() as tmp:
        paths=render_cards(payload,tmp)
        receipt=send_images(paths,requests.Session(),os.environ['TG_TOKEN'],os.environ['TG_CHAT_ID'].strip(),
            'COO 重点图片格式测试｜2026-10-21已有报告摘录，非重新取数。7/8产品，QY缺失；23:00快照，非完整日结。共2张，直接查看即可。')
    print(json.dumps(receipt))
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
        out.write('### COO inline-photo receipt\n\nDestination: MMTTDAY💰\n\n```json\n'+json.dumps(receipt,indent=2)+'\n```\n')

if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Image test failed; inspect destination and send outcome before retrying.') from None
