with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 _cleanup_low_sell_items 方法后添加 sticker 监控方法
old_code = '''        print(f"[SellScan] 已从 All_item.json 删除 {len(low_ids)} 个在售<{threshold}的物品"
              f"（剩余 {len(updated)} 个）")

    def _load_sell_watch(self):'''

new_code = '''        print(f"[SellScan] 已从 All_item.json 删除 {len(low_ids)} 个在售<{threshold}的物品"
              f"（剩余 {len(updated)} 个）")

    # ========================
    # Sticker 在售数量扫描线程（每天凌晨12点执行）
    # ========================
    def _sticker_sell_scan_loop(self):
        """独立线程：每天凌晨12点扫描 sticker.json，监测在售数量变化"""
        from datetime import datetime
        first_round = True
        scan_index = 1

        while self.running:
            try:
                # 检查是否到了凌晨12点（0点）
                now = datetime.now()
                if now.hour != 0 or now.minute != 0:
                    # 没到时间，等待1分钟后再检查
                    time.sleep(60)
                    continue

                # 到了凌晨12点，开始扫描
                sticker_items = storage.load_json("data/sticker.json")
                if not sticker_items or not isinstance(sticker_items, list):
                    print("[StickerScan] sticker.json 加载失败或为空")
                    time.sleep(60)
                    continue

                print(f"[StickerScan] 第{scan_index}轮开始，共{len(sticker_items)}个贴纸")
                self.sticker_curr_sell_num = {}

                for item in sticker_items:
                    if not self.running:
                        break
                    # 等待主线程空闲再继续请求API
                    self._price_idle.wait()
                    item_id = str(item.get("id", ""))
                    item_name = item.get("name", "")
                    if not item_id:
                        continue
                    self._scan_sticker_sell_num_item(item_id, item_name)

                # 本轮结束，生成并发送 CSV 报告
                if not first_round:
                    time_str = self._now()
                    csv_path = self._generate_sticker_sell_csv(time_str)
                    if csv_path:
                        qq_robot.send_sell_file(csv_path, "贴纸在售监控报告.csv")

                first_round = False
                print(f"[StickerScan] 第{scan_index}轮结束")
                scan_index += 1

                # 等待到下一个凌晨12点（24小时后）
                time.sleep(86400 - now.minute * 60 - now.second)

            except Exception:
                traceback.print_exc()
                time.sleep(60)

    def _scan_sticker_sell_num_item(self, item_id, item_name):
        """扫描单个贴纸的在售数量"""
        try:
            info = self._safe_api_call(lambda: crawler.get_item_info(item_id))
            if not info or 'goods_info' not in info:
                return

            goods = info.get('goods_info', {})
            sell_num = goods.get("yyyp_sell_num")
            if sell_num is None:
                return

            self.sticker_curr_sell_num[item_id] = sell_num
            self._init_sticker_sell_num_state(item_id, sell_num)

        except Exception:
            traceback.print_exc()

    def _init_sticker_sell_num_state(self, item_id, sell_num):
        """初始化贴纸在售数量状态"""
        if item_id not in self.sticker_sell_num_state:
            self.sticker_sell_num_state[item_id] = {
                "last_num": sell_num,
                "prev_num": None,
                "trend": None,
                "prev_trend": None,
                "high": {"time": self._now(), "num": sell_num},
                "low": {"time": self._now(), "num": sell_num},
            }
        else:
            # 更新趋势
            s = self.sticker_sell_num_state[item_id]
            prev = s["last_num"]
            s["prev_num"] = prev
            s["prev_trend"] = s["trend"]
            if prev is not None:
                if sell_num > prev:
                    s["trend"] = Trend.UP
                elif sell_num < prev:
                    s["trend"] = Trend.DOWN
            s["last_num"] = sell_num

            # 更新波峰波谷
            peak = s["high"]
            trough = s["low"]
            if sell_num > peak["num"]:
                s["high"] = {"time": self._now(), "num": sell_num}
            if sell_num < trough["num"]:
                s["low"] = {"time": self._now(), "num": sell_num}

    def _generate_sticker_sell_csv(self, time_str):
        """生成贴纸在售监控 CSV 文件"""
        import csv
        csv_dir = os.path.join(base_dir, "data", "sell_reports")
        os.makedirs(csv_dir, exist_ok=True)
        
        csv_filename = "sticker_sell_report_latest.csv"
        csv_path = os.path.join(csv_dir, csv_filename)
        
        rows = []
        for item_id, state in self.sticker_sell_num_state.items():
            trough = state.get("low", {})
            trough_num = trough.get("num", 0)
            trough_time = trough.get("time", "")
            
            if not trough_num or trough_num == 0:
                continue
            
            curr_num = self.sticker_curr_sell_num.get(item_id, 0)
            if curr_num == 0:
                continue
            
            change_percent = (curr_num - trough_num) / trough_num * 100
            
            # 使用配置阈值过滤
            csv_threshold = config.get_param("csv_change_percent") or 0.10
            if abs(change_percent) < csv_threshold * 100:
                continue
            
            curr_price = self.curr_price.get(item_id, 0)
            
            # 从 sticker.json 获取名称
            sticker_items = storage.load_json("data/sticker.json")
            item_name = ""
            if sticker_items:
                for item in sticker_items:
                    if str(item.get("id", "")) == item_id:
                        item_name = item.get("name", "")
                        break
            
            rows.append({
                "id": item_id,
                "名称": item_name,
                "现在在售": curr_num,
                "现在价格": curr_price if curr_price > 0 else "未知",
                "波谷在售": trough_num,
                "波谷在售时间": trough_time,
                "变化幅度(%)": f"{change_percent:.1f}"
            })
        
        print(f"[StickerScan] CSV 过滤: 总物品数={len(self.sticker_sell_num_state)}, 满足条件数={len(rows)}")
        
        if not rows:
            return None
        
        rows.sort(key=lambda x: float(x["变化幅度(%)"]), reverse=True)
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["id", "名称", "现在在售", "现在价格", "波谷在售", "波谷在售时间", "变化幅度(%)"])
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"[StickerScan] CSV 报告已生成: {csv_path}")
        return csv_path

    def _load_sell_watch(self):'''

content = content.replace(old_code, new_code)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
