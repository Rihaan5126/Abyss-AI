"""Local image-upload demo: python -m perception.demo (model and artifact required)."""

import argparse
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
import json
import time

from PIL import Image

from .embed import CachedEncoder, DinoV2Encoder
from .perception import Perception

PAGE = b'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABYSS perception lab</title>
<style>body{background:#071923;color:#def;font:18px system-ui;max-width:800px;margin:50px auto;padding:20px}
button,input{font:inherit;margin:12px 0}img{max-width:100%;max-height:350px}pre{white-space:pre-wrap;background:#123;padding:20px}</style>
<h1>ABYSS perception lab</h1><p>Choose a cropped marine organism image to run the real model.</p>
<p>Familiar categories: {{CATEGORIES}}</p>
<input type="file" id="file" accept="image/*"><br><img id="preview" alt="Selected organism" hidden>
<p id="status">Waiting for an image.</p><pre id="result">Results will appear here.</pre>
<p>Similarity measures visual resemblance, not classification confidence. Unfamiliar does not mean a new species.</p>
<script>
let previous;
document.querySelector('#file').onchange=async function(){
 const file=this.files[0];if(!file)return;
 const status=document.querySelector('#status'), result=document.querySelector('#result');
 if(previous)URL.revokeObjectURL(previous);previous=URL.createObjectURL(file);
 document.querySelector('#preview').src=previous;document.querySelector('#preview').hidden=false;
 this.disabled=true;status.textContent='Running DINOv2...';result.textContent='';
 try{const response=await fetch('/predict',{method:'POST',body:file});const data=await response.json();
 if(!response.ok)throw Error(data.error);result.textContent=JSON.stringify(data,null,2);status.textContent='Prediction complete.';
 }catch(e){status.textContent=e.message;}finally{this.disabled=false;}
};
</script></html>'''


def handler_for(perception):
    page = PAGE.replace(b'{{CATEGORIES}}', escape(', '.join(sorted(set(perception.index.labels)))).encode())
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, content, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            self.reply(200 if self.path == '/' else 404,
                       page if self.path == '/' else b'Not found', 'text/html; charset=utf-8')

        def do_POST(self):
            if self.path != '/predict':
                self.reply(404, b'{"error":"Not found"}', 'application/json')
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 10_000_000:
                    raise ValueError('Choose an image smaller than 10 MB')
                started = time.perf_counter()
                with Image.open(BytesIO(self.rfile.read(length))) as image:
                    result = perception.predict(image).to_dict()
                result['threshold'] = perception.threshold
                result['elapsed_seconds'] = round(time.perf_counter() - started, 3)
                self.reply(200, json.dumps(result).encode(), 'application/json')
            except (ValueError, OSError) as exc:
                self.reply(400, json.dumps({'error': str(exc)}).encode(), 'application/json')
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', default='data/perception')
    parser.add_argument('--port', type=int, default=7860)
    args = parser.parse_args()
    perception = Perception.load(args.artifact, CachedEncoder(DinoV2Encoder(offline=True)))
    print(f'Open http://localhost:{args.port} in your browser', flush=True)
    HTTPServer(('127.0.0.1', args.port), handler_for(perception)).serve_forever()


if __name__ == '__main__':
    main()
