#!/usr/bin/env bash
# 山西录取线监控 · 一键启动
# 用法：  bash start.sh            交互式选择
#        bash start.sh watch      直接进入监控

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YEL='\033[1;33m'; B='\033[1m'; N='\033[0m'

echo -e "${B}山西录取投档线监控${N}\n"

# ---- 依赖自检 ----
miss=0
python3 -c "import requests" 2>/dev/null || { echo -e "${RED}✗${N} 缺 requests  →  pip install requests"; miss=1; }
command -v pdftotext >/dev/null 2>&1 || {
  echo -e "${RED}✗${N} 缺 pdftotext（PDF 解析）"
  echo "     Ubuntu/Debian: sudo apt install poppler-utils"
  echo "     macOS:         brew install poppler"
  echo "     Windows:       下载 poppler 并加入 PATH"
  miss=1
}
[ $miss -eq 1 ] && { echo -e "\n${YEL}装好依赖再跑一次${N}"; exit 1; }
echo -e "${GREEN}✓${N} 依赖齐全"

# ---- 推送自检 ----
if [ -n "$SCKEY$PUSHPLUS$BARK_URL$FEISHU_HOOK$DINGTALK_HOOK$WXWORK_HOOK$MAIL_TO" ]; then
  echo -e "${GREEN}✓${N} 已配置推送渠道"
else
  echo -e "${YEL}!${N} 未配置推送，只会在终端打印"
  echo "     想收微信通知：去 https://sct.ftqq.com 扫码拿 SendKey，然后"
  echo -e "     ${B}export SCKEY=\"你的key\"${N}"
fi
echo ""

ACTION="${1:-}"
if [ -z "$ACTION" ]; then
  echo "选择操作："
  echo "  1) 开始监控（60 秒一查，推荐这几天用）"
  echo "  2) 开始监控（120 秒一查，更省流量）"
  echo "  3) 只查一次，看看有没有新东西"
  echo "  4) 补抓历史数据（首次使用先跑这个）"
  echo "  5) 测试推送是否通"
  echo "  6) 重建离线查询页"
  read -rp "请输入序号 [1]: " c
  c=${c:-1}
else
  c=0; [ "$ACTION" = "watch" ] && c=1
fi

case "$c" in
  1) echo -e "\n${GREEN}监控启动${N} · 每 60 秒查一次 · Ctrl+C 退出\n"
     exec python3 monitor.py --loop 60 ;;
  2) echo -e "\n${GREEN}监控启动${N} · 每 120 秒查一次 · Ctrl+C 退出\n"
     exec python3 monitor.py --loop 120 ;;
  3) python3 monitor.py --once ;;
  4) python3 monitor.py --backfill
     echo -e "\n${GREEN}完成${N} · 打开 site/index.html 即可查分" ;;
  5) python3 notify.py ;;
  6) python3 build_site.py ;;
  *) echo "无效选择"; exit 1 ;;
esac
