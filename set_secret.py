#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把推送密钥加密上传到 GitHub Secrets。

用法:
    python3 set_secret.py SCKEY 你的SendKey值
    python3 set_secret.py BARK_URL https://api.day.app/xxxx

需要环境变量 GH_TOKEN 和 GH_REPO（形如 用户名/仓库名）。
密钥经 libsodium 公钥加密后上传，GitHub 侧只有 Actions 运行时能解出来，
网页上永远显示为 ***，任何人（包括你自己）都读不回明文。
"""
import base64
import json
import os
import sys
import urllib.request

from nacl import encoding, public

TOKEN = os.environ.get("GH_TOKEN", "")
REPO = os.environ.get("GH_REPO", "")


def api(path, data=None, method=None):
    url = f"https://api.github.com/repos/{REPO}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "sxkszx-monitor")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})


def encrypt(pubkey_b64, secret_value):
    pk = public.PublicKey(pubkey_b64.encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(secret_value.encode())
    return base64.b64encode(sealed).decode()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    if not TOKEN or not REPO:
        print("请先设置 GH_TOKEN 和 GH_REPO 环境变量")
        sys.exit(1)

    name, value = sys.argv[1], sys.argv[2]

    _, key = api("/actions/secrets/public-key")
    payload = {
        "encrypted_value": encrypt(key["key"], value),
        "key_id": key["key_id"],
    }
    status, _ = api(f"/actions/secrets/{name}", payload, method="PUT")
    if status in (201, 204):
        print(f"✅ {name} 已加密写入 GitHub Secrets（明文未上传）")
    else:
        print(f"❌ 写入失败，HTTP {status}")
        sys.exit(1)

    _, lst = api("/actions/secrets")
    print(f"   当前已配置 {lst.get('total_count', 0)} 个密钥：",
          ", ".join(s["name"] for s in lst.get("secrets", [])))


if __name__ == "__main__":
    main()
