import re

with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 _group_sell_buffer 方法后添加 _generate_sell_csv 方法
old_code = '''    def _group_sell_buffer(self, buffer, is_increase):
        """按基础名分组，每组只保留变幅最大的一条，按变幅从大到小排序返回消息列表
        is_increase: True 表示只取激增，False 表示只取锐减
        """
        groups = {}  # base_name -> (percent, msg)
        for base_name, percent, msg, inc in buffer:
            if inc != is_increase:
                continue
            if base_name not in groups or percent > groups[base_name][0]:
                groups[base_name] = (percent, msg)

        # 按变幅从大到小排序
        sorted_items = sorted(groups.values(), key=lambda x: x[0], reverse=True)
        return [msg for _, msg in sorted_items]

    # ========================
    # follow 持久化
    # ========================'''

new_code = '''    def _group_sell_buffer(self, buffer, is_increase):
        """按基础名分组，每组只保留变幅最大的一条，按变幅从大到小排序返回消息列表
        is_increase: True 表示只取激增，False 表示只取锐减
        """
        groups = {}  # base_name -> (percent, msg)
        for base_name, percent, msg, inc in buffer:
            if inc != is_increase:
                continue
            if base_name not in groups or percent > groups[base_name][0]:
                groups[base_name] = (percent, msg)

        # 按变幅从大到小排序
        sorted_items = sorted(groups.values(), key=lambda x: x[0], reverse=True)
        return [msg for _, msg in sorted_items]

    def _generate_sell_csv(self, time_str):
        """生成在售监控 CSV 文件，返回文件路径"""
        import csv
        csv_dir = os.path.join(base_dir, "data", "sell_reports")
        os.makedirs(csv_dir, exist_ok=True)
        
        csv_filename = f"sell_report_{time_str.replace(':', '').replace(' ', '_')}.csv"
        csv_path = os.path.join(csv_dir, csv_filename)
        
        # 收集所有有在售状态的物品
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
            })
        
        if not rows:
            return None
        
        # 按变化幅度排序
        rows.sort(key=lambda x: float(x["变化幅度(%)"]), reverse=True)
        
        # 写入 CSV
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["id", "名称", "现在在售", "现在价格", "波谷在售", "波谷在售时间", "变化幅度(%)"])
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"[SellScan] CSV 报告已生成: {csv_path}")
        return csv_path

    # ========================
    # follow 持久化
    # ========================'''

content = content.replace(old_code, new_code)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
