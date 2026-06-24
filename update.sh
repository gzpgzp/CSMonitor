#!/bin/bash

echo "停止 CSMonitor..."
systemctl stop csmonitor

echo "更新代码..."
git fetch origin

git reset --hard origin/master

git clean -fd

echo "启动 CSMonitor..."
systemctl start csmonitor

echo "更新完成，当前状态："
systemctl status csmonitor --no-pager