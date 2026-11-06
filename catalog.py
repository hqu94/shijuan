import argparse

from sources import load_sources


def main():
    parser = argparse.ArgumentParser(description="查看已接入书源的章节目录")
    parser.add_argument("url", help="作品详情页链接")
    args = parser.parse_args()

    source = next((item for item in load_sources() if item.accepts(args.url)), None)
    if source is None:
        parser.error("该链接不属于已接入书源。")

    _, chapters = source.book(args.url)
    print(f"{source.name} · {len(chapters)} 章")
    for number, chapter in enumerate(chapters, start=1):
        print(f"{number:>3}. {chapter.title}")


if __name__ == "__main__":
    main()
