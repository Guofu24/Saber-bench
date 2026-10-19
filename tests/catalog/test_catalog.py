import unittest, subprocess, json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
class CatalogTests(unittest.TestCase):
 def test_integrity(self):
  p=subprocess.run([sys.executable,str(ROOT/'scripts/validate_catalog.py')],cwd=ROOT,text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
 def test_example_is_in_catalog(self):
  rows=json.loads((ROOT/'catalog/subtasks.json').read_text(encoding='utf8'))
  m={x['id']:x for x in rows}
  self.assertEqual(m['T1112.001']['environment'],'file')
  self.assertEqual(m['T1389.003']['environment'],'vm')
  self.assertEqual(m['T1109.003']['environment'],'vm')
  self.assertTrue(any('service_alive' in x for x in m['T1109.003']['score_items_source']))
 def test_no_claim_of_ready(self):
  rows=json.loads((ROOT/'catalog/subtasks.json').read_text(encoding='utf8'))
  self.assertTrue(all(r['score_implementation_status']=='UNIMPLEMENTED_UNREVIEWED' for r in rows))
if __name__=='__main__':unittest.main()
