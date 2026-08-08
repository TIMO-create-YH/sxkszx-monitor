#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多渠道推送。全部通过环境变量配置，不填就自动跳过。

  SCKEY        Server酱³（微信推送，最省事，推荐）  https://sct.ftqq.com
  PUSHPLUS     PushPlus token                      https://www.pushplus.plus
  BARK_URL     Bark（iOS）完整推送地址，如 https://api.day.app/xxxx
  FEISHU_HOOK  飞书群机器人 webhook
  DINGTALK_HOOK 钉钉群机器人 webhook
  WXWORK_HOOK  企业微信群机器人 webhook
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / MAIL_TO   邮件
"""

import os
import smtplib
import json
from email.mime.text import MIMEText
from email.header import Header

import requests

TIMEOUT = 20


def load_env():
    """自动读取同目录下的 .env，填一次就永久生效，不用每次 export。
    格式：每行 KEY=VALUE，# 开头为注释。已存在的环境变量优先，不覆盖。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v and not os.getenv(k):
                    os.environ[k] = v
    except Exception as e:
        print(f"（.env 读取失败，忽略：{e}）", flush=True)


load_env()


def build_message(items):
    """把发现的内容拼成推送标题 + 正文（Markdown）。"""
    prio = [i for i in items if i.get("priority") or "投档最低分" in i["title"]
            or "分数线" in i["title"]]
    head = prio[0] if prio else items[0]

    if len(items) == 1:
        title = f"山西录取｜{head['title'][:40]}"
    else:
        title = f"山西录取｜{head['title'][:30]} 等 {len(items)} 条"

    lines = []
    for i in items:
        star = "🔥 " if (i.get("priority") or "投档最低分" in i["title"]) else ""
        lines.append(f"### {star}{i['title']}")
        lines.append(f"**发布：** {i['date']}　[打开官网原文]({i['url']})")
        if i.get("rows"):
            lines.append(f"**已解析投档记录：** {i['rows']} 条（本地表格可直接搜院校）")
        if i.get("attachments"):
            lines.append(f"**附件已下载 {len(i['attachments'])} 个：**")
            for a in i["attachments"][:12]:
                lines.append(f"- {a}")
            if len(i["attachments"]) > 12:
                lines.append(f"- …另有 {len(i['attachments'])-12} 个")
        if i.get("text"):
            snippet = i["text"][:300].replace("\n", " ")
            lines.append(f"> {snippet}")
        lines.append("")
    lines.append("---")
    lines.append("📁 附件已存到本地，官网挤爆也不影响你查。")
    return title, "\n".join(lines)


# ---------------- 各渠道 ----------------
def _serverchan(title, body):
    key = os.getenv("SCKEY")
    if not key:
        return None
    url = (f"https://{key}.push.ft07.com/send/{key}.send"
           if key.startswith("sctp") else f"https://sctapi.ftqq.com/{key}.send")
    r = requests.post(url, data={"title": title[:100], "desp": body}, timeout=TIMEOUT)
    return f"Server酱 {r.status_code}"


def _pushplus(title, body):
    tok = os.getenv("PUSHPLUS")
    if not tok:
        return None
    r = requests.post("http://www.pushplus.plus/send", timeout=TIMEOUT,
                      json={"token": tok, "title": title[:100],
                            "content": body, "template": "markdown"})
    return f"PushPlus {r.status_code}"


def _bark(title, body):
    url = os.getenv("BARK_URL")
    if not url:
        return None
    r = requests.post(url.rstrip("/"), timeout=TIMEOUT,
                      json={"title": title[:100], "body": body[:1000],
                            "group": "山西录取", "sound": "alarm", "level": "timeSensitive"})
    return f"Bark {r.status_code}"


def _feishu(title, body):
    hook = os.getenv("FEISHU_HOOK")
    if not hook:
        return None
    r = requests.post(hook, timeout=TIMEOUT, json={
        "msg_type": "interactive",
        "card": {"header": {"title": {"tag": "plain_text", "content": title[:100]},
                            "template": "red"},
                 "elements": [{"tag": "markdown", "content": body[:4000]}]}})
    return f"飞书 {r.status_code}"


def _dingtalk(title, body):
    hook = os.getenv("DINGTALK_HOOK")
    if not hook:
        return None
    r = requests.post(hook, timeout=TIMEOUT, json={
        "msgtype": "markdown",
        "markdown": {"title": title[:60], "text": f"## {title}\n\n{body[:4000]}"}})
    return f"钉钉 {r.status_code}"


def _wxwork(title, body):
    hook = os.getenv("WXWORK_HOOK")
    if not hook:
        return None
    r = requests.post(hook, timeout=TIMEOUT, json={
        "msgtype": "markdown", "markdown": {"content": f"## {title}\n\n{body[:3800]}"}})
    return f"企业微信 {r.status_code}"


def _mail(title, body):
    host, user = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER")
    pwd, to = os.getenv("SMTP_PASS"), os.getenv("MAIL_TO")
    if not all([host, user, pwd, to]):
        return None
    port = int(os.getenv("SMTP_PORT", "465"))
    html = "<br>".join(body.split("\n"))
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = user
    msg["To"] = to
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        s = smtplib.SMTP(host, port, timeout=30); s.starttls()
    s.login(user, pwd)
    s.sendmail(user, to.split(","), msg.as_string())
    s.quit()
    return "邮件 已发送"


CHANNELS = [_serverchan, _pushplus, _bark, _feishu, _dingtalk, _wxwork, _mail]


def send_all(items):
    if not items:
        return
    load_env()  # 每次推送前重读 .env，中途配好 key 也能立刻生效，无需重启
    title, body = build_message(items)
    print("\n" + "=" * 60)
    print("【推送内容预览】")
    print(title)
    print("-" * 60)
    print(body[:1500])
    print("=" * 60 + "\n", flush=True)

    sent = []
    for fn in CHANNELS:
        try:
            r = fn(title, body)
            if r:
                sent.append(r)
        except Exception as e:
            sent.append(f"{fn.__name__} 失败:{e}")
    if sent:
        print("推送结果:", " | ".join(sent), flush=True)
    else:
        print("（未配置任何推送渠道，仅本地记录。设置 SCKEY 即可收微信推送）", flush=True)


if __name__ == "__main__":
    send_all([{
        "title": "【测试】山西省2026年普通高校招生普通专科（高职）批院校专业组投档最低分",
        "date": "测试", "url": "http://www.sxkszx.cn/news/ptgk/index.html",
        "text": "这是一条推送连通性测试。", "attachments": ["测试_历史类.pdf", "测试_物理类.pdf"],
        "rows": 1234, "priority": True}])
