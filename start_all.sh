#!/bin/bash
# ========================================
#   csMonitor 一键启动脚本 (Linux)
# ========================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAPCAT_DIR="$SCRIPT_DIR/robot/NapCat.Shell"

echo "========================================"
echo "  csMonitor 一键启动脚本 (Linux)"
echo "========================================"
echo ""

# ---- 第1步：启动 NapCat ----
echo "[1/2] 正在启动 NapCat 机器人..."
cd "$NAPCAT_DIR"

# 查找 Linux QQ 安装路径
QQ_PATH=""
for candidate in \
    "/opt/QQ/qq" \
    "/usr/bin/qq" \
    "/usr/local/bin/qq" \
    "$HOME/.local/bin/qq"; do
    if [ -x "$candidate" ]; then
        QQ_PATH="$candidate"
        break
    fi
done

if [ -z "$QQ_PATH" ]; then
    echo "[错误] 未找到 Linux QQ，请确认已安装（预期路径: /opt/QQ/qq）"
    exit 1
fi

echo "  QQ 路径: $QQ_PATH"

# 设置 NapCat 环境变量并后台启动
export NAPCAT_PATCH_PACKAGE="$NAPCAT_DIR/qqnt.json"
export NAPCAT_MAIN_PATH="$NAPCAT_DIR/napcat.mjs"

# 生成 loadNapCat.js
NAPCAT_MAIN_PATH_URL="${NAPCAT_MAIN_PATH//\//\\/}"
echo "(async () => {await import(\"file://$NAPCAT_MAIN_PATH\")})()" > "$NAPCAT_DIR/loadNapCat.js"

# 使用 napcat 的 shell 启动方式（Linux 下直接用 qq 命令注入）
nohup "$QQ_PATH" > /tmp/napcat.log 2>&1 &
NAPCAT_PID=$!
echo "  NapCat 已启动 (PID: $NAPCAT_PID)"

# ---- 第2步：等待 NapCat 就绪（检测端口3000可连通） ----
echo "[2/2] 等待 NapCat 启动完成..."
READY=0
for i in $(seq 1 60); do
    if [ $READY -eq 0 ]; then
        if (echo > /dev/tcp/127.0.0.1/3000) 2>/dev/null; then
            READY=1
            echo "  NapCat 已就绪！"
        else
            echo "  等待中... [$i/60]"
            sleep 3
        fi
    fi
done

if [ $READY -eq 0 ]; then
    echo "[错误] NapCat 在 3 分钟内未启动，请检查 /tmp/napcat.log"
    kill $NAPCAT_PID 2>/dev/null
    exit 1
fi

# ---- 第3步：启动 csMonitor ----
echo ""
echo "正在启动 csMonitor..."
cd "$SCRIPT_DIR"
while true; do
    python3 main.py
    echo "程序崩了，5秒后重启..."
    sleep 5
done
