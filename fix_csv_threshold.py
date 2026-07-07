with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 把过滤阈值从 0.1% 改为 sell_num_warning_percent
old_code = '''            # 计算变化幅度
            change_percent = (curr_num - trough_num) / trough_num * 100
            
            # 变化幅度为0，跳过
            if abs(change_percent) < 0.1:
                continue'''

new_code = '''            # 计算变化幅度
            change_percent = (curr_num - trough_num) / trough_num * 100
            
            # 只保留变化幅度超过阈值的饰品
            if abs(change_percent) < self.sell_num_warning_percent * 100:
                continue'''

content = content.replace(old_code, new_code)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
