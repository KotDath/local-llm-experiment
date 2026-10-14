"""Isolated real runs; only id/question enter Agent, rubric never enters prompts."""
import argparse
import hashlib
import json
from pathlib import Path
from agent import Agent
from common import ServiceError, append_jsonl, utc_now
ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--questions',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--ids',default='')
    p.add_argument('--repeat',type=int,default=1)
    p.add_argument('--rerank',action='store_true')
    p.add_argument('--profile',default='optimized',choices=['baseline','optimized'])
    args=p.parse_args()
    if args.output.exists():p.error('Output already exists; choose a new file to preserve run provenance')
    questions=[json.loads(line) for line in args.questions.read_text().splitlines() if line.strip()]
    if args.ids:questions=[q for q in questions if q['id'] in args.ids.split(',')]
    source=hashlib.sha256(b''.join((ROOT/f).read_bytes() for f in ['agent.py','rag.py','model.py','grounding.py','index.py'])).hexdigest()
    snapshot=args.output.parent/('source-'+source)
    snapshot.mkdir(parents=True,exist_ok=True)
    for filename in ['agent.py','rag.py','model.py','grounding.py','index.py','configs/retrieval.json','configs/baseline.json','configs/optimized.json']:
        target=snapshot/filename;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/filename).read_bytes())
    props=Agent().model.info()
    runtime={'model_file':Path(props['model_path']).name,'build':props['build_info'],
             'context_per_slot':props['default_generation_settings']['n_ctx'],'slots':props['total_slots']}
    for repeat in range(args.repeat):
        for q in questions:
            agent=Agent(profile=args.profile,rag=True,rerank=args.rerank)
            row={'id':q['id'],'question':q['question'],'repeat':repeat,'utc':utc_now(),
                 'runtime_model':runtime,'source_sha256':source,'questions_sha256':hashlib.sha256(args.questions.read_bytes()).hexdigest()}
            complete=agent.model.complete
            def measured(messages,profile=None):
                result=complete(messages,profile)
                append_jsonl(args.output.with_suffix('.calls.jsonl'),{'id':q['id'],'repeat':repeat,'utc':utc_now(),'usage':result['usage'],
                    'counted_prompt_tokens':result.get('counted_prompt_tokens'),'generation_ms':result.get('generation_ms'),
                    'max_tokens':(profile or {}).get('max_tokens'),'finish_reason':result['finish_reason']})
                return result
            agent.model.complete=measured
            try:row.update(agent.ask(q['question']));row['ok']=True
            except ServiceError as exc:
                row.update((exc.detail or {}).get('failure_trace',{}));row.update(ok=False,error=exc.code,detail=exc.detail)
            row['answer_sha256']=hashlib.sha256(row.get('text','').encode()).hexdigest()
            append_jsonl(args.output,row)
            print(repeat,q['id'],row.get('status',row.get('error')),round(row.get('total_ms',0)),flush=True)


if __name__=='__main__':main()
