import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Chapter:
    title: str
    url: str


def paragraph_text(node):
    for line_break in node.find_all("br"):
        line_break.replace_with("\n")
    for hidden in node.find_all(["script", "style"]):
        hidden.decompose()
    text = node.get_text()
    text = re.sub(r"&e(?:m)?sp;?(?![a-zA-Z0-9])", "\u3000", text)
    text = re.sub(r"[\u200b\u2060\ufeff]", "", text)
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.strip(" \t") for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")


class ShaonianSource:
    name = "少年小说网"
    origin = "https://www.snxsw.com"
    book_path = re.compile(r"/book/(\d+)/?")
    hidden_row = re.compile(
        r"\.section-list\.ycxsid\s*>\s*li:nth-(child|last-child)"
        r"\((\d+)\)\s*\{\s*display\s*:\s*none\b",
        re.IGNORECASE,
    )

    def __init__(self, rule=None):
        if rule:
            self.name = rule["name"]
            self.origin = rule["url"].rstrip("/")

    def accepts(self, url):
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.netloc.lower() == "www.snxsw.com"
            and self.book_path.fullmatch(parsed.path) is not None
        )

    def fetch(self, url, data=None, *, timeout=20):
        request = Request(url, data=data, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=timeout) as response:
            return BeautifulSoup(response.read(), "html.parser")

    def search(self, query):
        document = self.fetch(
            self.origin + "/search.html",
            urlencode({"s": query, "submit": "搜索"}).encode("ascii"),
            timeout=5,
        )
        results = {}
        for row in document.select("ul.txt-list > li"):
            link = row.select_one(".s2 a[href]")
            if link is None:
                continue
            url = urljoin(self.origin, link["href"])
            if not self.accepts(url):
                continue
            author = row.select_one(".s3")
            latest = row.select_one(".s4")
            results[url] = {
                "title": link.get_text(strip=True),
                "url": url,
                "author": author.get_text(strip=True) if author else "",
                "latest": latest.get_text(strip=True) if latest else "",
                "source": self.name,
            }
        return list(results.values())

    def catalog(self, url):
        return self.book(url)[1]

    def book(self, url, *, first_only=False):
        if not self.accepts(url):
            raise ValueError("请输入少年小说网的 HTTPS 作品详情页链接。")
        book_id = self.book_path.fullmatch(urlsplit(url).path)[1]
        detail_url = f"{self.origin}/book/{book_id}/"
        index_url = f"{self.origin}/index/{book_id}/1/"
        detail = self.fetch(detail_url)
        title_tag = detail.select_one('meta[property="og:title"]')
        title = title_tag.get("content", "").strip() if title_tag else ""
        title = title or f"少年小说网 {book_id}"
        if first_only:
            first_page = self.parse_page(detail, book_id)
            if first_page:
                return title, first_page[:1]
        index = self.fetch(index_url)

        pages = dict.fromkeys([detail_url])
        for option in index.select("select option[value]"):
            page = urlsplit(urljoin(index_url, option["value"]))
            if (
                page.scheme == "https"
                and page.netloc == "www.snxsw.com"
                and re.fullmatch(rf"/index/{book_id}/\d+/", page.path)
            ):
                pages[self.origin + page.path] = None
        if len(pages) == 1:
            pages[index_url] = None

        chapters = {}
        for page_url in pages:
            if page_url == detail_url:
                document = detail
            elif page_url == index_url:
                document = index
            else:
                document = self.fetch(page_url)
            for chapter in self.parse_page(document, book_id):
                chapters.setdefault(chapter.url, chapter)
        if not chapters:
            raise ValueError("书源未返回可识别的章节目录。")
        return title, list(chapters.values())[:1] if first_only else list(chapters.values())

    def parse_page(self, document, book_id):
        lists = document.select("ul.section-list")
        if not lists:
            return []
        catalog = max(lists, key=lambda item: len(item.find_all("li", recursive=False)))
        rows = catalog.find_all("li", recursive=False)
        hidden = set()
        if "ycxsid" in catalog.get("class", []):
            for style in document.find_all("style"):
                for direction, number in self.hidden_row.findall(style.get_text()):
                    position = int(number)
                    hidden.add(position if direction == "child" else len(rows) + 1 - position)

        chapters = []
        for position, row in enumerate(rows, start=1):
            if position in hidden:
                continue
            link = row.find("a", href=True)
            if link is None:
                continue
            url = urlsplit(urljoin(self.origin, link["href"]))
            if url.netloc != "www.snxsw.com" or url.scheme != "https":
                continue
            if not re.fullmatch(rf"/read/\d+/{book_id}/\d+\.html", url.path):
                continue
            title = link.get_text(strip=True)
            if title:
                chapters.append(Chapter(title, self.origin + url.path))
        return chapters

    def read_chapter(self, chapter, *, brief=False):
        paragraphs = []
        visited = set()
        url = chapter.url
        while url:
            if url in visited or len(visited) >= 20:
                raise ValueError("章节分页异常。")
            visited.add(url)
            document = self.fetch(url)
            reader = document.select_one(".word_read")
            if reader is None:
                raise ValueError("书源没有返回章节正文。")
            page = []
            for node in reader.find_all(["p", "script"]):
                if node.name == "p":
                    page.append(paragraph_text(node))
                else:
                    for encoded in re.findall(r"""qsbs\.bb\(['"]([A-Za-z0-9+/=]+)['"]\)""", node.string or ""):
                        fragment = BeautifulSoup(base64.b64decode(encoded, validate=True), "html.parser")
                        page.extend(paragraph_text(p) for p in fragment.find_all("p"))
            if not any(text.strip() for text in page):
                raise ValueError("书源返回了空白正文。")
            paragraphs.extend(text for text in page if text.strip())
            if brief:
                return paragraphs
            next_link = next(
                (a for a in reader.select(".read_btn a[href]") if a.get_text(strip=True) == "下一页"),
                None,
            )
            url = urljoin(url, next_link["href"]) if next_link else None
            if url:
                target = urlsplit(url)
                chapter_path = urlsplit(chapter.url).path.removesuffix(".html")
                if (
                    target.scheme != "https"
                    or target.netloc != "www.snxsw.com"
                    or not re.fullmatch(re.escape(chapter_path) + r"(?:[_-]\d+)?\.html", target.path)
                ):
                    raise ValueError("章节的下一页链接异常。")
        return paragraphs


class CssSource:
    def __init__(self, rule):
        self.rule = rule
        self.name = rule["name"]
        self.origin = rule["url"].rstrip("/")
        self.host = urlsplit(self.origin).hostname

    def same_site(self, url):
        parsed = urlsplit(url)
        return parsed.scheme in {"https", "http"} and parsed.netloc.lower() == self.host

    def accepts(self, url):
        pattern = self.rule.get("book", {}).get("url")
        return self.same_site(url) and (
            not pattern or re.fullmatch(pattern.split("@", 1)[0], url) is not None
        )

    def fetch(self, url, data=None, settings=None, *, timeout=12):
        settings = settings or {}
        headers = {"User-Agent": "Mozilla/5.0"}
        if settings.get("cookies"):
            headers["Cookie"] = settings["cookies"]
        with urlopen(Request(url, data=data, headers=headers), timeout=timeout) as response:
            return BeautifulSoup(response.read(), "html.parser"), response.url

    def search(self, query):
        rule = self.rule.get("search")
        if not rule:
            return []
        url = rule["url"]
        data = None
        if rule.get("method", "get").lower() == "post":
            fields = {}
            for pair in rule["data"].strip("{} ").split(","):
                key, value = pair.split(":", 1)
                fields[key.strip()] = value.strip().replace("%s", query)
            data = urlencode(fields).encode("ascii")
        else:
            url = url.replace("%s", quote(query, safe=""))
        document, base = self.fetch(url, data, rule, timeout=5)
        results = {}
        for row in document.select(rule["result"]):
            link = row.select_one(rule["bookName"].split("@", 1)[0])
            if not link or not link.get("href"):
                continue
            book_url = urljoin(base, link["href"])
            if not self.accepts(book_url):
                continue
            fields = {}
            for key in ("author", "latestChapter"):
                selector = rule.get(key, "").split("@", 1)[0]
                value = row.select_one(selector) if selector else None
                fields[key] = value.get_text(strip=True) if value else ""
            results[book_url] = {
                "title": link.get_text(strip=True), "url": book_url,
                "author": fields["author"], "latest": fields["latestChapter"], "source": self.name,
            }
        return list(results.values())

    def book(self, url, *, first_only=False):
        if not self.accepts(url):
            raise ValueError("作品链接与书源不匹配。")
        detail, base = self.fetch(url)
        title_tag = detail.select_one('meta[property="og:title"]')
        heading = detail.select_one("h1, title")
        title = title_tag.get("content", "").strip() if title_tag else ""
        title = title or (heading.get_text(strip=True) if heading else self.name)
        rule = self.rule["toc"]
        pattern = self.rule.get("book", {}).get("url", "").split("@", 1)[0]
        match = re.fullmatch(pattern, url) if pattern else None
        book_id = match[1] if match and match.lastindex else ""
        page_url = rule.get("url", "").replace("%s", book_id)
        document, page_base = self.fetch(page_url) if page_url and page_url != url else (detail, base)
        visited = {page_url or url}
        chapters = {}
        while True:
            links = document.select(rule["item"])
            if rule.get("isDesc"):
                links.reverse()
            for link in links:
                chapter_url = urljoin(rule.get("baseUri", page_base).replace("%s", book_id), link.get("href", ""))
                name = link.get_text(strip=True)
                if link.get("href") and name and self.same_site(chapter_url):
                    if first_only:
                        return title, [Chapter(name, chapter_url)]
                    chapters.setdefault(chapter_url, Chapter(name, chapter_url))
            selector = rule.get("nextPage")
            next_link = document.select_one(selector) if selector else None
            if next_link is None or not next_link.get("href"):
                break
            next_url = urljoin(page_base, next_link["href"])
            if next_url in visited:
                break
            if not self.same_site(next_url) or len(visited) >= 100:
                raise ValueError("目录分页异常。")
            visited.add(next_url)
            document, page_base = self.fetch(next_url)
        if not chapters:
            raise ValueError("书源未返回可识别的章节目录。")
        return title, list(chapters.values())

    def read_chapter(self, chapter, *, brief=False):
        rule = self.rule["chapter"]
        paragraphs = []
        visited = set()
        url = chapter.url
        while url:
            if url in visited or len(visited) >= 20:
                raise ValueError("章节分页异常。")
            visited.add(url)
            document, base = self.fetch(url)
            selector = rule.get("nextPage", "").replace(":contains(", ":-soup-contains(")
            next_link = document.select_one(selector) if selector else None
            page = []
            for node in document.select(rule["content"]):
                if rule.get("filterTag"):
                    for unwanted in reversed(node.select(rule["filterTag"])):
                        unwanted.decompose()
                for paragraph in node.find_all("p"):
                    paragraph.append("\n\n")
                text = paragraph_text(node)
                if rule.get("filterTxt"):
                    text = re.sub(rule["filterTxt"], "", text)
                page.extend(part for part in text.split("\n\n") if part.strip())
            if not page:
                raise ValueError("书源未返回可识别的正文。")
            paragraphs.extend(page)
            if brief or not next_link or not next_link.get("href"):
                break
            candidate = urljoin(base, next_link["href"])
            label = next_link.get_text(strip=True)
            chapter_path = urlsplit(chapter.url).path.removesuffix(".html")
            same_chapter_page = re.fullmatch(
                re.escape(chapter_path) + r"[_-]\d+\.html",
                urlsplit(candidate).path,
            )
            if not same_chapter_page and "下一页" not in label and "下页" not in label:
                break
            if not self.same_site(candidate):
                raise ValueError("章节的下一页链接异常。")
            url = candidate
        if not paragraphs:
            raise ValueError("书源未返回可识别的正文。")
        return paragraphs


def load_sources():
    path = Path(__file__).with_name("sources.local.json")
    if not path.is_file():
        path = path.with_name("sources.json")
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    adapters = {"shaonian": ShaonianSource, "css": CssSource}
    return [
        adapters[entry["adapter"]](entry["rule"])
        for group in config["sets"].values()
        for entry in group
        if entry["enabled"] and entry["adapter"] in adapters
    ]
