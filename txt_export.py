import re
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import Response


def export_txt(sections, filename, directory):
    body = "\n\n".join(sections).replace("\n", "\r\n")
    if not directory:
        return Response(body, media_type="text/plain; charset=utf-8", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")
        })
    folder = Path(directory).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise HTTPException(400, "请输入本机已存在的绝对目录路径。")
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename.removesuffix(".txt")).strip(" .")[:80]
    stem = stem or "拾卷下载"
    if re.match(r"(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", stem):
        stem = "_" + stem
    for number in range(1, 1001):
        suffix = "" if number == 1 else f" ({number})"
        target = folder / f"{stem}{suffix}.txt"
        try:
            with target.open("xb") as output:
                try:
                    output.write(body.encode("utf-8"))
                except OSError:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise
        except FileExistsError:
            continue
        except OSError as error:
            raise HTTPException(400, "无法写入下载目录，请检查目录权限。") from error
        return {"saved": str(target)}
    raise HTTPException(409, "同名文件过多，请更换目录。")
