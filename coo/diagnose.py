import os,json,base64,zlib,hashlib
import requests
from test_send import EXPECTED_HASH

def main():
    try:
        value=os.environ.get('COO_TEST_PDF_ZLIB_B64','')
        raw=zlib.decompress(base64.b64decode(value,validate=True))
        print(json.dumps({'pdf_present':bool(value),'pdf_hash_matches':hashlib.sha256(raw).hexdigest()==EXPECTED_HASH,'pdf_magic_matches':raw.startswith(b'%PDF-')}))
    except Exception as e:
        print(json.dumps({'pdf_check_error_type':type(e).__name__}))
    token=os.environ.get('TG_TOKEN','').strip()
    chat=os.environ.get('TG_CHAT_ID','').strip()
    print(json.dumps({'token_present':bool(token),'chat_present':bool(chat)}))
    for endpoint,data in [('getMe',{}),('getChat',{'chat_id':chat}),('getWebhookInfo',{})]:
        try:
            r=requests.post('https://api.telegram.org/bot'+token+'/'+endpoint,data=data,timeout=30)
            d=r.json(); result=d.get('result',{})
            safe={'endpoint':endpoint,'http_status':r.status_code,'ok':d.get('ok'),'error_code':d.get('error_code')}
            if endpoint=='getMe': safe['bot_username']=result.get('username')
            if endpoint=='getChat': safe.update(title=result.get('title'),type=result.get('type'),title_matches=result.get('title')=='MMTTDAY')
            if endpoint=='getWebhookInfo': safe['webhook_configured']=bool(result.get('url'))
            print(json.dumps(safe,ensure_ascii=False))
        except Exception as e: print(json.dumps({'endpoint':endpoint,'exception_type':type(e).__name__}))

if __name__=='__main__': main()
