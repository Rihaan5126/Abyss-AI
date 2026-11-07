"""Serve the replay plus optional fresh local inference on registered images only."""

import argparse
from functools import partial
import hashlib
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
from pathlib import Path
from urllib.parse import urlsplit

from .embed import CachedEncoder, DinoV2Encoder
from .perception import Perception


def handler_for(model, registry, ui_root):
    # A raw encoder deliberately bypasses the mission's embedding cache.
    if isinstance(model.encoder, CachedEncoder):
        raise ValueError('Fresh reanalysis requires an uncached encoder')
    allowed = {key: dict(value) for key,value in registry.items()}
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ui_root),**kwargs)

        def reply(self, status, payload):
            body=json.dumps(payload,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)

        def do_GET(self):
            if urlsplit(self.path).path == '/api/inspector':
                self.reply(200, {'artifact_id': model.artifact_id, 'fresh_encoder': True})
            else: super().do_GET()

        def do_POST(self):
            if self.path != '/api/reanalyse':
                return self.reply(404, {'error':'Unknown endpoint'})
            # Refuse cross-origin browser requests to this local inference endpoint.
            origin=self.headers.get('Origin')
            if self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1'):
                return self.reply(403, {'error':'Local host required'})
            if origin and origin != 'http://' + self.headers.get('Host',''):
                return self.reply(403, {'error':'Cross-origin requests are not permitted'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096: raise ValueError('Invalid request size')
                request=json.loads(self.rfile.read(length))
                if not isinstance(request,dict): raise ValueError('Expected an image ID object')
                key=request.get('id')
                if not isinstance(key,str) or key not in allowed:
                    return self.reply(404, {'error':'Image ID is not registered; regenerate the vision replay'})
                record=allowed[key];path=Path(record['input_path'])
                if hashlib.sha256(path.read_bytes()).hexdigest()!=record['input_sha256']:
                    raise ValueError('Registered image changed; regenerate evidence before reanalysis')
                result,evidence=model.predict_with_evidence(path)
                # Return inference results, never private paths or arbitrary files.
                for neighbor in evidence['neighbors']: neighbor.pop('reference',None)
                evidence['embedding_cached']=False
                evidence['recorded_artifact_id']=record['artifact_id']
                evidence['artifact_matches']=record['artifact_id']==model.artifact_id
                self.reply(200,evidence)
            except OSError:
                self.reply(400, {'error':'Registered image could not be read; regenerate the replay'})
            except (ValueError,TypeError) as exc:
                self.reply(400, {'error':str(exc)})
            except RuntimeError:
                self.reply(500, {'error':'The local encoder failed; inspect the server terminal for model/runtime availability'})
    return Handler


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact',default='data/perception-expanded')
    p.add_argument('--registry',default='data/inspector-registry.json')
    p.add_argument('--ui',default='ui')
    p.add_argument('--port',type=int,default=8001)
    p.add_argument('--model-cache',default='.cache/huggingface')
    args=p.parse_args()
    encoder=DinoV2Encoder(cache_dir=args.model_cache,offline=True)
    model=Perception.load(args.artifact,encoder)
    registry=json.loads(Path(args.registry).read_text())
    print(f'Open http://localhost:{args.port} — fresh inference enabled; weights loaded offline.',flush=True)
    HTTPServer(('127.0.0.1',args.port),handler_for(model,registry,Path(args.ui).resolve())).serve_forever()


if __name__=='__main__':main()
