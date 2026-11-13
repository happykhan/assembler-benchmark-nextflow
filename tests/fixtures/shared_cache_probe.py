"""Two-node GPFS admission probe; fixture bytes only, no scientific workload."""
import argparse
import errno
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benchlib.preparation import execute_work_list, plan_preparation

PAYLOAD = b'assembly-benchmark-shared-cache-probe\n' * 2048


def save(path,value):
    temporary=path.with_name(path.name+'.partial-'+str(os.getpid()))
    temporary.write_text(json.dumps(value,indent=2)+'\n');os.replace(temporary,path)


def server(directory):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            with (directory/'requests.jsonl').open('a') as stream:
                stream.write(json.dumps({'client':self.client_address[0],'pid':os.getpid()})+'\n')
            time.sleep(.5)
            self.send_response(200);self.send_header('Content-Length',str(len(PAYLOAD)));self.end_headers()
            self.wfile.write(PAYLOAD)
    http=ThreadingHTTPServer(('0.0.0.0',0),Handler)
    host=socket.gethostbyname(socket.gethostname())
    save(directory/'server.json',{'url':'http://%s:%s/input'%(host,http.server_port),
         'sha256':hashlib.sha256(PAYLOAD).hexdigest(),'size_bytes':len(PAYLOAD)})
    http.serve_forever()


def worker(directory,offline):
    # This fixture's URL is a sibling compute node, never an external service.
    # Explicitly avoid site/user outbound HTTP proxies for the internal probe.
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    metadata=json.loads((directory/'server.json').read_text())
    host=socket.gethostname();mode='offline' if offline else 'online'
    (directory/('ready-'+mode+'-'+host)).touch()
    deadline=time.monotonic()+30
    while len(list(directory.glob('ready-'+mode+'-*')))<2:
        if time.monotonic()>deadline:raise TimeoutError('Two distinct worker nodes did not reach the barrier')
        time.sleep(.05)
    blocked=False
    if offline:
        try:
            probe=socket.socket(socket.AF_INET,socket.SOCK_STREAM);probe.close()
        except OSError as error:blocked=error.errno==errno.EAFNOSUPPORT
        if not blocked:raise RuntimeError('Offline worker is not protected by the network-blocking wrapper')
    plan={'dependencies':[{'id':'shared-probe','kind':'reference','target':'references/shared-probe.bin',
          'source':{'url':metadata['url']},'sha256':metadata['sha256'],'size_bytes':metadata['size_bytes']}]}
    work=plan_preparation(plan,directory/'cache',directory,offline=offline)
    try:result=execute_work_list(work)
    except urllib.error.HTTPError as error:
        save(directory/('http-error-'+host+'.json'),{'status':error.code,
             'server':error.headers.get('Server'),'body':error.read(512).decode('utf-8','replace')})
        raise
    save(directory/('result-'+mode+'-'+host+'.json'),{'host':host,'offline':offline,
         'network_blocked':blocked,'ready':result['ready'],'sha256':result['items'][0]['observed_sha256']})


def verify(directory):
    online=[json.loads(p.read_text()) for p in directory.glob('result-online-*.json')]
    offline=[json.loads(p.read_text()) for p in directory.glob('result-offline-*.json')]
    requests=[json.loads(line) for line in (directory/'requests.jsonl').read_text().splitlines()]
    assert len(online)==2 and len(offline)==2
    assert len({r['host'] for r in online})==2
    assert all(r['ready'] for r in online+offline)
    assert all(r['network_blocked'] for r in offline)
    assert len({r['sha256'] for r in online+offline})==1
    assert len(requests)==1,requests
    result={'status':'verified','nodes':sorted({r['host'] for r in online}),
            'http_downloads':len(requests),'online_requesters':2,'offline_blocked_requesters':2,
            'sha256':online[0]['sha256'],'lock':'atomic mkdir on GPFS; post-lock target recheck'}
    save(directory/'verification.json',result);print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('server','worker','verify'))
    parser.add_argument('directory',type=Path)
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args();args.directory.mkdir(parents=True,exist_ok=True)
    if args.mode=='server':server(args.directory)
    elif args.mode=='worker':worker(args.directory,args.offline)
    else:verify(args.directory)
