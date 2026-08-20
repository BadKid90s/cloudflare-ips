# -*- coding: utf-8 -*-
"""
CloudFlare 优选 IP 解析脚本
从 https://api.uouin.com/cloudflare.html 抓取表格，
按线路(电信/联通/移动/多线/IPV6)各取速度最高的 3 条记录，
拼接为:  IP:PORT#线路-速度(带单位)

用法:
    python cloudflare_ips.py                # 在线抓取, 默认端口 443
    python cloudflare_ips.py --port 2053    # 指定端口
    python cloudflare_ips.py --html cloudflare.html   # 解析本地已保存的页面
    python cloudflare_ips.py --top 5        # 每个线路取前 N 条
"""

import argparse
import re
import sys
import urllib.request

URL = "https://api.uouin.com/cloudflare.html"
DEFAULT_PORT = "443"   # CloudFlare 常见端口: 443/2053/2083/2087/2096/8443, 可按需修改

# 线路在页面上的出现顺序, 输出时保持该顺序
LINE_ORDER = ["电信", "联通", "移动", "多线", "IPV6"]


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "ignore")


def parse_table(html: str) -> list[dict]:
    """解析 HTML 表格, 返回 [{line, ip, loss, latency, speed}] 列表"""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S)
    data = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(cells) < 6:
            continue
        speed_m = re.search(r"([\d.]+)([a-zA-Z/%]*)", cells[5])   # 速度列, 如 "56.58mb/s"
        if not speed_m:
            continue
        data.append({
            "line":  cells[1],                          # 线路
            "ip":    cells[2],                          # IP
            "loss":  cells[3],                          # 丢包率
            "latency": cells[4],                        # 延迟
            "speed": float(speed_m.group(1)),           # 速度(纯数值, 用于排序)
            "speed_raw": speed_m.group(0),              # 速度(原始字符串, 带单位)
        })
    return data


def format_ip_port(ip: str, port: str) -> str:
    """IPv6 需加方括号: [2606:4700::1]:443"""
    if ":" in ip:
        return f"[{ip}]:{port}"
    return f"{ip}:{port}"


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudFlare 优选IP按线路取速度TopN并拼接")
    parser.add_argument("--port", default=DEFAULT_PORT, help="拼接端口, 默认 443")
    parser.add_argument("--html", help="使用本地 HTML 文件解析(跳过网络抓取)")
    parser.add_argument("--top", type=int, default=3, help="每个线路取速度最高的前 N 条, 默认 3")
    parser.add_argument("--out", default="cloudflare_top.txt", help="结果输出文件, 默认 cloudflare_top.txt")
    args = parser.parse_args()

    html = open(args.html, encoding="utf-8", errors="ignore").read() if args.html else fetch_html(URL)
    data = parse_table(html)
    if not data:
        print("未解析到任何数据, 请检查页面结构", file=sys.stderr)
        sys.exit(1)
    print(f"共解析 {len(data)} 条记录\n")

    results = []
    for line in LINE_ORDER:
        items = [d for d in data if d["line"] == line]
        if not items:
            print(f"[{line}] 无数据")
            continue
        top = sorted(items, key=lambda d: d["speed"], reverse=True)[: args.top]
        print(f"===== {line} (共{len(items)}条, 取速度Top{len(top)}) =====")
        for d in top:
            # 速度按表格原始单位输出(如 56.58mb/s), 不做单位转换
            s = f"{format_ip_port(d['ip'], args.port)}#{line}-{d['speed_raw']}"
            results.append(s)
            print(f"  {d['ip']:<45} {d['loss']:<8} {d['latency']:<10} {d['speed']:g}mb/s")

    print(f"\n===== 拼接结果({len(results)} 条) =====")
    for s in results:
        print(s)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(results) + "\n")
        print(f"\n已保存到: {args.out}")


if __name__ == "__main__":
    main()
