#!/usr/bin/env python3
"""通过代理抓取 tweet 内容"""
import urllib.request
import json
import re
import sys
import os

os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1087"

proxy = urllib.request.ProxyHandler({"https": "http://127.0.0.1:1087"})
opener = urllib.request.build_opener(proxy)
urllib.request.install_opener(opener)

tweet_id = "2058748970302923105"

# 方法1: 用 Twitter oEmbed API
url = f"https://publish.twitter.com/oembed?url=https://x.com/damobianyuan/status/{tweet_id}"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        html = data.get("html", "")
        # 提取文本
        text = re.sub(r'<[^>]+>', '', html)
        author = data.get("author_name", "")
        print(f"作者: {author}")
        print(f"内容: {text[:1000]}")
        sys.exit(0)
except Exception as e:
    print(f"oEmbed 失败: {e}")

# 方法2: 尝试 Twitter API v2 (需要 bearer token)
# 没有 token 所以跳过

# 方法3: 尝试 nitter
for host in ["nitter.net", "nitter.lacontrevoie.fr", "nitter.privacydev.net"]:
    try:
        url = f"https://{host}/damobianyuan/status/{tweet_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode()
            # 提取 tweet 文本
            patterns = [
                r'class="tweet-content"[^>]*>(.*?)</div>',
                r'class="content"[^>]*>.*?<p[^>]*>(.*?)</p>',
                r'<div class="tweet-text"[^>]*>(.*?)</div>',
            ]
            for p in patterns:
                m = re.search(p, html, re.DOTALL)
                if m:
                    text = re.sub(r'<[^>]+>', '', m.group(1))
                    print(f"来源: {host}")
                    print(f"内容: {text[:2000]}")
                    sys.exit(0)
            print(f"{host}: 未找到 tweet 内容")
    except Exception as e:
        print(f"{host}: {e}")

print("\n所有方式都失败了。你可以直接把 tweet 文本发给我。")
