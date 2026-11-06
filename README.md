<div align="center">

# 📚 拾卷 · Shijuan

**搜到书，先看一章，再决定下载。**

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-536DFE)
![FastAPI](https://img.shields.io/badge/FastAPI-local-009688?logo=fastapi&logoColor=white)
![TXT UTF-8](https://img.shields.io/badge/Export-TXT%20%2F%20UTF--8-8A5CC2)
![MIT](https://img.shields.io/badge/License-MIT-E6A23C)

</div>

拾卷是一款在自己电脑上运行的小说整理工具。默认按书名搜索，也可以粘贴已启用书源的作品链接。遇到同名或标题混乱的版本，可以先看首章正文，再选章节导出 TXT。

## ✨ 能做什么

| 功能 | 使用方式 |
| --- | --- |
| 🔎 **找书** | 按书名搜索，结果按书源返回的顺序追加。也可以切换到「粘贴链接」。 |
| 📖 **核对版本** | 左侧分页比较结果，点击整行后右侧显示首章开头。按需展开完整首章或目录。 |
| 🎚️ **选择章节** | 下载全书、前 3 章，或指定起止章节。 |
| ⚡ **并行下载** | 最多同时抓取 4 章，显示处理进度，并按目录顺序合并正文。 |
| 🧩 **处理失败章节** | 可以单独重试。若主动确认保存已有章节，TXT 会标注缺失位置。 |

## 🚀 快速开始

需要 Python 3.12。下载或克隆仓库后，在项目目录运行对应的命令。

### 🪟 Windows · PowerShell

如果你有打包版，双击 `Shijuan.exe` 即可启动并打开浏览器。使用源码时运行以下命令。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.cmd
```

如需自行生成 Windows 打包版，在安装应用依赖后运行：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\build-windows.cmd
```

生成的文件位于 `dist/Shijuan.exe`。如需自定义书源，把配置文件放在 EXE 同一目录。

### 🍎 macOS / 🐧 Linux · 终端

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 7765
```

启动后打开 [拾卷](http://127.0.0.1:7765/)。在启动窗口按 **Ctrl+C** 停止服务。

## 📚 书源配置

书源集中在 [sources.json](sources.json)，可以新增、删除、修改或停用。下次搜索或打开作品时会读取最新配置。个人配置也可以放在 `sources.local.json`，程序会优先使用它。

## 🔒 本地运行

默认只监听 `127.0.0.1`。搜索、预览和下载会向已启用的书源发送请求，应用没有设备信息上报。TXT 由浏览器保存到你选择的位置。请仅下载你有权获取和保存的内容。

## 🗂️ 项目结构

| 位置 | 内容 |
| --- | --- |
| [web/](web/) | 网页模板、样式和浏览器交互 |
| [adapters/](adapters/) | 书源解析与正文清洗 |
| [sources.json](sources.json) | 默认书源配置 |
| [app.py](app.py) | 本地 API 和下载流程 |
| [txt_export.py](txt_export.py) | TXT 格式化与保存 |

## 💚 许可证

拾卷采用 [MIT 许可证](LICENSE)。
