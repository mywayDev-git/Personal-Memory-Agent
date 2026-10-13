"""Run the synthetic web playground using the existing local model servers."""
import argparse
import threading
import time
import webbrowser
from dataclasses import replace

import uvicorn

from config.settings import Settings
from pma.life_web import ROOT, LifeDataset
from pma.settings import AppSettings
from pma.web import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    dataset = LifeDataset(ROOT / 'data/life_diagnostics.json',
                          ROOT / 'output/life-evaluation-20261013')
    settings = replace(AppSettings.from_env(), data_dir=ROOT / '.local/life-web', port=8766,
                       embedding_revision=dataset.revision, llm=replace(Settings.from_env(), model='qwen3'))
    app = create_app(settings, test_dataset=dataset)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=settings.port,
                                          access_log=False))
    def open_browser():
        while not server.started and not server.should_exit:
            time.sleep(.1)
        if server.started:
            url = settings.origin + '/#token=' + app.state.bootstrap_token
            if args.no_browser:
                (settings.data_dir / 'launch-url').write_text(url, encoding='utf-8')
            else:
                webbrowser.open(url)
    threading.Thread(target=open_browser, daemon=True).start()
    server.run()


if __name__ == '__main__':
    main()
