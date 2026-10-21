import unittest,tempfile
from unittest.mock import Mock
from pathlib import Path
from send_images import send_images

class PhotoTests(unittest.TestCase):
    def test_album_uses_photo_media_and_verifies_all_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[Path(tmp)/'1.jpg',Path(tmp)/'2.jpg']
            for p in paths: p.write_bytes(b'jpeg-test')
            chat,resp,session=Mock(),Mock(),Mock()
            chat.json.return_value={'ok':True,'result':{'id':-1,'title':'MMTTDAY💰'}}
            resp.json.return_value={'ok':True,'result':[{'chat':{'id':-1},'message_id':i,'photo':[{}]} for i in (10,11)]}
            session.post.side_effect=[chat,resp]
            result=send_images(paths,session,'token','-1','test')
            self.assertEqual(result['message_ids'],[10,11])
            self.assertTrue(session.post.call_args.args[0].endswith('/sendMediaGroup'))
            self.assertIn('"type": "photo"',session.post.call_args.kwargs['data']['media'])

    def test_wrong_group_does_not_send(self):
        session=Mock()
        session.post.return_value.json.return_value={'ok':True,'result':{'id':-1,'title':'other'}}
        with self.assertRaises(RuntimeError): send_images([Path('test.jpg')],session,'token','-1','test')
        self.assertEqual(session.post.call_count,1)

    def test_timeout_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'1.jpg';p.write_bytes(b'jpeg')
            chat,session=Mock(),Mock()
            chat.json.return_value={'ok':True,'result':{'id':-1,'title':'MMTTDAY💰'}}
            session.post.side_effect=[chat,TimeoutError()]
            with self.assertRaises(TimeoutError): send_images([p],session,'token','-1','test')
            self.assertEqual(session.post.call_count,2)

if __name__=='__main__':unittest.main()
