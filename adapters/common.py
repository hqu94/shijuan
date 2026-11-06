import re
from dataclasses import dataclass


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
