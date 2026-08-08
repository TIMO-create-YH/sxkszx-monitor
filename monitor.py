#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
山西招生考试网 —— 录取投档线秒级监控器

核心思路（为什么不用"抢网"）：
  1. 只轮询 20KB 的栏目列表页（0.2 秒返回），对官网几乎零压力；
  2. 一旦发现新公告，立刻把公告页 + 全部 PDF 附件"整包搬回本地"；
  3. 之后你查分看的是本地副本 + 本地可搜索表格，
     官网被十万人挤爆的时候，你已经在离线翻表了。

用法：
  python3 monitor.py --once        # 跑一次（GitHub Actions / crontab 模式）
  python3 monitor.py --loop 120    # 常驻，每 120 秒轮询一次
  python3 monitor.py --backfill    # 把当前列表页已有的历史投档线全部抓回来
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

BASE = "http://www.sxkszx.cn"
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
PDF_DIR = os.path.join(DATA, "pdf")
JSON_DIR = os.path.join(DATA, "json")
STATE_FILE = os.path.join(DATA, "state.json")
CONFIG_FILE = os.path.join(ROOT, "config.json")

CST = timezone(timedelta(hours=8))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}


def now():
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{now()}] {msg}", flush=True)


# --------------------------------------------------------------------------
# 配置 / 状态
# --------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "channels": ["ptgk"],
    "keywords": ["投档最低分", "控制分数线", "征集志愿", "录取", "分段统计", "计划"],
    "priority_keywords": ["投档最低分", "控制分数线"],
    "download_attachments": True,
    "parse_pdf": True,
    "probe_files": [],
    "timeout": 30,
}

CHANNEL_NAMES = {
    "ptgk": "普通高考",
    "dksxks": "对口升学",
    "zsbks": "专升本考试",
    "zhxw": "工作动态",
    "crgk": "成人高考",
    "yjsks": "研究生考试",
    "zzks": "中考",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"seen": {}, "probed": {}, "last_run": None}


def save_state(state):
    os.makedirs(DATA, exist_ok=True)
    state["last_run"] = now()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# 抓取
# --------------------------------------------------------------------------
def fetch(url, timeout=30, binary=False):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    if binary:
        return r.content
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def parse_list(html):
    """解析栏目列表页。站点 href 不带引号，需要宽松匹配。"""
    items = []
    blocks = re.findall(
        r'<td class="newsbodylist1">(.*?)</td>\s*<td class="newsbodydate">(.*?)</td>',
        html, re.S)
    for body, datecell in blocks:
        m = re.search(r'href=["\']?([^\s"\'>]+\.html)', body)
        if not m:
            continue
        url = urllib.parse.urljoin(BASE, m.group(1))
        title = re.sub(r"<[^>]+>", "", body)
        title = title.replace("&nbsp;", " ").strip()
        d = re.search(r"\[([^\]]+)\]", datecell)
        date = d.group(1).strip() if d else ""
        if title:
            items.append({"title": title, "url": url, "date": date})
    return items


def extract_attachments(html, page_url):
    """提取公告页中的 PDF/Excel/Word 附件链接（去重、保序）。"""
    urls = re.findall(
        r'href=["\']?([^"\'>\s]+\.(?:pdf|xls|xlsx|doc|docx|zip))', html, re.I)
    out, seen = [], set()
    for u in urls:
        full = urllib.parse.urljoin(page_url, u.replace("&amp;", "&"))
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def article_text(html):
    """抽取公告正文纯文本。"""
    h = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", "", h, flags=re.S | re.I)
    body = re.search(r'录入日期(.*?)(?:【|</body>)', h, re.S)
    seg = body.group(1) if body else h
    txt = re.sub(r"<[^>]+>", "\n", seg)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&")
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    return "\n".join(lines)


def safe_name(url):
    name = urllib.parse.unquote(url.split("/")[-1])
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def download(url, dest_dir, timeout=120):
    os.makedirs(dest_dir, exist_ok=True)
    fname = safe_name(url)
    path = os.path.join(dest_dir, fname)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path, False
    # 中文路径需要转义
    parts = urllib.parse.urlsplit(url)
    quoted = urllib.parse.urlunsplit((
        parts.scheme, parts.netloc,
        urllib.parse.quote(parts.path, safe="/"),
        parts.query, parts.fragment))
    r = requests.get(quoted, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path, True


# --------------------------------------------------------------------------
# PDF -> 结构化数据
# --------------------------------------------------------------------------
# 专业组片段：括号可能因 PDF 排版被截断而不闭合，故 \) 设为可选
GROUP = r"第\s*\d+\s*组(?:\s*[（(][^)）]*[)）]?)?"
# 完整行：代号 院校名 科类 专业组 分数
ROW_FULL = re.compile(rf"^\s*(\d{{4}})\s+(.+?)\s+({GROUP})\s+([\d]+\.[\d]+)\s*$")
# 缺额行：代号 院校名 科类 专业组（无分数 —— 该组未投满，需征集志愿）
ROW_EMPTY = re.compile(rf"^\s*(\d{{4}})\s+(.+?)\s+({GROUP})\s*$")


def _split_school_subject(blob):
    """把 '首都师范大学科德学院     物理类' 拆成 (院校, 科类)。"""
    parts = re.split(r"\s{2,}", blob.strip())
    if len(parts) >= 2:
        return re.sub(r"\s+", "", "".join(parts[:-1])), re.sub(r"\s+", "", parts[-1])
    # 兜底：按已知科类词尾切
    s = re.sub(r"\s+", "", blob)
    for kw in ("物理类", "历史类", "体育类", "舞蹈类", "书法类", "美术与设计类",
               "播音与主持类", "服装表演", "戏剧影视表演", "戏剧影视导演",
               "音乐表演", "音乐教育", "综合改革"):
        if s.endswith(kw):
            return s[: -len(kw)], kw
    return s, ""


def parse_score_pdf(pdf_path):
    """把投档最低分 PDF 解析成结构化记录。

    注意：部分专业组在原始 PDF 中分数列为空，代表该组未投满、
    将进入征集志愿。这类记录同样保留，标记 vacancy=True。
    """
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, timeout=300)
        text = out.stdout.decode("utf-8", errors="ignore")
    except Exception as e:
        log(f"  ! pdftotext 失败: {e}")
        return None

    batch = ""
    mb = re.search(r"批次[:：]\s*(\S+)", text)
    if mb:
        batch = mb.group(1)

    rows, vacancy = [], 0
    for line in text.split("\n"):
        if not line.strip() or "院校名称" in line or "投档最低分" in line:
            continue
        if not re.match(r"^\s*\d{4}\s+\S", line):
            continue

        m = ROW_FULL.match(line)
        if m:
            code, blob, group, score = m.groups()
            school, subject = _split_school_subject(blob)
            rows.append({
                "code": code, "school": school, "subject": subject,
                "group": re.sub(r"\s+", "", group),
                "score": score, "min_score": score.split(".")[0],
                "vacancy": False,
            })
            continue

        m = ROW_EMPTY.match(line)
        if m:
            code, blob, group = m.groups()
            school, subject = _split_school_subject(blob)
            rows.append({
                "code": code, "school": school, "subject": subject,
                "group": re.sub(r"\s+", "", group),
                "score": "", "min_score": "", "vacancy": True,
            })
            vacancy += 1

    return {"batch": batch, "file": os.path.basename(pdf_path),
            "rows": rows, "vacancy_count": vacancy}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def handle_article(item, cfg, state):
    """抓取公告详情 + 附件 + 解析，返回推送用的摘要。"""
    log(f"  → 抓取详情: {item['title']}")
    html = fetch(item["url"], cfg["timeout"])
    text = article_text(html)
    atts = extract_attachments(html, item["url"]) if cfg["download_attachments"] else []

    key = hashlib.md5(item["url"].encode()).hexdigest()[:10]
    sub = os.path.join(PDF_DIR, f"{item['date'].replace('年','-').replace('月','-').replace('日','')}_{key}")

    saved, parsed_files, total_rows = [], [], 0
    for a in atts:
        try:
            path, is_new = download(a, sub, cfg["timeout"] * 4)
            saved.append(os.path.basename(path))
            log(f"    ✓ 附件 {'新下载' if is_new else '已存在'}: {os.path.basename(path)}")
            if cfg["parse_pdf"] and path.lower().endswith(".pdf"):
                res = parse_score_pdf(path)
                if res and res["rows"]:
                    os.makedirs(JSON_DIR, exist_ok=True)
                    jp = os.path.join(JSON_DIR, os.path.basename(path) + ".json")
                    with open(jp, "w", encoding="utf-8") as f:
                        json.dump(res, f, ensure_ascii=False)
                    parsed_files.append(os.path.basename(jp))
                    total_rows += len(res["rows"])
                    log(f"      ↳ 解析出 {len(res['rows'])} 条投档记录")
        except Exception as e:
            log(f"    ! 附件失败 {a}: {e}")

    # 存正文
    os.makedirs(sub, exist_ok=True)
    with open(os.path.join(sub, "公告正文.txt"), "w", encoding="utf-8") as f:
        f.write(f"{item['title']}\n{item['date']}\n{item['url']}\n\n{text}")
    with open(os.path.join(sub, "原始页面.html"), "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "title": item["title"],
        "date": item["date"],
        "url": item["url"],
        "text": text[:600],
        "attachments": saved,
        "parsed": parsed_files,
        "rows": total_rows,
        "local_dir": sub,
    }


def probe_files(cfg, state):
    """文件直探：官网常常先把 PDF 传上服务器、再挂公告。
    用 HEAD 请求探测预测文件名，可比公告早几分钟到几十分钟拿到数据。"""
    hits = []
    for url in cfg.get("probe_files", []):
        if state["probed"].get(url):
            continue
        parts = urllib.parse.urlsplit(url)
        quoted = urllib.parse.urlunsplit((
            parts.scheme, parts.netloc,
            urllib.parse.quote(parts.path, safe="/"), parts.query, parts.fragment))
        try:
            r = requests.head(quoted, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                log(f"  ★ 文件直探命中: {safe_name(url)}")
                sub = os.path.join(PDF_DIR, "直探_" + datetime.now(CST).strftime("%m%d"))
                path, _ = download(url, sub, 180)
                res = parse_score_pdf(path) if path.lower().endswith(".pdf") else None
                if res and res["rows"]:
                    os.makedirs(JSON_DIR, exist_ok=True)
                    with open(os.path.join(JSON_DIR, os.path.basename(path) + ".json"),
                              "w", encoding="utf-8") as f:
                        json.dump(res, f, ensure_ascii=False)
                state["probed"][url] = now()
                hits.append({
                    "title": f"【文件直探】{safe_name(url)}",
                    "date": now(), "url": url, "text": "官网文件已上传（公告可能尚未挂出）",
                    "attachments": [safe_name(url)],
                    "parsed": [], "rows": len(res["rows"]) if res else 0,
                    "local_dir": sub,
                })
        except Exception:
            pass
    return hits


def run_once(cfg, state, backfill=False, notify_fn=None):
    found = []

    for ch in cfg["channels"]:
        url = f"{BASE}/news/{ch}/index.html"
        try:
            t0 = time.time()
            html = fetch(url, cfg["timeout"])
            cost = time.time() - t0
        except Exception as e:
            log(f"! 栏目 {ch} 抓取失败: {e}")
            continue

        items = parse_list(html)
        log(f"栏目 {CHANNEL_NAMES.get(ch, ch)}: {len(items)} 条 "
            f"({len(html)//1024}KB / {cost:.2f}s)")

        for it in items:
            if not any(k in it["title"] for k in cfg["keywords"]):
                continue
            if it["url"] in state["seen"]:
                continue
            if backfill and not any(k in it["title"] for k in cfg["priority_keywords"]):
                state["seen"][it["url"]] = {"title": it["title"], "at": now()}
                continue

            is_priority = any(k in it["title"] for k in cfg["priority_keywords"])
            log(f"{'★★★ 重点' if is_priority else '·  '} 新公告: {it['title']} [{it['date']}]")
            try:
                info = handle_article(it, cfg, state)
                info["priority"] = is_priority
                found.append(info)
                state["seen"][it["url"]] = {"title": it["title"], "at": now()}
            except Exception as e:
                log(f"! 处理失败: {e}")

    if not backfill:
        found.extend(probe_files(cfg, state))

    save_state(state)

    if found and notify_fn:
        notify_fn(found)
    return found


def main():
    ap = argparse.ArgumentParser(description="山西招生考试网 录取投档线监控")
    ap.add_argument("--once", action="store_true", help="只跑一次")
    ap.add_argument("--loop", type=int, metavar="SEC", help="常驻轮询，间隔秒数")
    ap.add_argument("--duration", type=int, metavar="SEC",
                    help="配合 --loop 使用：跑满指定秒数后优雅退出。"
                         "用于 GitHub Actions 在一次任务内做密集探测，"
                         "绕开 cron 最小 5 分钟粒度的限制")
    ap.add_argument("--backfill", action="store_true", help="补抓列表页已有的历史投档线")
    ap.add_argument("--no-notify", action="store_true", help="不推送")
    args = ap.parse_args()

    cfg = load_config()
    state = load_state()
    os.makedirs(DATA, exist_ok=True)

    notify_fn = None
    if not args.no_notify:
        try:
            from notify import send_all, load_env
            load_env()  # 读取 .env，让下面的自检能拿到配置
            notify_fn = send_all
            # 启动时明确告知推送状态，避免"以为配好了其实没生效"
            ready = []
            if os.getenv("SCKEY"):
                ready.append("Server酱(微信)")
            if os.getenv("PUSHPLUS"):
                ready.append("PushPlus(微信)")
            if os.getenv("BARK_URL"):
                ready.append("Bark(iOS)")
            if os.getenv("FEISHU_HOOK"):
                ready.append("飞书")
            if os.getenv("DINGTALK_HOOK"):
                ready.append("钉钉")
            if os.getenv("WXWORK_HOOK"):
                ready.append("企业微信")
            if os.getenv("SMTP_HOST") and os.getenv("MAIL_TO"):
                ready.append("邮件")
            if ready:
                log(f"推送已就绪 → {' + '.join(ready)}")
            else:
                log("! 未配置推送渠道，发现新内容只会记到本地。"
                    "运行 bash setup_push.sh 一分钟配好微信推送")
        except Exception as e:
            log(f"（推送模块未启用: {e}）")

    if args.backfill:
        log("=== 补抓模式：拉取列表页已有的全部投档线 ===")
        res = run_once(cfg, state, backfill=True, notify_fn=None)
        log(f"=== 补抓完成，共处理 {len(res)} 篇 ===")
    elif args.loop:
        if args.duration:
            end_at = time.time() + args.duration
            log(f"=== 密集探测窗口：每 {args.loop} 秒一次，"
                f"持续 {args.duration} 秒后自动退出 ===")
        else:
            end_at = None
            log(f"=== 常驻监控启动，每 {args.loop} 秒轮询一次，Ctrl+C 退出 ===")
        rounds = 0
        while True:
            try:
                run_once(cfg, state, notify_fn=notify_fn)
                rounds += 1
            except KeyboardInterrupt:
                log("已退出"); break
            except Exception as e:
                log(f"! 本轮异常: {e}")
            if end_at is not None:
                # 剩余时间不够下一轮就收工，避免被外部强杀
                if time.time() + args.loop >= end_at:
                    log(f"=== 窗口结束，本次共探测 {rounds} 轮 ===")
                    break
            try:
                time.sleep(args.loop)
            except KeyboardInterrupt:
                log("已退出"); break
    else:
        res = run_once(cfg, state, notify_fn=notify_fn)
        log(f"=== 本轮发现 {len(res)} 条新内容 ===")

    # 每次都重建查询站点
    try:
        from build_site import build
        build()
    except Exception as e:
        log(f"（站点生成跳过: {e}）")


if __name__ == "__main__":
    main()
