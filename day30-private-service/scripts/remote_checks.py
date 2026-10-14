"""Probe HTTP(S) locally or on VPS; SSH is only remote administration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_env

ROOT = Path(__file__).resolve().parents[1]


def run(script):
    env = os.environ.copy()
    env['SSHPASS'] = env['SERVER_PASSWORD']
    result = subprocess.run(['sshpass', '-e', 'ssh', '-p', env.get('SERVER_PORT', '22'),
                             '-o', 'StrictHostKeyChecking=yes', '-o', 'PreferredAuthentications=password',
                             '-o', 'PubkeyAuthentication=no', env['SERVER_LOGIN'] + '@' + env['HOST_IP'],
                             'python3 -'], input=script, capture_output=True, text=True, env=env, timeout=3600)
    if result.returncode:
        log = ROOT / 'runtime/remote_check_error.log'
        log.parent.mkdir(exist_ok=True)
        log.write_text(result.stderr)
        log.chmod(0o600)
        raise RuntimeError('Remote check failed: exit ' + str(result.returncode) + '; details in private runtime/remote_check_error.log')
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['network', 'load', 'limits', 'overflow', 'final'])
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--api-url', default='http://127.0.0.1:8781')
    parser.add_argument('--client', choices=['vps', 'local'], default='vps')
    parser.add_argument('--output-prefix', default='remote')
    args = parser.parse_args()
    load_env(args.env_file)
    load_env(ROOT / '.env')
    # Preserve the exact registered credential bytes; the API uses the same CSV.
    tokens = [value for value in os.environ.get('API_TEST_TOKENS', '').split(',') if value]
    needed = {'load': 4, 'limits': 2, 'overflow': 5}.get(args.mode, 0)
    if len(tokens) < needed:
        parser.error('Set at least ' + str(needed) + ' comma-separated API_TEST_TOKENS in private .env, then restart the PC API')
    if not os.environ.get('API_TOKEN') or os.environ['API_TOKEN'] == 'REPLACE_WITH_RANDOM_TOKEN':
        parser.error('Set a real API_TOKEN in private .env before running remote checks')
    base = '''import urllib.request,urllib.error,json,time,concurrent.futures
url=API_URL_PLACEHOLDER
def call(path,token,data=None):
 req=urllib.request.Request(url+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=1800) as r:return {'status':r.status,'body':json.load(r),'retry_after':r.headers.get('Retry-After')}
 except urllib.error.HTTPError as e:
  raw=e.read()
  try:body=json.loads(raw)
  except ValueError:body={'error':'non_json_http_error','response_text':raw.decode('utf-8',errors='replace')[:1000]}
  return {'status':e.code,'body':body,'retry_after':e.headers.get('Retry-After')}
'''
    base = base.replace('API_URL_PLACEHOLDER', repr(args.api_url.rstrip('/')))
    if args.mode == 'final':
        script = base + 'token=' + repr(os.environ['API_TOKEN']) + '''
health=call('/health',token)
created=call('/sessions',token,{})
sid=created['body'].get('session_id')
questions=['Как MemGPT организует основную и внешнюю память?',
           'Как он продолжает выполнение нескольких функций без ответа пользователю?',
           'Чем этот механизм отличается от забывания в MemoryBank?',
           'Какой измеренный p95 ответа MemGPT на Galaxy A54 в этих статьях?']
rag=[]
if sid:
 for question in questions:
  rag.append(call('/chat',token,{'session_id':sid,'message':question,'rag':True,'rerank':False,'web':False}))
plain_created=call('/sessions',token,{})
plain_sid=plain_created['body'].get('session_id')
plain=[]
reset=None
if plain_sid:
 for question in ['Запомни в этом разговоре: кодовое слово Липа-7319.','Какое кодовое слово я назвал?']:
  plain.append(call('/chat',token,{'session_id':plain_sid,'message':question}))
 reset=call('/sessions/reset',token,{'session_id':plain_sid})
 plain.append(call('/chat',token,{'session_id':plain_sid,'message':'Какое кодовое слово я назвал?'}))
print(json.dumps({'client':'VPS','stage':'final service after measured model selection',
                 'health':health,'rag_session_create':created,'rag_turns':rag,
                 'plain_session_create':plain_created,'plain_turns':plain,'reset':reset},ensure_ascii=False))
'''
    elif args.mode == 'network':
        script = base + 'token=' + repr(os.environ['API_TOKEN']) + '''
sid=call('/sessions',token,{})['body']['session_id']
first=call('/chat',token,{'session_id':sid,'message':'Запомни в этом разговоре: кодовое слово Липа-7319.'})
second=call('/chat',token,{'session_id':sid,'message':'Какое кодовое слово я назвал?'})
reset=call('/sessions/reset',token,{'session_id':sid})
after=call('/chat',token,{'session_id':sid,'message':'Какое кодовое слово я назвал?'})
print(json.dumps({'client':'VPS','first':first,'second':second,'reset':reset,'after_reset':after},ensure_ascii=False))
'''
    elif args.mode == 'load':
        script = (ROOT / 'load_test.py').read_text().split("if __name__ == '__main__':")[0]
        script += '\nbase_url=' + repr(args.api_url.rstrip('/')) + '\ntoken=' + repr(tokens[3]) + '''
series=[]
for count in [5,10]:
 series.append({'count':count,'results':load(base_url,token,count)})
print(json.dumps({'client':'VPS','series':series},ensure_ascii=False))
'''
    elif args.mode == 'limits':
        script = base + 'rate_token=' + repr(tokens[0]) + '\ncontext_token=' + repr(tokens[1]) + '''
unauthorized=call('/health','wrong')
# curl reads an early 413 while uploading; urllib may instead raise BrokenPipe.
# Credentials go through stdin, never process arguments; TLS verification stays on.
import subprocess,tempfile,pathlib
with tempfile.TemporaryDirectory() as directory:
 payload=pathlib.Path(directory)/'payload.json'; response=pathlib.Path(directory)/'response.json'
 payload.write_text(json.dumps({'message':'a'*530000}))
 config='url = '+json.dumps(url+'/chat')+'\\nheader = '+json.dumps('Authorization: Bearer '+context_token)+'\\nheader = "Content-Type: application/json"\\ndata-binary = '+json.dumps('@'+str(payload))+'\\noutput = '+json.dumps(str(response))+'\\nwrite-out = "%{http_code}"\\n'
 probe=subprocess.run(['curl','--silent','--show-error','--max-time','30','--config','-'],input=config,capture_output=True,text=True)
 if probe.returncode:raise RuntimeError('Body-limit curl transport failed: '+str(probe.returncode))
 raw=response.read_text()
 try: body=json.loads(raw)
 except ValueError:body={'response_text':raw[:1000]}
 oversize={'status':int(probe.stdout),'body':body,'retry_after':None,'transport':'curl; early-response capable; default TLS verification'}
context=call('/chat',context_token,{'message':'x '*70000})
rate=[call('/chat',rate_token,{'message':'x '*70000}) for _ in range(21)]
summary=[{'status':r['status'],'error':r['body'].get('error'),'retry_after':r['retry_after']} for r in rate]
remaining=int(rate[-1].get('retry_after') or 1)
while remaining>0:
 delay=min(remaining,30);time.sleep(delay);remaining-=delay
recovered=call('/chat',rate_token,{'message':'Назови столицу Франции одним предложением.'})
print(json.dumps({'client':'VPS','unauthorized':unauthorized,'body_limit':oversize,'context_limit':context,'rate':summary,'after_rate_window':recovered},ensure_ascii=False))
'''
    else:
        script = base + 'token=' + repr(tokens[4]) + '''
question='Напиши подробное связное объяснение работы операционных систем примерно на 700 слов.'
with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
 results=list(pool.map(lambda i:call('/chat',token,{'message':question}),range(15)))
print(json.dumps({'client':'VPS','statuses':[r['status'] for r in results],'results':[{'status':r['status'],'error':r['body'].get('error'),'request_id':r['body'].get('request_id'),'usage':r['body'].get('usage')} for r in results]},ensure_ascii=False))
'''
    if args.client == 'vps':
        result = run(script)
    else:
        local = subprocess.run([sys.executable, '-'], input=script, capture_output=True, text=True, timeout=3600)
        if local.returncode:
            log=ROOT/'runtime/local_probe_error.log'
            log.write_text(local.stderr);log.chmod(0o600)
            raise RuntimeError('HTTPS client probe failed: exit '+str(local.returncode)+'; details in private runtime/local_probe_error.log')
        result = json.loads(local.stdout)
    result['client'] = 'VPS HTTPS client' if args.client == 'vps' and args.api_url.startswith('https://') else ('PC external HTTPS client; no client SSH forward' if args.api_url.startswith('https://') else args.client)
    result['api_url'] = args.api_url
    result['tls_verified'] = args.api_url.startswith('https://')
    result['client_ssh_forward_required'] = False if args.api_url.startswith('https://') else None
    if args.mode == 'final':
        from model import Model
        props = Model().info()
        result['pc_runtime_model'] = {
            'file': Path(props['model_path']).name,
            'bytes': Path(props['model_path']).stat().st_size,
            'build': props['build_info'], 'slots': props['total_slots'],
            'context_per_slot': props['default_generation_settings']['n_ctx'],
        }
        result['pc_core_sha256'] = hashlib.sha256(b''.join(
            (ROOT / name).read_bytes() for name in ['agent.py', 'rag.py', 'model.py', 'grounding.py', 'index.py'])).hexdigest()
        selected = ROOT / 'configs/selected.json'
        if selected.exists():
            result['measured_selection'] = json.loads(selected.read_text())
            result['selection_matches_current_core'] = result['measured_selection'].get('source_sha256') == result['pc_core_sha256']
            result['selection_scope'] = 'Q8/optimized model/profile inherited from previous controlled matrix; current agent quality measured separately in results/quality-v2'
    (ROOT / ('results/' + args.output_prefix + '_' + args.mode + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(args.mode, 'saved;', result['client'])


if __name__ == '__main__':
    main()
