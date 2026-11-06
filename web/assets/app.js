const byId = id => document.getElementById(id);
const settingsDialog = byId('settings-dialog');
let saveDirectory = localStorage.getItem('shijuan.downloadDirectory') || '';
byId('download-settings').addEventListener('click', () => {
  byId('save-directory').value = saveDirectory;
  settingsDialog.showModal();
});
byId('cancel-settings').addEventListener('click', () => settingsDialog.close());
byId('settings-form').addEventListener('submit', event => {
  event.preventDefault();
  saveDirectory = byId('save-directory').value.trim();
  localStorage.setItem('shijuan.downloadDirectory', saveDirectory);
  settingsDialog.close();
});

function requestDownload(path) {
  return fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({directory: saveDirectory}),
  });
}

async function saveDownload(response, filename) {
  if (response.headers.get('content-type')?.includes('application/json')) {
    const {saved} = await response.json();
    return '已保存到 ' + saved;
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return '';
}
const status = byId('status');
const openButton = byId('open');
const download = byId('download');
const query = byId('query');
const toggle = byId('toggle');
const matches = byId('matches');
const workspace = byId('workspace');
const range = byId('range');
const views = [...document.querySelectorAll('.preview-tools button')];
const inputs = {search: '', link: ''};
let mode = 'search';
let book;
let activeView = 'brief';
const pageSize = 18;
let results = [];
let page = 0;
let selectedUrl = '';
let searching = false;
let busy = false;
let partialRange = null;

function clearPartial() {
  partialRange = null;
  byId('partial-download').hidden = true;
}

function renderMatches() {
  const pageCount = Math.ceil(results.length / pageSize);
  const rows = results.slice(page * pageSize, (page + 1) * pageSize).map(item => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'match';
    row.disabled = busy;
    row.setAttribute('aria-pressed', String(item.url === selectedUrl));
    const title = document.createElement('strong');
    title.textContent = item.title;
    const details = document.createElement('small');
    details.textContent = [item.source, item.author, item.latest && '末章：' + item.latest].filter(Boolean).join(' · ');
    row.addEventListener('click', () => showBook(item.url, row));
    row.append(title, details);
    return row;
  });
  byId('match-list').replaceChildren(...rows);
  if (!rows.length) byId('match-list').textContent = '暂无候选版本。';
  byId('pagination').hidden = pageCount <= 1;
  byId('page-label').textContent = '第 ' + (page + 1) + ' / ' + pageCount + ' 页';
  updatePagination(busy);
}

function updatePagination(busy) {
  byId('previous').disabled = busy || page === 0;
  byId('next').disabled = busy || (page + 1) * pageSize >= results.length;
}

for (const [id, direction] of [['previous', -1], ['next', 1]]) {
  byId(id).addEventListener('click', () => {
    page += direction;
    renderMatches();
    byId('match-list').scrollTop = 0;
  });
}

function clearPreview(message = '选择左侧的版本，查看首章开头。') {
  byId('result').hidden = true;
  byId('preview-empty').textContent = message;
  byId('preview-empty').hidden = false;
}

function selectView(view) {
  activeView = view;
  for (const button of views) button.setAttribute('aria-pressed', String(button.dataset.view === view));
  byId('chapters').hidden = view !== 'catalog';
  byId('chapter-actions').hidden = view === 'catalog';
  byId('chapter-title').hidden = view === 'catalog';
  const preview = byId('preview');
  preview.hidden = view === 'catalog';
  preview.dataset.view = view;
  const readingWindow = byId('reading-window');
  readingWindow.scrollTop = 0;
  readingWindow.tabIndex = view === 'brief' ? -1 : 0;
  views.find(button => button.dataset.view === 'full').textContent = view === 'full' ? '收起全章' : '展开全章';
  if (view !== 'catalog') {
    byId('preview-text').textContent = view === 'brief' ? book.preview : (book.fullPreview ?? '正在加载完整首章…');
  }
}

for (const button of views) button.addEventListener('click', async () => {
  const view = activeView === button.dataset.view ? 'brief' : button.dataset.view;
  selectView(view);
  const current = book;
  if (view === 'catalog') {
    try {
      await loadCatalog(current);
    } catch (error) {
      if (book === current && activeView === 'catalog') byId('chapters').textContent = error.message;
    }
    return;
  }
  if (view !== 'full' || current.fullPreview !== undefined) return;
  try {
    const response = await fetch('/preview/' + current.token);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail);
    current.fullPreview = data.text;
    if (book === current && activeView === 'full') selectView('full');
  } catch (error) {
    if (book === current && activeView === 'full') byId('preview-text').textContent = error.message;
  }
});

async function loadCatalog(current) {
  if (!current.chapters) {
    const list = byId('chapters');
    list.textContent = '正在读取完整目录…';
    const response = await fetch('/catalog/' + current.token);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail);
    current.chapters = data.chapters;
    if (book === current) {
      byId('count').textContent = current.source + ' · ' + current.chapters.length + ' 章';
      for (const id of ['start', 'end']) byId(id).max = current.chapters.length;
      list.replaceChildren(...current.chapters.map(chapter => {
        const row = document.createElement('li');
        const link = document.createElement('a');
        link.href = chapter.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = chapter.title;
        row.append(link);
        return row;
      }));
    }
  }
  return current.chapters;
}

function updateRange() {
  clearPartial();
  const custom = range.value === 'custom';
  byId('custom-range').hidden = !custom;
  byId('start').disabled = !custom;
  byId('end').disabled = !custom;
  download.textContent = '下载 TXT';
}
range.addEventListener('change', updateRange);
for (const id of ['start', 'end']) byId(id).addEventListener('input', () => {
  clearPartial();
  download.textContent = '下载 TXT';
});

function setBusy(value) {
  busy = value;
  openButton.disabled = busy || searching;
  toggle.disabled = busy || searching;
  download.disabled = busy;
  byId('partial-download').disabled = busy;
  for (const button of matches.querySelectorAll('button')) button.disabled = busy;
  for (const button of views) button.disabled = busy;
  updatePagination(busy);
}

toggle.addEventListener('click', () => {
  inputs[mode] = query.value;
  mode = mode === 'search' ? 'link' : 'search';
  const link = mode === 'link';
  query.type = link ? 'url' : 'search';
  query.maxLength = link ? 1000 : 100;
  query.placeholder = link ? '粘贴已接入书源的作品详情页链接' : '输入书名，例如：地球上线';
  query.value = inputs[mode];
  byId('input-label').textContent = link ? '作品链接' : '书名';
  toggle.textContent = link ? '按书名搜索' : '粘贴链接';
  openButton.textContent = link ? '读取目录' : '搜索小说';
  byId('matches-title').textContent = '书源对比';
  byId('match-list').textContent = link ? '粘贴链接后在这里显示对应版本。' : '搜索后在这里比较候选版本。';
  workspace.hidden = true;
  byId('pagination').hidden = true;
  clearPreview();
  status.textContent = '';
  query.focus();
});

async function request(path, payload) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败。');
  return data;
}

async function showBook(url, selected) {
  setBusy(true);
  workspace.hidden = false;
  const hasPreview = !byId('result').hidden;
  if (!hasPreview) clearPreview('正在加载首章…');
  status.textContent = '正在读取首章预览…';
  download.textContent = '下载 TXT';
  try {
    const data = await request('/catalog', {url});
    book = data;
    byId('download-progress').hidden = true;
    byId('title').textContent = data.title;
    byId('count').textContent = data.source;
    byId('original').href = data.url;
    byId('chapters').replaceChildren();
    byId('chapter-title').textContent = data.firstChapter.title;
    if (!selected) {
      const name = document.createElement('strong');
      name.textContent = data.title;
      const details = document.createElement('p');
      details.textContent = data.source;
      byId('match-list').replaceChildren(name, details);
    } else {
      selectedUrl = url;
      for (const button of matches.querySelectorAll('button.match')) {
        const active = button === selected;
        button.setAttribute('aria-pressed', String(active));
      }
    }
    selectView('brief');
    range.value = 'all';
    byId('start').value = 1;
    byId('end').value = 1;
    for (const id of ['start', 'end']) byId(id).removeAttribute('max');
    updateRange();
    byId('preview-empty').hidden = true;
    byId('result').hidden = false;
    status.textContent = '';
  } catch (error) {
    if (!hasPreview) clearPreview('未能加载预览。');
    status.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

byId('lookup').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || searching) return;
  const value = query.value.trim();
  if (!value) return;
  workspace.hidden = false;
  clearPreview();
  byId('matches-title').textContent = '书源对比';
  byId('match-list').textContent = '';
  byId('pagination').hidden = true;
  results = [];
  page = 0;
  selectedUrl = '';
  if (mode === 'link') {
    await showBook(value);
    return;
  }
  searching = true;
  setBusy(false);
  status.textContent = '';
  const heading = byId('matches-title');
  heading.textContent = '书源对比 · 搜索中…';
  const errors = [];
  try {
    const response = await fetch('/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: value})
    });
    if (!response.ok) throw new Error('搜索请求失败。');
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += chunk.value;
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        const batch = JSON.parse(line);
        if (batch.error) errors.push(batch.error);
        if (batch.results?.length) {
          results.push(...batch.results);
          const list = byId('match-list');
          const scroll = list.scrollTop;
          renderMatches();
          list.scrollTop = scroll;
        }
        heading.textContent = '书源对比 · ' + results.length + ' 个版本 · 搜索中…';
      }
    }
    heading.textContent = '书源对比 · ' + results.length + ' 个版本';
    renderMatches();
    if (!busy) status.textContent = errors.length
      ? '未能完成搜索：' + errors.join('、')
      : (results.length ? '' : '已接入书源没有找到这本书。');
  } catch (error) {
    status.textContent = error.message;
  } finally {
    searching = false;
    setBusy(busy);
  }
});

byId('range-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  clearPartial();
  setBusy(true);
  const current = book;
  const progressPanel = byId('download-progress');
  const progressBar = byId('progress-bar');
  const progressLabel = byId('progress-label');
  let timer;
  let running = true;
  progressPanel.hidden = false;
  progressBar.removeAttribute('value');
  progressLabel.textContent = '正在准备下载…';
  try {
    if (!current.chapters) progressLabel.textContent = '正在读取完整目录…';
    const count = (await loadCatalog(current)).length;
    const start = range.value === 'custom' ? Number(byId('start').value) : 1;
    const end = range.value === 'custom' ? Number(byId('end').value) : (range.value === 'first' ? Math.min(3, count) : count);
    if (start > end || end > count) throw new Error('章节范围无效，本书共 ' + count + ' 章。');
    const run = crypto.randomUUID();
    progressBar.max = end - start + 1;
    progressBar.value = 0;
    progressLabel.textContent = '已处理 0 / ' + progressBar.max + ' 章';
    const poll = async () => {
      try {
        const reply = await fetch('/download/' + current.token + '/progress', {cache: 'no-store'});
        if (!reply.ok || !running) return;
        const {progress} = await reply.json();
        if (!running || progress?.run !== run) return;
        progressBar.value = progress.processed;
        progressLabel.textContent = '已处理 ' + progress.processed + ' / ' + progress.total + ' 章'
          + (progress.failed ? ' · 失败 ' + progress.failed + ' 章' : '');
      } catch {
        // The download response still reports the outcome if polling fails.
      } finally {
        if (running) timer = setTimeout(poll, 500);
      }
    };
    timer = setTimeout(poll, 500);
    const response = await requestDownload('/download/' + current.token + '?start=' + start + '&end=' + end + '&run=' + run);
    if (!response.ok) {
      const data = await response.json();
      if (data.failed) {
        const numbers = data.failed.map(chapter => chapter.number).join('、');
        progressBar.value = data.completed + data.failed.length;
        progressLabel.textContent = '成功 ' + data.completed + ' 章 · 失败 ' + data.failed.length + ' 章';
        download.textContent = '重试失败章节';
        if (data.completed) {
          partialRange = {book: current, start, end};
          byId('partial-download').hidden = false;
        }
        throw new Error('已抓取 ' + data.completed + ' 章。失败章序号：' + numbers);
      }
      throw new Error(data.detail || '下载失败。');
    }
    const suffix = start === 1 && end === count ? '' : ' [' + start + '-' + end + ']';
    const saved = await saveDownload(response, book.title.replace(/[<>:"/\\|?*]/g, '_') + suffix + '.txt');
    download.textContent = '下载 TXT';
    progressBar.value = end - start + 1;
    progressLabel.textContent = saved || '已完成 ' + (end - start + 1) + ' 章';
  } catch (error) {
    progressLabel.textContent = error.message;
  } finally {
    running = false;
    clearTimeout(timer);
    setBusy(false);
  }
});

byId('partial-download').addEventListener('click', async () => {
  if (busy || !partialRange) return;
  const {book: current, start, end} = partialRange;
  if (!confirm('所选范围还有章节缺失。要下载已有章节吗？TXT 中会标出缺失位置。')) return;
  setBusy(true);
  try {
    const response = await requestDownload('/download/' + current.token + '?start=' + start + '&end=' + end + '&partial=true');
    if (!response.ok) throw new Error((await response.json()).detail || '下载失败。');
    const saved = await saveDownload(response, current.title.replace(/[<>:"/\\|?*]/g, '_') + ' [' + start + '-' + end + ' 缺章].txt');
    status.textContent = saved || '已生成缺章版 TXT。';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    setBusy(false);
  }
});
