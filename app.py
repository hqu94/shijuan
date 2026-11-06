from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
from pathlib import Path
from threading import Lock
from time import sleep
from urllib.error import URLError
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from sources import Chapter, CssSource, ShaonianSource, load_sources

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
catalogs = OrderedDict()
catalog_lock = Lock()
source_errors = (URLError, OSError, ValueError)
search_pool = ThreadPoolExecutor(max_workers=16)
chapter_pool = ThreadPoolExecutor(max_workers=4)


def fetch_download_chapter(source, chapter):
    sleep(0.35)
    return source.read_chapter(chapter)


@dataclass
class Book:
    source: ShaonianSource | CssSource
    chapters: list[Chapter]
    title: str
    url: str
    catalog_loaded: bool = False
    texts: dict = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)
    progress: dict | None = None


class Lookup(BaseModel):
    url: str = Field(max_length=1000)


class Search(BaseModel):
    query: str = Field(max_length=100)


@app.middleware("http")
async def local_requests(request: Request, call_next):
    if request.headers.get("host") not in {"127.0.0.1:7765", "localhost:7765"}:
        return JSONResponse({"detail": "请使用本机地址访问。"}, status_code=403)
    return await call_next(request)


@app.get("/")
def home():
    return FileResponse(Path(__file__).with_name("index.html"))


@app.post("/search")
def search(data: Search):
    query = data.query.strip()
    if not query:
        raise HTTPException(400, "请输入书名。")
    sources = load_sources()

    def events():
        jobs = {search_pool.submit(source.search, query): source.name for source in sources}
        try:
            yield json.dumps({"total": len(jobs)}) + "\n"
            for job in as_completed(jobs):
                try:
                    event = {"results": job.result()}
                except source_errors:
                    event = {"error": jobs[job]}
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            for job in jobs:
                job.cancel()

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post("/catalog")
def lookup(data: Lookup):
    url = data.url.strip()
    source = next((item for item in load_sources() if item.accepts(url)), None)
    if source is None:
        raise HTTPException(400, "请输入已启用书源的作品详情页链接。")
    try:
        title, chapters = source.book(url, first_only=True)
        preview = source.read_chapter(chapters[0], brief=True)
    except source_errors as error:
        raise HTTPException(502, f"读取书源失败：{error}") from error
    token = uuid4().hex
    book = Book(source, chapters, title, url)
    with catalog_lock:
        catalogs[token] = book
        if len(catalogs) > 12:
            catalogs.popitem(last=False)
    return {
        "token": token,
        "title": title,
        "source": source.name,
        "url": url,
        "firstChapter": chapters[0],
        "preview": "\n\n".join(preview)[:350],
    }


@app.get("/catalog/{token}")
def full_catalog(token: str):
    with catalog_lock:
        book = catalogs.get(token)
    if book is None:
        raise HTTPException(404, "目录已过期，请重新打开作品。")
    with book.lock:
        if not book.catalog_loaded:
            try:
                _, chapters = book.source.book(book.url)
            except source_errors as error:
                raise HTTPException(502, f"读取目录失败：{error}") from error
            if chapters[0].url != book.chapters[0].url:
                raise HTTPException(409, "首章已变化，请重新打开作品。")
            book.chapters = chapters
            book.catalog_loaded = True
        return {"chapters": book.chapters}


@app.get("/preview/{token}")
def full_preview(token: str):
    with catalog_lock:
        book = catalogs.get(token)
    if book is None:
        raise HTTPException(404, "目录已过期，请重新打开作品。")
    with book.lock:
        try:
            if 0 not in book.texts:
                book.texts[0] = book.source.read_chapter(book.chapters[0])
        except source_errors as error:
            raise HTTPException(502, f"读取完整首章失败：{error}") from error
        return {"text": "\n\n".join(book.texts[0])}


@app.get("/download/{token}/progress")
def download_progress(token: str):
    with catalog_lock:
        book = catalogs.get(token)
    if book is None:
        raise HTTPException(404, "目录已过期，请重新打开作品。")
    return {"progress": book.progress}


@app.post("/download/{token}")
def download(token: str, start: int = 1, end: int | None = None, run: str = "", partial: bool = False):
    with catalog_lock:
        book = catalogs.get(token)
    if book is None:
        raise HTTPException(404, "目录已过期，请重新打开作品。")
    if not book.catalog_loaded:
        raise HTTPException(409, "请先读取完整目录。")
    end = len(book.chapters) if end is None else end
    if not 1 <= start <= end <= len(book.chapters):
        raise HTTPException(400, "章节范围无效。")
    selected = range(start - 1, end)
    if not book.lock.acquire(blocking=False):
        raise HTTPException(409, "这本书正在下载。")
    try:
        if partial:
            if not any(number in book.texts for number in selected):
                raise HTTPException(409, "所选范围还没有成功下载的章节。")
            sections = [book.title, "此文件包含缺章，缺失位置已标注。"]
            for number in selected:
                chapter = book.chapters[number]
                paragraphs = book.texts.get(number)
                content = "\n\n".join(paragraphs) if paragraphs else f"【第 {number + 1} 章缺失】"
                sections.append(chapter.title + "\n\n" + content)
            return Response(
                "\n\n".join(sections).replace("\n", "\r\n"),
                media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(book.title + " [缺章].txt", safe="")},
            )
        failed = []
        processed = sum(number in book.texts for number in selected)
        book.progress = {"run": run, "processed": processed, "total": len(selected), "failed": 0}
        jobs = {
            chapter_pool.submit(fetch_download_chapter, book.source, book.chapters[number]): number
            for number in selected
            if number not in book.texts
        }
        for job in as_completed(jobs):
            number = jobs[job]
            try:
                book.texts[number] = job.result()
            except source_errors:
                failed.append({"number": number + 1, "title": book.chapters[number].title})
            processed += 1
            book.progress = {"run": run, "processed": processed, "total": len(selected), "failed": len(failed)}
        if failed:
            failed.sort(key=lambda item: item["number"])
            return JSONResponse({"failed": failed, "completed": len(selected) - len(failed)}, status_code=502)
        sections = [
            book.chapters[number].title + "\n\n" + "\n\n".join(book.texts[number])
            for number in selected
        ]
        return Response(
            "\n\n".join([book.title, *sections]).replace("\n", "\r\n"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(book.title + ".txt", safe="")},
        )
    finally:
        book.lock.release()
