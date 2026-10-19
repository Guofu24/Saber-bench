#!/usr/bin/env python3
"""Print exact source task/subtask metadata; does not execute exercises."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def main():
 if len(sys.argv)!=2:
  print('Usage: python scripts/show_subtask.py T1112.001');return 2
 id=sys.argv[1]
 all=json.loads((root/'catalog/subtasks.json').read_text(encoding='utf8'))
 rec=next((x for x in all if x['id']==id),None)
 if rec is None: print(f'Unknown benchmark subtask: {id}',file=sys.stderr);return 1
 for field in ('id','nice_id','service','task_name_vi','environment','source_existing_count_raw','scenario_source','input_descriptions_source','output_descriptions_source','score_items_source','score_aggregate_source','note_source'):
  print(f'{field}: {json.dumps(rec.get(field),ensure_ascii=False)}')
 print(f'Claude task card: tasks/subtasks/{id}.md')
 return 0
if __name__=='__main__': raise SystemExit(main())
