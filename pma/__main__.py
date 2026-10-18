import argparse
import logging
import threading
import time
import webbrowser

import uvicorn

from .settings import AppSettings
from .web import create_app


def main():
    parser = argparse.ArgumentParser(description="로컬 Personal Memory Agent")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("-test", "--test", action="store_true",
                        help="메인 실행 창에 저장·검색 과정을 한국어로 표시")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = AppSettings.from_env()
    app = create_app(settings, console_test=args.test)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=settings.port, access_log=False, log_level="warning"
        )
    )
    url = settings.origin + "/#token=" + app.state.bootstrap_token

    def open_when_ready():
        while not server.started and not server.should_exit:
            time.sleep(0.1)
        if server.started:
            print("이 PC에서만 사용할 일회용 접속 주소 (공유하지 마세요):\n" + url, flush=True)
            if not args.no_browser:
                try:
                    opened = webbrowser.open(url)
                except webbrowser.Error:
                    opened = False
                if not opened:
                    print(
                        "브라우저를 자동으로 열지 못했습니다. 위 주소를 직접 열어주세요.",
                        flush=True,
                    )

    threading.Thread(target=open_when_ready, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
