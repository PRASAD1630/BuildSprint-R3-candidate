#!/usr/bin/env python3
import argparse,json,sys
from workmate.engine import ingest,brief,ask,forget

def main():
 p=argparse.ArgumentParser(prog='assist'); sub=p.add_subparsers(dest='cmd',required=True)
 a=sub.add_parser('ingest'); a.add_argument('--day',type=int,required=True)
 b=sub.add_parser('brief'); b.add_argument('--person',required=True); b.add_argument('--date',required=True)
 c=sub.add_parser('ask'); c.add_argument('--person',required=True); c.add_argument('--at',required=True); c.add_argument('--ask',required=True)
 d=sub.add_parser('forget'); d.add_argument('--person',required=True); d.add_argument('--what',required=True)
 x=p.parse_args()
 try:
  if x.cmd=='ingest': result=ingest(x.day)
  elif x.cmd=='brief': result=brief(x.person,x.date)
  elif x.cmd=='ask': result=ask(x.person,x.at,x.ask)
  else: result=forget(x.person,x.what)
  print(json.dumps(result,ensure_ascii=False))
 except Exception as e:
  # Keep stdout machine-readable while sending diagnostics to stderr.
  print(json.dumps({'error':'internal_error'}),file=sys.stdout)
  print(f'[workmate] {type(e).__name__}: {e}',file=sys.stderr)
  sys.exit(1)
if __name__=='__main__': main()
