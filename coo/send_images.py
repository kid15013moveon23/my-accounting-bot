"""Inline-photo transport, isolated from legacy production workflows."""
from contextlib import ExitStack
import hashlib
import json


def send_images(paths, session, token, chat_id, caption):
    if not 1 <= len(paths) <= 10:
        raise ValueError('Telegram supports one photo or an album of 2-10')
    base='https://api.telegram.org/bot'+token.strip()
    chat=session.post(base+'/getChat',data={'chat_id':chat_id},timeout=30)
    chat.raise_for_status()
    d=chat.json()
    if not d.get('ok') or d['result'].get('title')!='MMTTDAY💰':
        raise RuntimeError('Destination mismatch; no photos sent')
    verified_id=d['result']['id']
    with ExitStack() as stack:
        files={}
        for i,path in enumerate(paths):
            files['photo'+str(i)]=(path.name,stack.enter_context(path.open('rb')),'image/jpeg')
        if len(paths)==1:
            method='sendPhoto'
            files={'photo':files['photo0']}
            data={'chat_id':verified_id,'caption':caption[:1024]}
        else:
            method='sendMediaGroup'
            media=[{'type':'photo','media':'attach://photo'+str(i)} for i in range(len(paths))]
            media[0]['caption']=caption[:1024]
            data={'chat_id':verified_id,'media':json.dumps(media,ensure_ascii=False)}
        # No blind retry: a timeout may occur after Telegram has accepted the album.
        response=session.post(base+'/'+method,data=data,files=files,timeout=120)
        response.raise_for_status()
        payload=response.json()
    if not payload.get('ok'):
        raise RuntimeError('Telegram rejected photos')
    messages=payload['result'] if isinstance(payload['result'],list) else [payload['result']]
    if len(messages)!=len(paths) or any(m.get('chat',{}).get('id')!=verified_id or not m.get('photo') or not m.get('message_id') for m in messages):
        raise RuntimeError('Photo receipt invalid; inspect before retrying')
    return {'status':'telegram_photos_accepted','message_ids':[m['message_id'] for m in messages],
            'count':len(paths),'sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]}
