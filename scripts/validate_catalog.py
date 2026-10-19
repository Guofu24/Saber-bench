#!/usr/bin/env python3
"""Validate the frozen 55/175/40 benchmark catalog. Standard library only."""
from pathlib import Path
import json, re, hashlib, collections, sys
ROOT=Path(__file__).resolve().parents[1]
def load(name): return json.loads((ROOT/'catalog'/name).read_text(encoding='utf-8'))
def main():
 t=load('tasks.json'); ss=load('subtasks.json'); hv=load('artifacts.json'); meta=load('metadata.json')
 ids={x['nice_id'] for x in t}; sids={x['id'] for x in ss}; hids={x['id'] for x in hv}
 problems=[]
 def must(cond,message):
  if not cond:problems.append(message)
 must(len(t)==55 and len(ids)==55,'tasks expected 55 unique')
 must(len(ss)==175 and len(sids)==175,'subtasks expected 175 unique')
 must(len(hv)==40 and len(hids)==40,'HV types expected 40 unique')
 must(len(t)+len(ss)>0,'not empty')
 must(collections.Counter(x['environment'] for x in ss)=={'file':110,'soc':47,'vm':18},'wrong env counts')
 must(collections.Counter(x['service'] for x in t)=={'MON':16,'CNT':5,'HUNT':13,'IR':21},'wrong svc task counts')
 must(collections.Counter(x['service'] for x in ss)=={'MON':58,'CNT':15,'HUNT':39,'IR':63},'wrong svc subtask counts')
 source=ROOT/meta['source_file']
 must(source.exists(),'frozen source missing')
 if source.exists(): must(hashlib.sha256(source.read_bytes()).hexdigest()==meta['source_sha256'],'source checksum mismatch')
 for i in ss:
  must(bool(re.fullmatch(r'T\d{4}\.\d{3}',i['id'])),'bad subtask id: '+i['id'])
  must(i['nice_id'] in ids,'missing NICE task: '+i['id'])
  must(i['id'].split('.')[0]==i['nice_id'],'subtask NICE prefix mismatch: '+i['id'])
  must(set(i['input_hv_ids']+i['output_hv_ids']).issubset(hids),'unknown HV refs: '+i['id'])
  must(bool(i['score_items_source']) and bool(i['score_aggregate_source']),'missing score: '+i['id'])
  must(i['environment'] in {'file','soc','vm'},'bad environment: '+i['id'])
  must(i['score_implementation_status']=='UNIMPLEMENTED_UNREVIEWED','catalog falsely claims implementation: '+i['id'])
  must((ROOT/'tasks'/'subtasks'/(i['id']+'.md')).exists(),'missing card: '+i['id'])
 for x in t:
  must(set(x['subtask_ids']).issubset(sids),'task has orphan subtask: '+x['nice_id'])
  must(len(x['subtask_ids'])==len(set(x['subtask_ids'])),'task duplicate subtask: '+x['nice_id'])
  for code in x['subtask_ids']:
   match=next(z for z in ss if z['id']==code)
   must(x['service']==match['service'],'service mismatch: '+code)
 must(sum(i['output_is_unmaterialized'] for i in ss)==106,'output placeholder count changed')
 if problems:
  for p in problems: print('FAIL',p,file=sys.stderr)
  return 1
 print('PASS: 55 NICE tasks / 175 subtasks / 40 HV artifact types')
 print('Services: MON 58; CNT 15; HUNT 39; IR 63 subtasks')
 print('Modes: file 110; soc 47; vm 18')
 print('Catalog is SPECIFIED; validator does NOT prove fixtures or grader implementations exist.')
 return 0
if __name__=='__main__': raise SystemExit(main())
