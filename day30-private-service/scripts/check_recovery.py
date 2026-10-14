from pathlib import Path
import os,json,sys,signal,time,subprocess
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'scripts'))
from common import load_env,http_json,utc_now
from model import Model
import argparse,urllib.request,urllib.error
parser=argparse.ArgumentParser(description='Stop/recover only recorded owned model/tunnel; use when API queue is idle.')
parser.add_argument('--env-file',required=True,help='Private VPS connection env for restarting outbound SSH')
parser.add_argument('--api-url',required=True)
args=parser.parse_args()
load_env(root/'.env');load_env(args.env_file)
def remote(path,data=None):
 req=urllib.request.Request(args.api_url.rstrip('/')+path,
     data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),
     headers={'Authorization':'Bearer '+os.environ['API_TOKEN'],'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=1800) as response:return {'status':response.status,'body':json.load(response)}
 except urllib.error.HTTPError as error:return {'status':error.code,'body':json.load(error)}
def save(name,result):
 result.update(api_url=args.api_url,tls_verified=args.api_url.startswith('https://'),client_ssh_forward_required=False)
 (root/'results'/('https_'+name)).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
def stop_owned(pid,match):
 cmd=Path('/proc',str(pid),'cmdline').read_bytes()
 assert match in cmd,'Refusing to stop an unrelated process'
 os.kill(pid,signal.SIGTERM)
 for _ in range(100):
  p=Path('/proc',str(pid),'status')
  if not p.exists() or '\nState:\tZ' in p.read_text():return
  time.sleep(.1)
 raise RuntimeError('Owned process did not terminate')
pidpath=root/'runtime/restored_processes.json';pids=json.loads(pidpath.read_text())
selected=json.loads((root/'configs/selected.json').read_text())
health=http_json('http://127.0.0.1:8780/health',token=os.environ['API_TOKEN'])
assert health['pending']==0 and health['context_matches'] and health['slots_match']
expected_file=Path(Model().info()['model_path']).name
stop_owned(pids['model'],expected_file.encode())
failed=remote('/health');assert failed['status']==503 and failed['body']['error']=='model_unavailable'
save('actual_model_outage.json',{'utc':utc_now(),'stage':'Actual owned PC llama-server stopped','client':'PC direct HTTPS; default TLS verification; no client SSH forward',**failed})
env=os.environ.copy();env.update(BACKEND='vulkan',PARALLEL='3',API_SLOTS='3',MODEL_TIMEOUT='600')
log=(root/'runtime/articles_model_recovered.log').open('w')
model=subprocess.Popen([str(root/'.venv/bin/python'),'scripts/start_selected_model.py'],cwd=root,env=env,stdout=log,stderr=log,start_new_session=True)
for _ in range(240):
 if model.poll() is not None:raise RuntimeError('Recovery backend failed; inspect private runtime log')
 try:
  props=Model().info();Model().health();break
 except Exception:time.sleep(1)
else:raise RuntimeError('Recovery model readiness timeout')
assert Path(props['model_path']).name==expected_file and props['default_generation_settings']['n_ctx']==selected['profile_settings']['context'] and props['total_slots']==3
pids['model']=model.pid;pidpath.write_text(json.dumps(pids))
answer=remote('/chat',{'message':'Назови столицу Франции одним предложением по-русски.'})
assert answer['status']==200 and 'Париж' in answer['body']['text'] and answer['body']['usage']['completion_tokens']>0
save('actual_model_recovery.json',{'utc':utc_now(),'client':'PC direct HTTPS; default TLS verification; no client SSH forward','model_file':expected_file,'selected_case':selected['case'],**answer})
print('Actual model outage503 and new generated recovery200 verified.',flush=True)
health=http_json('http://127.0.0.1:8780/health',token=os.environ['API_TOKEN'])
assert health['pending']==0,'Do not stop tunnel while API work is in progress'
reverse=[]
for proc in Path('/proc').glob('[0-9]*'):
 try:
  parts=(proc/'cmdline').read_bytes().split(b'\0')
  if parts and Path(os.fsdecode(parts[0])).name=='ssh' and b'-R' in parts and b'127.0.0.1:18780:127.0.0.1:8780' in parts:reverse.append(int(proc.name))
 except OSError:pass
assert len(reverse)==1,'Expected exactly one owned task reverse-forward'
stop_owned(reverse[0],b'127.0.0.1:18780:127.0.0.1:8780')
failed=remote('/health');assert failed['status']==503 and failed['body']['error']=='pc_tunnel_unavailable'
save('tunnel_outage.json',{'utc':utc_now(),'stage':'Actual task reverse SSH tunnel stopped','client':'PC direct HTTPS; default TLS verification; no client SSH forward',**failed})
log=(root/'runtime/articles_tunnel_recovered.log').open('w')
tunnel=subprocess.Popen(['bash','scripts/start_tunnel.sh'],cwd=root,env=env,stdout=log,stderr=log,start_new_session=True)
for _ in range(60):
 if tunnel.poll() is not None:raise RuntimeError('Reverse SSH recovery failed; inspect private runtime log')
 try:
  state=remote('/health')
  if state['status']==200 and state['body']['context_matches'] and state['body']['slots_match']:break
 except Exception:pass
 time.sleep(1)
else:raise RuntimeError('Reverse SSH recovery timeout')
pids['tunnel']=tunnel.pid;pidpath.write_text(json.dumps(pids))
answer=remote('/chat',{'message':'Назови столицу Японии одним предложением по-русски.'})
assert answer['status']==200 and 'Токио' in answer['body']['text'] and answer['body']['usage']['completion_tokens']>0
save('tunnel_recovery.json',{'utc':utc_now(),'client':'PC direct HTTPS; default TLS verification; no client SSH forward','health':state,'model_file':expected_file,**answer})
print('Actual reverse tunnel outage503 and new generated recovery200 verified.',flush=True)
print('HTTPS recovery checks complete; no client forward used.',flush=True)
