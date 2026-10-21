import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import deliver

class DeliveryGuardTests(unittest.TestCase):
    def test_existing_attempt_ledger_blocks_network_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'inbox').mkdir()
            report_id='2026-10-21-fees'
            (root/'inbox'/f'{report_id}.json').write_text(json.dumps({'report_id':report_id}))
            event=root/'event.json';event.write_text(json.dumps({'before':'old','after':'new'}))
            response=Mock();response.json.return_value={'artifacts':[{'name':'existing-ledger'}]}
            cwd=os.getcwd()
            try:
                os.chdir(tmp)
                with patch.dict(os.environ,{'GITHUB_EVENT_PATH':str(event),'TG_TOKEN':'fake','GITHUB_TOKEN':'fake','GITHUB_REPOSITORY':'owner/repo'}),patch.object(deliver.subprocess,'check_output',return_value=f'inbox/{report_id}.json\n'),patch.object(deliver,'unseal',return_value={'report_id':report_id,'kind':'fees','date':'2026-10-21'}),patch.object(deliver.requests,'get',return_value=response),patch.object(deliver,'send_images') as send:
                    with self.assertRaises(RuntimeError):deliver.main()
                    send.assert_not_called()
            finally:os.chdir(cwd)

    def test_multiple_reports_in_commit_rejected_before_decryption(self):
        with tempfile.TemporaryDirectory() as tmp:
            event=Path(tmp)/'event.json';event.write_text(json.dumps({'before':'old','after':'new'}))
            with patch.dict(os.environ,{'GITHUB_EVENT_PATH':str(event),'TG_TOKEN':'fake'}),patch.object(deliver.subprocess,'check_output',return_value='inbox/2026-10-21-fees.json\ninbox/2026-10-21-pd.json\n'),patch.object(deliver,'unseal') as decrypt:
                with self.assertRaises(ValueError):deliver.main()
                decrypt.assert_not_called()

if __name__=='__main__':unittest.main()
