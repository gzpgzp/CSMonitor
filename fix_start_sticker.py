with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 start() 方法中添加 sticker 线程启动
old_start = '''        # 独立在售数量扫描线程（主线程忙时自动暂停）
        threading.Thread(
            target=self._sell_num_scan_loop,
            daemon=True
        ).start()

    def stop(self):'''

new_start = '''        # 独立在售数量扫描线程（主线程忙时自动暂停）
        threading.Thread(
            target=self._sell_num_scan_loop,
            daemon=True
        ).start()

        # Sticker 在售数量扫描线程（每天凌晨12点执行）
        threading.Thread(
            target=self._sticker_sell_scan_loop,
            daemon=True
        ).start()

    def stop(self):'''

content = content.replace(old_start, new_start)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
