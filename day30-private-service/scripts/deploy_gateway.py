"""Install only the loopback relay on the explicitly configured VPS."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_env

ROOT = Path(__file__).resolve().parents[1]
UNIT = '''[Unit]
Description=Local LLM experiment private relay (no inference)
After=network.target
[Service]
ExecStart=/usr/bin/python3 -u /opt/local-llm-experiment-gateway/gateway.py
Restart=on-failure
RestartSec=3
DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
RestrictAddressFamilies=AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
'''


def ssh(command):
    env = os.environ.copy()
    env['SSHPASS'] = env['SERVER_PASSWORD']
    return subprocess.run(['sshpass', '-e', 'ssh', '-p', env.get('SERVER_PORT', '22'),
                           '-o', 'StrictHostKeyChecking=yes', '-o', 'PreferredAuthentications=password',
                           '-o', 'PubkeyAuthentication=no', env['SERVER_LOGIN'] + '@' + env['HOST_IP'], command],
                          env=env, capture_output=True, text=True, check=True).stdout


def main():
    load_env(sys.argv[1] if len(sys.argv) > 1 else '.env')
    code = base64.b64encode((ROOT / 'gateway.py').read_bytes()).decode()
    unit = base64.b64encode(UNIT.encode()).decode()
    key_path = ROOT / 'runtime/tunnel_key'
    key_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not key_path.exists():
        subprocess.run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-C', 'local-llm-experiment-tunnel', '-f', str(key_path)], check=True, stdout=subprocess.DEVNULL)
    public = key_path.with_suffix('.pub').read_text().strip()
    restricted = 'command="/bin/false",restrict,port-forwarding,permitlisten="127.0.0.1:18780",permitopen="127.0.0.1:8781" ' + public
    # Payload is code/public key only; no credentials or model artifacts cross SSH.
    script = f'''import base64,pathlib,subprocess
root=pathlib.Path('/opt/local-llm-experiment-gateway')
root.mkdir(exist_ok=True)
(root/'gateway.py').write_bytes(base64.b64decode({code!r}))
pathlib.Path('/etc/systemd/system/local-llm-experiment-gateway.service').write_bytes(base64.b64decode({unit!r}))
ssh=pathlib.Path.home()/'.ssh'
ssh.mkdir(mode=0o700,exist_ok=True)
auth=ssh/'authorized_keys'
existing=auth.read_text() if auth.exists() else ''
line={restricted!r}
if line not in existing.splitlines():
 with auth.open('a') as f:f.write(('\\n' if existing and not existing.endswith('\\n') else '')+line+'\\n')
auth.chmod(0o600)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','local-llm-experiment-gateway.service'],check=True)
subprocess.run(['systemctl','restart','local-llm-experiment-gateway.service'],check=True)
print('gateway enabled; restricted tunnel public key installed')
'''
    encoded = base64.b64encode(script.encode()).decode()
    output = ssh('python3 -c "import base64;exec(base64.b64decode(\'' + encoded + '\'))"')
    print(output.strip())


if __name__ == '__main__':
    main()
