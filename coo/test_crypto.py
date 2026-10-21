import copy,unittest
from cryptography.exceptions import InvalidTag
from crypto_transport import recipient,seal,unseal

class CryptoTests(unittest.TestCase):
    def test_round_trip_and_no_plaintext(self):
        p={'report_id':'2026-10-21-fees','cards':[{'title':'私密金额123456'}]}
        e=seal(p,recipient('fake-token'),'2026-10-21-fees')
        self.assertEqual(unseal(e,'fake-token'),p)
        self.assertNotIn('私密',str(e))
    def test_unique_randomized_envelopes(self):
        r=recipient('fake-token')
        self.assertNotEqual(seal({},r,'id')['ciphertext'],seal({},r,'id')['ciphertext'])
    def test_wrong_recipient_fails(self):
        e=seal({},recipient('first'),'id')
        with self.assertRaises(ValueError):unseal(e,'second')
    def test_metadata_tamper_rejected(self):
        e=seal({},recipient('first'),'id');e['report_id']='changed'
        with self.assertRaises(InvalidTag):unseal(e,'first')

if __name__=='__main__':unittest.main()
