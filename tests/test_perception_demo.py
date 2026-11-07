from http.server import HTTPServer
from io import BytesIO
import json
from threading import Thread
from types import SimpleNamespace
from urllib.request import Request, urlopen

from PIL import Image

from perception.demo import handler_for


def test_demo_displays_loaded_categories_and_runs_uploaded_image():
    class Predictor:
        index = SimpleNamespace(labels=['Scotoplanes', 'Atolla', 'Atolla'])
        threshold = .4

        def predict(self, image):
            assert image.size == (12, 8)
            return SimpleNamespace(to_dict=lambda: {'predicted_category': 'Atolla', 'is_unknown': False})

    server = HTTPServer(('127.0.0.1', 0), handler_for(Predictor()))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        page = urlopen(url).read().decode()
        assert 'Atolla, Scotoplanes' in page
        assert 'Vampyroteuthis infernalis' not in page
        buffer = BytesIO()
        Image.new('RGB', (12, 8), 'blue').save(buffer, format='PNG')
        result = json.loads(urlopen(Request(url + '/predict', data=buffer.getvalue())).read())
        assert result['predicted_category'] == 'Atolla'
        assert result['threshold'] == .4
        assert result['elapsed_seconds'] >= 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
