import base64
import re
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .common import Chapter, paragraph_text


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
