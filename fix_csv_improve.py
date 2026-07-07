with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 _generate_sell_csv 方法，从 All_item.json 获取名称和价格
old_code = '''    def _generate_sell_csv(self, time_str):
        """生成在售监控 CSV 文件，返回文件路径（只保留一个最新文件）"""
        import csv
        csv_dir = os.path.join(base_dir, "data", "sell_reports")
        os.makedirs(csv_dir, exist_ok=True)
        
        # 文件名固定，每次覆盖
        csv_filename = "sell_report_latest.csv"
        csv_path = os.path.join(csv_dir, csv_filename)
        
        # 只收集有变化的饰品（有波谷数据且变化幅度超过阈值）
        rows = []
        total_count = 0
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
                continue
            
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
            })
        
        print(f"[SellScan] CSV 过滤: 总物品数={total_count}, 满足条件数={len(rows)}, 阈值={self.sell_num_warning_percent * 100}%")
        
        if not rows:
            return None
        
        # 按变化幅度排序
        rows.sort(key=lambda x: float(x["变化幅度(%)"]), reverse=True)
        
        # 写入 CSV
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["id", "名称", "现在在售", "现在价格", "波谷在售", "波谷在售时间", "变化幅度(%)"])
            writer.writeheader()
            writer.writerows(rows)
        
        return csv_path'''

new_code = '''    def _generate_sell_csv(self, time_str):
        """生成在售监控 CSV 文件，返回文件路径（只保留一个最新文件）"""
        import csv
        
        # 从 All_item.json 获取名称映射
        all_items = storage.load_json("data/All_item.json")
        item_name_map = {}
        if all_items:
            for item in all_items:
                item_id = str(item.get("id", ""))
                item_name = item.get("name", "")
                if item_id and item_name:
                    item_name_map[item_id] = item_name
        
        csv_dir = os.path.join(base_dir, "data", "sell_reports")
        os.makedirs(csv_dir, exist_ok=True)
        
        # 文件名固定，每次覆盖
        csv_filename = "sell_report_latest.csv"
        csv_path = os.path.join(csv_dir, csv_filename)
        
        # 只收集有变化的饰品（有波谷数据且变化幅度超过阈值）
        rows = []
        total_count = 0
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
            
            # 只保留变化幅度超过阈值的饰品（提高到30%）
            if abs(change_percent) < 30:
                continue
            
            curr_price = self.curr_price.get(item_id, 0)
            # 优先从 config 获取名称，否则从 All_item.json 获取
            item_name = config.get_item_name(item_id) or item_name_map.get(item_id, "")
            
            rows.append({
                "id": item_id,
                "名称": item_name,
                "现在在售": curr_num,
                "现在价格": curr_price if curr_price > 0 else "未知",
                "波谷在售": trough_num,
                "波谷在售时间": trough_time,
                "变化幅度(%)": f"{change_percent:.1f}"
            })
        
        print(f"[SellScan] CSV 过滤: 总物品数={len(self.sell_num_state)}, 满足条件数={len(rows)}, 阈值=30%")
        
        if not rows:
            return None
        
        # 按变化幅度排序
        rows.sort(key=lambda x: float(x["变化幅度(%)"]), reverse=True)
        
        # 写入 CSV
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["id", "名称", "现在在售", "现在价格", "波谷在售", "波谷在售时间", "变化幅度(%)"])
            writer.writeheader()
            writer.writerows(rows)
        
        return csv_path'''

content = content.replace(old_code, new_code)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
