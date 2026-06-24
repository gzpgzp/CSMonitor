#!/bin/bash

echo "停止 CSMonitor..."
systemctl stop csmonitor

cd /root/CSMonitor || exit 1

echo "强制同步代码..."

git fetch origin
git reset --hard origin/master

echo "启动 CSMonitor..."
systemctl start csmonitor

echo "当前状态："
systemctl status csmonitor --no-pager

echo "更新完成"
