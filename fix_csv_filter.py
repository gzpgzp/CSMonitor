with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 _generate_sell_csv 方法，只保留有变化的饰品
old_code = '''        # 收集所有有在售状态的物品
        rows = []
        for item_id, state in self.sell_num_state.items():
            trough = state.get("low", {})
            trough_num = trough.get("num", 0)
            trough_time = trough.get("time", "")
            
            curr_num = self.curr_sell_num.get(item_id, 0)
            if curr_num == 0:
                continue
            
            # 获取当前价格
            curr_price = self.curr_price.get(item_id, 0)
            
            # 计算变化幅度
            if trough_num and trough_num > 0:
                change_percent = (curr_num - trough_num) / trough_num * 100
            else:
                change_percent = 0
            
            item_name = config.get_item_name(item_id)
            
            rows.append({
                "id": item_id,
                "名称": item_name,
                "现在在售": curr_num,
                "现在价格": curr_price if curr_price > 0 else "未知",
                "波谷在售": trough_num,
                "波谷在售时间": trough_time,
                "变化幅度(%)": f"{change_percent:.1f}"
            })'''

new_code = '''        # 只收集有变化的饰品（有波谷数据且变化幅度不为0）
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
            
            # 变化幅度为0，跳过
            if abs(change_percent) < 0.1:
                continue
            
            # 获取当前价格
            curr_price = self.curr_price.get(item_id, 0)
            
            item_name = config.get_item_name(item_id)
            
            rows.append({
                "id": item_id,
                "名称": item_name,
                "现在在售": curr_num,
                "现在价格": curr_price if curr_price > 0 else "未知",
                "波谷在售": trough_num,
                "波谷在售时间": trough_time,
                "变化幅度(%)": f"{change_percent:.1f}"
            })'''

content = content.replace(old_code, new_code)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
