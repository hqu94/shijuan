import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from app import app

HOST = "127.0.0.1"
PORT = 7765
URL = f"http://{HOST}:{PORT}/"


def open_when_ready(server):
    while not server.started and not server.should_exit:
        time.sleep(0.1)
    if server.started:
        webbrowser.open(URL)


def main():
    try:
        with urllib.request.urlopen(URL, timeout=1) as response:
            if "拾卷 · 本地小说下载器".encode() in response.read(8192):
                webbrowser.open(URL)
                return
    except (urllib.error.URLError, OSError):
        pass

    print(f"Shijuan: {URL}  (Ctrl+C to stop)", flush=True)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, loop="asyncio", http="h11"))
    threading.Thread(target=open_when_ready, args=(server,), daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
