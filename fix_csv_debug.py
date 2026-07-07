with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 _generate_sell_csv 里加日志，看看实际有多少饰品满足条件
old_code = '''        # 只收集有变化的饰品（有波谷数据且变化幅度不为0）
        rows = []
        for item_id, state in self.sell_num_state.items():
            trough = state.get("low", {})
            trough_num = trough.get("num", 0)
            trough_time = trough.get("time", "")
            
            # 没有波谷数据，跳过
            if not trough_num or trough_num == 0:
                continue
            
            curr_num = self.curr_sell_num.get(item_id, 0)
            if curr_num == 0:
                continue
            
            # 计算变化幅度
            change_percent = (curr_num - trough_num) / trough_num * 100
            
            # 只保留变化幅度超过阈值的饰品
            if abs(change_percent) < self.sell_num_warning_percent * 100:
                continue'''

new_code = '''        # 只收集有变化的饰品（有波谷数据且变化幅度超过阈值）
        rows = []
        total_count = 0
        for item_id, state in self.sell_num_state.items():
            total_count += 1
            trough = state.get("low", {})
            trough_num = trough.get("num", 0)
            trough_time = trough.get("time", "")
            
            # 没有波谷数据，跳过
            if not trough_num or trough_num == 0:
                continue
            
            curr_num = self.curr_sell_num.get(item_id, 0)
            if curr_num == 0:
                continue
            
            # 计算变化幅度
            change_percent = (curr_num - trough_num) / trough_num * 100
            
            # 只保留变化幅度超过阈值的饰品
            if abs(change_percent) < self.sell_num_warning_percent * 100:
                continue'''

content = content.replace(old_code, new_code)

# 在写入 CSV 前加日志
old_code2 = '''        if not rows:
            return None
        
        # 按变化幅度排序
        rows.sort(key=lambda x: float(x["变化幅度(%)"]), reverse=True)'''

new_code2 = '''        print(f"[SellScan] CSV 过滤: 总物品数={total_count}, 满足条件数={len(rows)}, 阈值={self.sell_num_warning_percent * 100}%")
        
        if not rows:
            return None
        
        # 按变化幅度排序
        rows.sort(key=lambda x: float(x["变化幅度(%)"]), reverse=True)'''

content = content.replace(old_code2, new_code2)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
