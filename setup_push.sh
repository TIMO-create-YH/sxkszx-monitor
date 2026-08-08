#!/usr/bin/env bash
# 推送配置向导 —— 填一次，永久生效
# 用法: bash setup_push.sh

cd "$(dirname "$0")" || exit 1
ENV_FILE=".env"

echo ""
echo "============================================================"
echo "        山西投档线监控 · 推送配置向导"
echo "============================================================"
echo ""
echo "  投档线一发布，手机立刻响。选一个渠道即可，推荐 1。"
echo ""
echo "   1) Server酱³  → 微信收消息（最省事，免费额度够用）"
echo "                   领 key: https://sct.ftqq.com  微信扫码登录即得"
echo "   2) PushPlus   → 微信收消息（备选）"
echo "                   领 token: https://www.pushplus.plus"
echo "   3) Bark       → iPhone 专用，免费无限量"
echo "                   App Store 装 Bark，复制里面的推送地址"
echo "   4) 邮件       → 发到你的邮箱"
echo "   5) 跳过，只本地记录"
echo ""
read -rp "  请选择 [1-5]: " CH
echo ""

write_env() {
  # $1=KEY  $2=VALUE
  touch "$ENV_FILE"
  grep -v "^$1=" "$ENV_FILE" > "$ENV_FILE.tmp" 2>/dev/null
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  echo "$1=$2" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

case "$CH" in
  1)
    echo "  打开 https://sct.ftqq.com 微信扫码，复制页面上的 SendKey"
    echo "  （形如 SCT123456TxxxxxxxxxxxxxxxxxxxxxxxX）"
    echo ""
    read -rp "  粘贴 SendKey: " V
    [ -z "$V" ] && { echo "  未输入，已取消"; exit 1; }
    write_env "SCKEY" "$V"
    echo "  ✓ 已保存 Server酱"
    ;;
  2)
    read -rp "  粘贴 PushPlus token: " V
    [ -z "$V" ] && { echo "  未输入，已取消"; exit 1; }
    write_env "PUSHPLUS" "$V"
    echo "  ✓ 已保存 PushPlus"
    ;;
  3)
    echo "  形如 https://api.day.app/AbCdEf123456"
    read -rp "  粘贴 Bark 地址: " V
    [ -z "$V" ] && { echo "  未输入，已取消"; exit 1; }
    write_env "BARK_URL" "$V"
    echo "  ✓ 已保存 Bark"
    ;;
  4)
    read -rp "  SMTP 服务器 (如 smtp.qq.com): " H
    read -rp "  端口 (QQ邮箱填 465): " P
    read -rp "  发件邮箱: " U
    read -rsp "  授权码(非登录密码，输入不显示): " W; echo ""
    read -rp "  收件邮箱: " T
    write_env "SMTP_HOST" "$H"; write_env "SMTP_PORT" "${P:-465}"
    write_env "SMTP_USER" "$U"; write_env "SMTP_PASS" "$W"
    write_env "MAIL_TO"   "${T:-$U}"
    echo "  ✓ 已保存邮件配置"
    ;;
  5)
    echo "  已跳过。数据仍会正常抓取并存到本地。"
    exit 0
    ;;
  *)
    echo "  输入无效，已退出"; exit 1
    ;;
esac

echo ""
echo "------------------------------------------------------------"
echo "  正在发送测试消息，请注意查收..."
echo "------------------------------------------------------------"
python3 notify.py 2>&1 | tail -20
echo ""
echo "  收到了 → 配置成功，接下来运行:  bash start.sh  选 1"
echo "  没收到 → 检查 key 是否粘贴完整，重跑本脚本即可覆盖"
echo ""
