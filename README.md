# cloudflare-ips

从 [CloudFlare 优选 IP](https://api.uouin.com/cloudflare.html) 抓取测速表格，按线路（电信 / 联通 / 移动 / 多线 / IPV6）各取速度最高的 3 条，写入 `ips.txt`。

GitHub Actions 每天北京时间 **06:00**、**18:00** 自动更新；有变更时提交并清除 jsDelivr 缓存。

## 订阅地址

jsDelivr（推荐）：

```text
https://cdn.jsdelivr.net/gh/BadKid90s/cloudflare-ips@main/ips.txt
```

GitHub Raw：

```text
https://raw.githubusercontent.com/BadKid90s/cloudflare-ips/main/ips.txt
```

`ips.txt` 每行格式：

```text
IP:PORT#线路-速度
```

IPv6 会写成 `[IPv6]:PORT#线路-速度`。

## 本地运行

需要已安装 Chrome / Chromium（页面数据由 JS 刷新，直接下载 HTML 是过期快照）。Python 3.10+，无第三方依赖。

```bash
python cloudflare_ips.py --out ips.txt
```

常用参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `--out` | 结果文件 | `cloudflare_top.txt` |
| `--port` | 拼接端口 | `443` |
| `--top` | 每条线路取前 N 条 | `3` |
| `--wait` | 打开页面后等待毫秒数 | `2000` |
| `--html` | 解析本地 HTML，跳过浏览器 | — |

## 自动更新

工作流：`.github/workflows/update-ips.yml`

1. 无头 Chrome 打开页面，等待 2 秒后解析
2. 覆盖写入 `ips.txt`，有变化则提交推送
3. 等待 3 秒后 purge jsDelivr 的 `@main` 与无版本号两个地址

也可在仓库 Actions 页手动 **Run workflow**。

## License

[Apache License 2.0](LICENSE)
