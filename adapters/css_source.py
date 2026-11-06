import re
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .common import Chapter, paragraph_text


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
