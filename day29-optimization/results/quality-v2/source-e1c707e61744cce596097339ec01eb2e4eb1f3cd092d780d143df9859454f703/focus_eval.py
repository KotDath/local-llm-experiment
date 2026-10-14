"""Paired live relevance filtering of saved real generations; never a full rerun."""
import argparse,copy,hashlib,json,time
from pathlib import Path
from agent import Agent
from common import ServiceError,append_jsonl,utc_now
ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ids',default='');p.add_argument('--follow',action='store_true');p.add_argument('--expected',type=int)
    args=p.parse_args()
    if args.output.exists():p.error('Choose a new output file')
    seen=set();core=hashlib.sha256(b''.join((ROOT/f).read_bytes() for f in ['agent.py','rag.py','model.py','grounding.py','index.py'])).hexdigest()
    snapshot=args.output.parent/('source-'+core);snapshot.mkdir(parents=True,exist_ok=True)
    for f in ['agent.py','rag.py','model.py','grounding.py','index.py']:(snapshot/f).write_bytes((ROOT/f).read_bytes())
    while True:
        rows=[json.loads(l) for l in args.input.read_text().splitlines() if l.strip()]
        for row in rows:
            key=(row['repeat'],row['id'])
            if key in seen or (args.ids and row['id'] not in args.ids.split(',')):continue
            a=Agent(profile=row['profile'],rag=True);trace=copy.deepcopy(row)
            trace['generation_source_sha256']=row['source_sha256'];trace['source_sha256']=core
            trace['paired_input_answer_sha256']=hashlib.sha256(row.get('text','').encode()).hexdigest()
            trace['evaluation_scope']='Paired actual focus call on saved base-agent generation; original upstream calls reused, not rerun.'
            start=time.monotonic()
            try:
                answer=a._focus_answer(row['question'],{k:row[k] for k in ['text','claims','sources','status','finish_reason']},trace)
                trace.update(answer);trace['ok']=True
            except ServiceError as exc:trace.update(ok=False,error=exc.code,detail=exc.detail)
            trace['focus_ms']=(time.monotonic()-start)*1000
            trace['total_ms']=row['total_ms']+trace['focus_ms']
            trace['usage']={k:sum(c['usage'].get(k,0) for c in trace['llm_calls']) for k in ['prompt_tokens','completion_tokens','total_tokens']}
            trace['answer_sha256']=hashlib.sha256(trace.get('text','').encode()).hexdigest()
            append_jsonl(args.output,trace);seen.add(key)
            print(row['repeat'],row['id'],trace.get('status',trace.get('error')),flush=True)
        if not args.follow or (args.expected and len(seen)>=args.expected):break
        time.sleep(10)


if __name__=='__main__':main()
