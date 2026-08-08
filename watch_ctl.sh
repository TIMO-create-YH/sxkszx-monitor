#!/usr/bin/env bash
# 轮询守护控制：start / stop / status / restart
# 用 pidfile 管理，避免 pgrep -f 误伤调用方自身的 shell
cd "$(dirname "$0")" || exit 1
PIDF=data/watch.pid
INTERVAL=${INTERVAL:-60}

_alive() { [ -f "$PIDF" ] && kill -0 "$(cat $PIDF)" 2>/dev/null; }

case "${1:-status}" in
  start)
    if _alive; then echo "已在运行 PID=$(cat $PIDF)"; exit 0; fi
    setsid nohup python3 -u monitor.py --loop "$INTERVAL" > data/watch.log 2>&1 < /dev/null &
    echo $! > "$PIDF"
    sleep 8
    if _alive; then echo "已启动 PID=$(cat $PIDF)（每 ${INTERVAL} 秒）"; else echo "启动失败，看 data/watch.log"; fi
    ;;
  stop)
    if _alive; then kill "$(cat $PIDF)" && echo "已停止 PID=$(cat $PIDF)"; rm -f "$PIDF"
    else echo "未在运行"; fi
    ;;
  restart)
    bash "$0" stop >/dev/null 2>&1; sleep 1; bash "$0" start
    ;;
  status)
    if _alive; then
      echo "运行中 PID=$(cat $PIDF)  已跑 $(ps -o etime= -p "$(cat $PIDF)" | tr -d ' ')"
    else
      echo "未运行"
    fi
    echo "--- 最近日志 ---"
    tail -3 data/watch.log 2>/dev/null
    ;;
  *) echo "用法: bash watch_ctl.sh {start|stop|restart|status}" ;;
esac
