# -*- coding: utf-8 -*-
"""
CloudFlare 优选 IP 解析脚本
从 https://api.uouin.com/cloudflare.html 抓取表格，
按线路(电信/联通/移动/多线/IPV6)与本地结果合并，各保留速度最高的 10 条。
新测速高于本地则加入/更新，低于本地则淘汰。

用法:
    python cloudflare_ips.py                # 打开网页等待刷新后解析, 默认端口 443
    python cloudflare_ips.py --port 2053    # 指定端口
    python cloudflare_ips.py --wait 2000    # 打开页面后等待毫秒数, 默认 2000
    python cloudflare_ips.py --html cloudflare.html   # 解析本地已保存的页面
    python cloudflare_ips.py --top 10       # 每个线路累计保留前 N 条
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

URL = "https://api.uouin.com/cloudflare.html"
DEFAULT_PORT = "443"   # CloudFlare 常见端口: 443/2053/2083/2087/2096/8443, 可按需修改
DEFAULT_WAIT_MS = 2000
DEFAULT_TOP = 10

# 线路在页面上的出现顺序, 输出时保持该顺序
LINE_ORDER = ["电信", "联通", "移动", "多线", "IPV6"]

OUTPUT_LINE_RE = re.compile(
    r"^(?:\[(?P<ipv6>[^\]]+)\]|(?P<ipv4>[^:#\[]+)):(?P<port>\d+)#(?P<line>[^-]+)-(?P<speed_raw>.+)$"
)


def find_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    return None


def fetch_html(url: str, wait_ms: int = DEFAULT_WAIT_MS) -> str:
    """用无头 Chrome 打开页面, 等待 JS 刷新表格后再取 DOM。"""
    chrome = find_chrome()
    if not chrome:
        print("未找到 Chrome/Chromium, 无法加载页面刷新后的数据", file=sys.stderr)
        sys.exit(1)

    print(f"打开页面并等待 {wait_ms}ms: {url}")
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--dump-dom",
        f"--virtual-time-budget={wait_ms}",
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        print("浏览器打开页面超时", file=sys.stderr)
        sys.exit(1)

    html = proc.stdout.decode("utf-8", "ignore")
    if "<tr" not in html:
        err = proc.stderr.decode("utf-8", "ignore").strip()
        print("浏览器未返回表格 DOM", file=sys.stderr)
        if err:
            print(err[-1000:], file=sys.stderr)
        sys.exit(1)
    return html


def parse_speed(speed_raw: str) -> float | None:
    speed_m = re.search(r"([\d.]+)", speed_raw)
    if not speed_m:
        return None
    return float(speed_m.group(1))


def parse_table(html: str) -> list[dict]:
    """解析 HTML 表格, 返回 [{line, ip, loss, latency, speed, speed_raw}] 列表"""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S)
    data = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(cells) < 6:
            continue
        speed = parse_speed(cells[5])   # 速度列, 如 "56.58mb/s"
        if speed is None:
            continue
        speed_m = re.search(r"([\d.]+)([a-zA-Z/%]*)", cells[5])
        data.append({
            "line":  cells[1],                          # 线路
            "ip":    cells[2],                          # IP
            "loss":  cells[3],                          # 丢包率
            "latency": cells[4],                        # 延迟
            "speed": speed,                             # 速度(纯数值, 用于排序)
            "speed_raw": speed_m.group(0) if speed_m else cells[5],
        })
    return data


def parse_output_line(text: str) -> dict | None:
    """解析 ips.txt 一行: IP:PORT#线路-速度 或 [IPv6]:PORT#线路-速度"""
    text = text.strip()
    if not text or text.startswith("#"):
        return None
    m = OUTPUT_LINE_RE.match(text)
    if not m:
        return None
    speed = parse_speed(m.group("speed_raw"))
    if speed is None:
        return None
    ip = m.group("ipv6") or m.group("ipv4")
    return {
        "line": m.group("line"),
        "ip": ip,
        "loss": "",
        "latency": "",
        "speed": speed,
        "speed_raw": m.group("speed_raw"),
    }


def load_existing(path: str) -> list[dict]:
    if not path or not os.path.isfile(path):
        return []
    records = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for raw in f:
            item = parse_output_line(raw)
            if item:
                records.append(item)
    return records


def merge_by_line(existing: list[dict], incoming: list[dict], top: int) -> list[dict]:
    """按线路合并: 同 IP 保留更高网速, 再按网速取前 N 条。"""
    merged: list[dict] = []
    for line in LINE_ORDER:
        pool: dict[str, dict] = {}
        for d in existing:
            if d["line"] == line:
                pool[d["ip"]] = d
        for d in incoming:
            if d["line"] != line:
                continue
            old = pool.get(d["ip"])
            if old is None or d["speed"] > old["speed"]:
                pool[d["ip"]] = d
        ranked = sorted(pool.values(), key=lambda d: d["speed"], reverse=True)[:top]
        merged.extend(ranked)
    return merged


def format_ip_port(ip: str, port: str) -> str:
    """IPv6 需加方括号: [2606:4700::1]:443"""
    if ":" in ip:
        return f"[{ip}]:{port}"
    return f"{ip}:{port}"


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudFlare 优选IP按线路累计速度TopN并拼接")
    parser.add_argument("--port", default=DEFAULT_PORT, help="拼接端口, 默认 443")
    parser.add_argument("--html", help="使用本地 HTML 文件解析(跳过网络抓取)")
    parser.add_argument("--wait", type=int, default=DEFAULT_WAIT_MS, help="打开页面后等待毫秒数, 默认 2000")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="每个线路累计保留速度最高的前 N 条, 默认 10")
    parser.add_argument("--out", default="cloudflare_top.txt", help="结果输出文件, 默认 cloudflare_top.txt")
    args = parser.parse_args()

    html = open(args.html, encoding="utf-8", errors="ignore").read() if args.html else fetch_html(URL, args.wait)
    incoming = parse_table(html)
    if not incoming:
        print("未解析到任何数据, 请检查页面结构", file=sys.stderr)
        sys.exit(1)
    print(f"共解析 {len(incoming)} 条记录")

    existing = load_existing(args.out)
    print(f"本地已有 {len(existing)} 条记录\n")
    merged = merge_by_line(existing, incoming, args.top)

    results = []
    for line in LINE_ORDER:
        items = [d for d in merged if d["line"] == line]
        if not items:
            print(f"[{line}] 无数据")
            continue
        print(f"===== {line} (累计{len(items)}条, 按速度排序) =====")
        for d in items:
            s = f"{format_ip_port(d['ip'], args.port)}#{line}-{d['speed_raw']}"
            results.append(s)
            extra = f"{d['loss']:<8} {d['latency']:<10}" if d.get("loss") or d.get("latency") else ""
            print(f"  {d['ip']:<45} {extra}{d['speed']:g}mb/s")

    print(f"\n===== 拼接结果({len(results)} 条) =====")
    for s in results:
        print(s)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(results) + "\n")
        print(f"\n已保存到: {args.out}")


if __name__ == "__main__":
    main()
