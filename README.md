# 山西录取投档线 · 秒级监控与离线查询

一套自动盯着山西招生考试网、**新数据一发布就抓回本地并推送到你手机**的系统。
官网被十万人挤爆的时候，你翻的是自己电脑里的离线表格。

---

## 它解决什么问题

| 痛点 | 这套系统怎么做 |
|---|---|
| 不知道啥时候发布，得手动反复刷新 | 每 1~5 分钟自动查一次，发布即推送微信 |
| 一发布官网就卡死、PDF 打不开 | 发布瞬间就把 PDF 全部搬到本地，你查的是本地副本 |
| PDF 几十页翻着找学校太痛苦 | 自动解析成可搜索表格，输院校名秒出 |
| 想知道哪些专业组没招满 | 自动识别缺额组，填征集志愿直接用 |

**核心逻辑不是"抢网"，是"错峰"**：监控只请求 20KB 的列表页（0.2 秒），
对官网压力几乎为零；一旦命中就整包下载，之后全部离线操作。

---

## 快速开始

### 1. 本地跑（最简单，5 秒上手）

```bash
pip install requests
sudo apt install poppler-utils        # PDF 解析，macOS 用 brew install poppler

python3 monitor.py --backfill         # 先把已发布的历史数据全抓回来
python3 monitor.py --loop 120         # 常驻监控，每 2 分钟查一次
```

然后**双击 `site/index.html`** —— 离线查询页，断网也能用。

### 2. 配上微信推送（推荐，1 分钟）

**最省事的办法 —— 跑配置向导，它会一步步问你：**

```bash
bash setup_push.sh
```

选 `1`（Server酱），去 [sct.ftqq.com](https://sct.ftqq.com) 微信扫码登录复制 SendKey 粘进去。
脚本会自动保存到 `.env` 并**立刻发一条测试消息**——微信收到就说明配好了。

> `.env` 填一次永久生效，不用每次 `export`。权限已设为 600，只有你能读。
> 监控在跑的时候中途配也行，**下次推送自动读取新配置，无需重启**。

<details>
<summary>不想用向导？手动配也可以</summary>

```bash
echo 'SCKEY=你的SendKey' > .env    # 或 export SCKEY="你的SendKey"
python3 notify.py                  # 测一下，微信应该立刻收到
python3 monitor.py --loop 60
```
</details>

支持的推送渠道（填哪个用哪个，全部可选）：

| 环境变量 | 渠道 | 获取地址 |
|---|---|---|
| `SCKEY` | Server酱³ 微信推送 ★推荐 | https://sct.ftqq.com |
| `PUSHPLUS` | PushPlus 微信 | https://www.pushplus.plus |
| `BARK_URL` | Bark（iPhone，可强提醒） | App Store 搜 Bark |
| `FEISHU_HOOK` | 飞书群机器人 | 群设置 → 机器人 |
| `DINGTALK_HOOK` | 钉钉群机器人 | 群设置 → 机器人 |
| `WXWORK_HOOK` | 企业微信群机器人 | 群设置 → 机器人 |
| `SMTP_*` / `MAIL_TO` | 邮件 | 你的邮箱 SMTP |

**怎么确认推送真的生效了？** 启动监控时看第一行日志：

- `推送已就绪 → Server酱(微信)` ← 配好了
- `! 未配置推送渠道，发现新内容只会记到本地` ← 没配好，重跑 `bash setup_push.sh`

### 给云端（GitHub Actions）也配上推送

云端读不到本地的 `.env`，密钥要单独存进 GitHub 的加密保险箱：

```bash
export GH_TOKEN="你的GitHub令牌"
export GH_REPO="你的用户名/sxkszx-monitor"
python3 set_secret.py SCKEY 你的SendKey
```

密钥经 libsodium 公钥加密后才上传，网页上永远显示为 `***`，
只有 Actions 运行时能解出来用。同样支持上面表格里的所有渠道名。

### 3. 挂云端 7×24（不用开电脑）

**本仓库已经部署完毕**，无需再配：

| 项目 | 地址 |
|---|---|
| 查询页 | https://timo-create-yh.github.io/sxkszx-monitor/ |
| 运行记录 | https://github.com/TIMO-create-YH/sxkszx-monitor/actions |

自动任务每 5 分钟触发一次，**单次任务内部再跑 4.5 分钟密集探测（每 40 秒一轮）**，
抓到新数据自动提交回仓库并重新发布查询页。

<details>
<summary>想自己另建一个？三步</summary>

1. 仓库 → Settings → Secrets and variables → Actions → 添加 `SCKEY`
2. 仓库 → Settings → Actions → General → Workflow permissions → 选 **Read and write**
3. 仓库 → Settings → Pages → Source 选 **GitHub Actions**
</details>

**说句实话**：GitHub Actions 的定时任务在高峰期常有 5~15 分钟排队延迟，
这是免费额度的固有限制。所以才加了任务内密集探测窗口把实际密度拉回 40 秒级。
真要抢那几分钟，再在自己电脑上跑 `--loop 60`，两边同时开也不冲突。

---

## 实测数据（2026-08-08）

```
栏目列表页        20 KB / 0.17 秒
本科批物理类 PDF  62 页 / 0.33 秒下载
全量补抓          7 篇公告 / 27 个 PDF / 9 秒完成
解析结果          8619 条投档记录，含 210 个缺额组
解析准确率        100%（逐行核对，零漏行）
```

---

## 目录结构

```
sxkszx-monitor/
├── monitor.py          主程序：轮询 → 下载 → 解析 → 推送
├── notify.py           7 种推送渠道（自动读取 .env）
├── build_site.py       生成离线查询页
├── config.json         监控栏目、关键词、文件直探清单
├── setup_push.sh       ★ 推送配置向导，跑一次搞定微信推送
├── start.sh            ★ 一键启动菜单
├── .env                你的推送密钥（跑向导后自动生成，勿外传）
├── data/
│   ├── pdf/            按日期归档的原始 PDF + 公告正文
│   ├── json/           解析后的结构化数据
│   ├── state.json      已处理记录（避免重复推送）
│   └── watch.log       常驻监控日志
└── site/index.html     离线查询页（单文件，双击即用）
```

---

## 关键设计

**文件直探**：官网通常先把 PDF 传到服务器、过一会儿才挂公告链接。
`config.json` 里的 `probe_files` 按历史命名规律预测了普通专科批的文件名，
用 HEAD 请求探测，能比公告早几分钟拿到数据。命名规律参考：

```
2026年普通高考院校专业组投档最低分_普通本科批_历史类.pdf
2026年普通高考院校专业组投档最低分_普通本科批_物理类.pdf
2026年普通高考专科院校专业组投档最低分_K美术与设计类.pdf
```

**缺额组识别**：PDF 里有些专业组分数栏是空的，代表没招满、要走征集志愿。
系统把这些行标记为 `vacancy`，查询页可以单独筛出来——填征集志愿时这就是靶子。

**按分数筛可冲院校**：查询页输入你的分数，自动列出所有投档线不高于它的专业组。

---

## 2026 年录取时间表（官方）

| 批次 | 录取时间 |
|---|---|
| 普通本科批 | 7月23日–30日 ✅ 已出 |
| 普通专科（高职）提前批 | 8月4日–6日 ✅ 已出 |
| 艺术专科批、体育专科批 | 8月6日 ✅ 已出 |
| **普通专科（高职）批** | **8月6日–15日 ⏳ 投档线待发布** |

普通专科批投档最低分是眼下最该盯的——把监控挂上就行。

---

## 常见问题

**会不会被封 IP？**
不会。默认 2 分钟一次、只拉 20KB 列表页，比一个正常用户手动刷新还轻。
不建议改到 10 秒以下——既没必要，也不礼貌。

**数据准不准？**
PDF 是官网原件直接下载，解析逐行核对过，零漏行。
但**填志愿请以官网原文为准**，本地副本只是让你快人一步看到。

**pdftotext: command not found？**
`sudo apt install poppler-utils`（Ubuntu/Debian）或 `brew install poppler`（macOS）。

---

数据来源：山西招生考试网 http://www.sxkszx.cn ｜ 仅作个人查询提速，请勿高频滥用
