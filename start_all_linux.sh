#!/bin/bash

echo "检查 NapCat 服务..."

if systemctl is-active --quiet napcat; then
    echo "NapCat 已运行"
else
    echo "NapCat 未运行，启动 NapCat..."
    sudo systemctl start napcat

    echo "等待 NapCat 初始化..."
    sleep 10
fi

echo "启动 CSMonitor..."
./start.sh