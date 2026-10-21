"""Branch-only encrypted report consumer. Never logs plaintext report content."""
import hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
import requests
from crypto_transport import recipient,unseal
from render_cards import render_cards
from send_images import send_images

def main():
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    before,after=event['before'],event['after']
    changed=subprocess.check_output(['git','diff','--name-only',before,after],text=True).splitlines()
    token=os.environ['TG_TOKEN'].strip()
    if '.coo/bootstrap' in changed:
        print('COO_PUBLIC_RECIPIENT='+json.dumps(recipient(token)))
    paths=[p for p in changed if p.startswith('inbox/') and p.endswith('.json')]
    if not paths:return
    if len(paths)!=1:raise ValueError('Commit exactly one report per launch')
    path=paths[0]
    if not re.fullmatch(r'inbox/\d{4}-\d{2}-\d{2}-(morning|fees|pd|test)(-[a-z0-9]+)?\.json',path):raise ValueError('Unexpected inbox filename')
    envelope=json.loads(Path(path).read_text())
    if envelope['report_id']!=Path(path).stem:raise ValueError('Report ID must match filename')
    payload=unseal(envelope,token)
    if payload.get('report_id')!=envelope['report_id']:raise ValueError('Payload ID mismatch')
    if payload.get('kind') not in ('morning','fees','pd','test'):raise ValueError('Unknown report kind')
    expected_id_day=Path(path).stem[:10]
    if not payload.get('date','').startswith(expected_id_day):raise ValueError('Report date mismatch')
    key=hashlib.sha256(envelope['report_id'].encode()).hexdigest()[:32]
    artifact_name='coo-delivery-'+key
    # A persistent attempted or accepted ledger prevents blind reruns of a send.
    headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json'}
    api='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/artifacts'
    response=requests.get(api,headers=headers,params={'name':artifact_name,'per_page':100},timeout=30)
    response.raise_for_status()
    if response.json().get('artifacts'):raise RuntimeError('Report already attempted; inspect existing delivery ledger before retrying')
    ledger_dir=Path(os.environ['RUNNER_TEMP'])/'coo-receipt';ledger_dir.mkdir(exist_ok=True)
    ledger=ledger_dir/'receipt.json'
    receipt={'report_id':envelope['report_id'],'status':'prepared','artifact_name':artifact_name}
    with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('ledger_name='+artifact_name+'\n')
    caption=payload.get('caption',payload['date']+' COO重点报告')
    if len(caption)>1024:raise ValueError('Caption exceeds Telegram limit')
    with tempfile.TemporaryDirectory() as tmp:
        images=render_cards(payload,tmp)
        receipt['status']='attempted_delivery_outcome_unknown'
        ledger.write_text(json.dumps(receipt))
        sent=send_images(images,requests.Session(),token,os.environ['TG_CHAT_ID'].strip(),caption)
        receipt.update(sent)
        ledger.write_text(json.dumps(receipt))
    print(json.dumps(receipt))
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
        out.write('### COO inline delivery receipt\n\nVerified destination: MMTTDAY💰\n\n```json\n'+json.dumps(receipt,indent=2)+'\n```\n')

if __name__=='__main__':
    try:main()
    except Exception as e:
        # Token-bearing HTTP exception strings must never enter public logs.
        print('COO delivery stopped; exception type: '+type(e).__name__)
        raise SystemExit(1) from None
