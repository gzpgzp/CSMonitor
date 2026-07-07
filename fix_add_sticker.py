with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 __init__ 中添加 sticker 监控状态变量
old_init = '''        # 在售监控保护列表（不因价格/数量低于阈值而被删除）
        self.sell_watch_ids: set = set()
        self._load_sell_watch()'''

new_init = '''        # 在售监控保护列表（不因价格/数量低于阈值而被删除）
        self.sell_watch_ids: set = set()
        self._load_sell_watch()

        # ========================
        # Sticker 监控状态
        # ========================
        self.sticker_sell_num_state = {}
        self.sticker_curr_sell_num = {}'''

content = content.replace(old_init, new_init)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
