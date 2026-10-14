"""Add a dedicated HTTPS route to existing Caddy; preserve the OCR fallback."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import load_env, http_json, utc_now
from remote_checks import run

BLOCK = ''' # BEGIN LOCAL LLM HTTPS
 handle_path /local-llm/* {
  reverse_proxy 127.0.0.1:8781 {
   transport http {
    response_header_timeout 1800s
   }
  }
 }
 handle {
  reverse_proxy 127.0.0.1:8765
 }
 # END LOCAL LLM HTTPS'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    args = parser.parse_args()
    load_env(ROOT / '.env')
    load_env(args.env_file)
    token = os.environ['API_TOKEN']
    health = http_json('http://127.0.0.1:8780/health', token=token, timeout=10)
    if not all(health.get(k) for k in ['ready', 'rag_ready', 'context_matches', 'slots_match']):
        raise RuntimeError('Restore the measured matching PC service first')
    script = '''import pathlib,subprocess,json,hashlib,re,urllib.request,datetime
config=pathlib.Path('/etc/caddy/Caddyfile')
previous=config.read_bytes()
text=previous.decode()
'''+ '\ntoken='+repr(token)+'\nblock='+repr(BLOCK)+'''
request=urllib.request.Request('http://127.0.0.1:8781/health',headers={'Authorization':'Bearer '+token})
with urllib.request.urlopen(request,timeout=10) as response:health=json.load(response)
assert all(health.get(k) for k in ['ready','rag_ready','context_matches','slots_match'])
if '# BEGIN LOCAL LLM HTTPS' in text:
 if block not in text:raise RuntimeError('Existing managed route differs; inspect before replacing')
 candidate=previous;changed=False
else:
 lines=text.splitlines(keepends=True)
 matches=[i for i,line in enumerate(lines) if line.strip()=='reverse_proxy 127.0.0.1:8765']
 if len(matches)!=1 or '/local-llm' in text:raise RuntimeError('Unsupported Caddy layout; original unchanged')
 i=matches[0];candidate=(''.join(lines[:i])+block+chr(10)+''.join(lines[i+1:])).encode();changed=True
stage=pathlib.Path('/etc/caddy/Caddyfile.local-llm.staged')
stage.write_bytes(candidate);stage.chmod(config.stat().st_mode & 0o777)
validation=subprocess.run(['caddy','validate','--config',str(stage),'--adapter','caddyfile'],capture_output=True,text=True)
if validation.returncode:raise RuntimeError('Caddy validation failed; original unchanged')
old=json.loads(subprocess.check_output(['caddy','adapt','--config',str(config),'--adapter','caddyfile'],stderr=subprocess.DEVNULL))
new=json.loads(subprocess.check_output(['caddy','adapt','--config',str(stage),'--adapter','caddyfile'],stderr=subprocess.DEVNULL))
assert old.get('apps',{}).get('tls')==new.get('apps',{}).get('tls'),'TLS settings changed'
def normalized_groups(server):
 # Caddy assigns arbitrary group names while adapting mutually exclusive handles.
 names={}
 def walk(value):
  if isinstance(value,list):return [walk(item) for item in value]
  if isinstance(value,dict):
   return {key:(names.setdefault(item,'group-'+str(len(names))) if key=='group' and isinstance(item,str) else walk(item)) for key,item in value.items()}
  # file_server auto-hides the config filename; the staged filename changes on activation.
  if value==str(stage):return str(config)
  return value
 return walk(server)
oldservers=old['apps']['http']['servers'];newservers=new['apps']['http']['servers']
assert set(oldservers)==set(newservers)
for name in oldservers:
 assert oldservers[name]['listen']==newservers[name]['listen']
 if ':80' in oldservers[name]['listen']:assert normalized_groups(oldservers[name])==normalized_groups(newservers[name]),'ACME/HTTP routes changed'
assert config.read_bytes()==previous,'Concurrent Caddy modification; refusing overwrite'
backup=None
if changed:
 backup=config.with_name('Caddyfile.before-local-llm-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 backup.write_bytes(previous);backup.chmod(config.stat().st_mode & 0o777)
 config.write_bytes(candidate)
 result=subprocess.run(['systemctl','reload','caddy'],capture_output=True,text=True)
 if result.returncode:
  config.write_bytes(previous);subprocess.run(['systemctl','reload','caddy'],check=True,capture_output=True)
  raise RuntimeError('Caddy reload failed; previous configuration restored')
assert subprocess.run(['systemctl','is-active','--quiet','caddy']).returncode==0
stage.unlink(missing_ok=True)
print(json.dumps({'changed':changed,'backup':str(backup) if backup else None,'caddy_validation':True,
 'tls_settings_preserved':True,'acme_http_routes_preserved':True,
 'before_sha256':hashlib.sha256(previous).hexdigest(),'after_sha256':hashlib.sha256(candidate).hexdigest(),
 'route_prefix':'/local-llm','llm_upstream':'127.0.0.1:8781','ocr_fallback':'127.0.0.1:8765'}))
'''
    result = run(script)
    host = os.environ['HOST_IP']
    authority = '['+host+']' if ':' in host else host
    url = 'https://' + authority + '/local-llm'
    verified = http_json(url+'/health', token=token, timeout=15)
    assert verified['context_matches'] and verified['slots_match'] and verified['rag_ready']
    result.update(utc=utc_now(), api_url=url, public_https_health=verified,
                  tls_verification='Default trusted CA and hostname/IP verification; no insecure overrides')
    (ROOT/'results/https_deployment.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    private = ROOT/'runtime/https_client.env'
    private.write_text('API_URL='+url+'\nAPI_TOKEN='+token+'\n');private.chmod(0o600)
    print('HTTPS route deployed and verified:', url)
    print('Caddy validation passed; existing TLS/ACME settings and OCR fallback preserved.')


if __name__ == '__main__':
    main()
