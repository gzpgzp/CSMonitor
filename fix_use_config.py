with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 把硬编码的 30% 改为使用配置参数
old_code = '''            # 只保留变化幅度超过阈值的饰品（提高到30%）
            if abs(change_percent) < 30:
                continue'''

new_code = '''            # 只保留变化幅度超过阈值的饰品
            csv_threshold = config.get_param("csv_change_percent")
            if csv_threshold is None:
                csv_threshold = 0.10  # 默认10%
            if abs(change_percent) < csv_threshold * 100:
                continue'''

content = content.replace(old_code, new_code)

# 修改日志输出
old_log = '''        print(f"[SellScan] CSV 过滤: 总物品数={len(self.sell_num_state)}, 满足条件数={len(rows)}, 阈值=30%")'''
new_log = '''        csv_threshold = config.get_param("csv_change_percent") or 0.10
        print(f"[SellScan] CSV 过滤: 总物品数={len(self.sell_num_state)}, 满足条件数={len(rows)}, 阈值={csv_threshold * 100}%")'''

content = content.replace(old_log, new_log)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
