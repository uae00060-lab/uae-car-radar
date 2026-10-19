import json,os,sys,unittest
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import store
class Store(unittest.TestCase):
 def setUp(self):store._salts.clear()
 def test_new_files_reuse_the_opened_salt_with_fresh_ivs(self):
  first=json.loads(store.encrypt_bytes(b'user','k'))
  store._salts.clear();store.decrypt_bytes(json.dumps(first),'k')
  second=json.loads(store.encrypt_bytes(b'engine','k'))
  self.assertEqual(second['salt'],first['salt']);self.assertNotEqual(second['iv'],first['iv'])
  self.assertEqual(store.decrypt_bytes(json.dumps(second),'k'),b'engine')
 def test_wrong_passphrase_never_records_a_salt(self):
  text=store.encrypt_bytes(b'x','k');store._salts.clear()
  with self.assertRaises(store.BadPassphrase):store.decrypt_bytes(text,'wrong')
  self.assertNotIn('wrong',store._salts)
 def test_rekey_moves_an_old_file_onto_the_shared_salt_once(self):
  import tempfile
  path=os.path.join(tempfile.mkdtemp(),'r.pdf.enc')
  open(path,'w').write(store.encrypt_bytes(b'pdf','k'))
  store._salts.clear();store.decrypt_bytes(store.encrypt_bytes(b'user','k'),'k')
  shared=store.shared_salt('k');self.assertNotEqual(json.load(open(path))['salt'],shared)
  self.assertTrue(store.rekey(path,'k'));self.assertEqual(json.load(open(path))['salt'],shared)
  self.assertEqual(store.decrypt_bytes(open(path).read(),'k'),b'pdf');self.assertFalse(store.rekey(path,'k'))
