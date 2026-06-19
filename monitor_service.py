import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

import config
import csqaq_api as crawler
import qq_robot
import storage
from monitor_context import special_monitor_context


class Trend(Enum):
    UP = 1
    DOWN = 2


# 全局服务实例，供 qq_robot 等模块引用
service = None


class MonitorService:
    def __init__(self, items):
        self.items = items
        self.lock = threading.Lock()
        self.running = False

        # 主线程空闲信号：set=空闲可用API，clear=主线程占用API
        self._price_idle = threading.Event()
        self._price_idle.set()  # 初始为空闲

        # 统一状态结构（价格）
        self.state = {}
        """
        item_id -> {
            last_price,
            prev_price,
            trend,
            prev_trend,
            high: {time, price},
            low: {time, price}
        }
        """

        # 在售数量状态
        self.sell_num_state = {}
        """
        item_id -> {
            last_num,
            prev_num,
            trend,
            prev_trend,
            high: {time, num},    # 在售数量峰值
            low: {time, num}      # 在售数量谷值
        }
        """

        # 当前价格
        self.curr_price = {}

        # 当前在售数量
        self.curr_sell_num = {}

        # follow
        self.follow_map = {}

        # 通知控制
        self.last_notify = {} 

        # 在售数量通知控制
        self.sell_num_last_notify = {}

        # 历史小时价格
        self.hourly_prices = {}

        # 参数
        self.warning_percent = 0.05
        self.change_percent = 0.05
        self.sell_num_warning_percent = 0.10    # 在售数量变化5%告警
        self.sell_num_change_percent = 0.05     # 在售数量波峰波谷过滤阈值
        self.time_interval = 60 * 30
        self.sell_num_time_interval = 60 * 30   # 在售数量通知间隔

        # 每轮消息缓冲区
        # _rise_buffer: [(percent, msg), ...] 涨幅报告
        # _drop_buffer: [(percent, msg), ...] 跌幅报告
        # _sell_buffer: [(base_name, percent, msg, is_increase), ...] 在售报告（按基础名分组取最高）
        self._rise_buffer = []
        self._drop_buffer = []
        self._sell_buffer = []

        # 最新在售报告（供 .checksell 命令查询）
        self._last_sell_report = {
            "time": "",
            "increase": [],  # 完整激增消息列表
            "decrease": [],  # 完整锐减消息列表
        }

        # 在售监控保护列表（不因价格/数量低于阈值而被删除）
        self.sell_watch_ids: set = set()
        self._load_sell_watch()

        # 缓存
        self.hourly_cache = {}

    # ========================
    # 启动 / 停止
    # ========================
    def start(self, interval_min=5):
        self._load_follow_map()
        self._load_params_from_config()
        self._init_history(self.items)

        self.running = True
        threading.Thread(
            target=self._loop,
            args=(interval_min,),
            daemon=True
        ).start()

        # 独立在售数量扫描线程（主线程忙时自动暂停）
        threading.Thread(
            target=self._sell_num_scan_loop,
            daemon=True
        ).start()

    def stop(self):
        self.running = False

    def _loop(self, interval_min):
        index = 1
        while self.running:
            try:
                print(f"[Monitor] 第{index}轮开始")

                # 通知在售线程暂停
                self._price_idle.clear()

                with self.lock:
                    items = list(self.items)

                self.curr_price = {}
                self.curr_sell_num = {}
                self._rise_buffer = []
                self._drop_buffer = []

                for item_id in items:
                    self._safe_process(item_id, index != 1)

                # 本轮结束，统一发送汇总消息
                self._flush_msg_buffer(index)

                # 持久化小时价格缓存 & 清理超过7天的旧数据
                self.flush_cache()
                self._cleanup_hourly_cache()

                print(f"[Monitor] 第{index}轮结束\n")
                index += 1

                # 释放信号，在售线程可以继续
                self._price_idle.set()
                time.sleep(interval_min * 60)

            except Exception:
                traceback.print_exc()
                self._price_idle.set()  # 异常时也要释放，避免死锁
                qq_robot.send_msg("监控异常（主循环），已自动恢复")

    # ========================
    # 防卡死包装
    # ========================
    def _safe_process(self, item_id, need_notify):
        try:
            self.process_item(item_id, need_notify)
        except Exception:
            traceback.print_exc()
            qq_robot.send_msg(f"处理物品异常: {item_id}")

    # ========================
    # 核心逻辑
    # ========================
    def process_item(self, item_id, need_notify):
        info = self._safe_api_call(lambda: crawler.get_item_info(item_id))
        if not info or 'goods_info' not in info:
            return

        goods = info.get('goods_info', {})
        price = goods.get("yyyp_sell_price")
        sell_num = goods.get("yyyp_sell_num")

        if price is None:
            return

        name = config.get_item_name(item_id)
        self.curr_price[item_id] = price

        print(f"{name} 当前价格 {price}")

        self._init_state(item_id, price)

        # 如果没有历史波峰波谷（未初始化历史），跳过检测
        s = self.state[item_id]
        if s["high"]["price"] is None or s["low"]["price"] is None:
            self._update_trend(item_id, price)
            self._update_hourly(item_id, price)
            return

        self._update_trend(item_id, price)
        self._check_peak_trough(item_id, price, name, need_notify)
        self._check_up_break(item_id, price, name, need_notify)
        self._check_callback(item_id, price, name, need_notify)
        self._check_follow(item_id, price, name, need_notify)

        self._update_hourly(item_id, price)

        # 在售数量监控（已移至独立线程 _sell_num_scan_loop）
        # if sell_num is not None:
        #     self.curr_sell_num[item_id] = sell_num
        #     print(f"{name} 在售数量 {sell_num}")
        #     self._process_sell_num(item_id, sell_num, name, need_notify)

    # ========================
    # API防卡死
    # ========================
    def _safe_api_call(self, func, retry=3):
        for _ in range(retry):
            try:
                return func()
            except Exception:
                time.sleep(1)
        return None

    # ========================
    # 状态初始化
    # ========================
    def _init_state(self, item_id, price):
        if item_id not in self.state:
            self.state[item_id] = {
                "last_price": price,
                "prev_price": None,
                "trend": None,
                "prev_trend": None,
                "high": {"time": None, "price": None},
                "low": {"time": None, "price": None},
            }

    # ========================
    # 趋势
    # ========================
    def _update_trend(self, item_id, price):
        s = self.state[item_id]

        prev = s["last_price"]
        s["prev_price"] = prev

        # 先保存上一轮趋势（修复bug：原来在比较之后保存，导致 prev_trend 始终为 None）
        s["prev_trend"] = s["trend"]

        if prev is not None:
            if price > prev:
                s["trend"] = Trend.UP
            elif price < prev:
                s["trend"] = Trend.DOWN

        s["last_price"] = price

    # ========================
    # 波峰波谷
    # ========================
    def _check_peak_trough(self, item_id, price, name, need_notify):
        s = self.state[item_id]

        prev_trend = s["prev_trend"]
        trend = s["trend"]
        prev_price = s["prev_price"]

        peak = s["high"]
        trough = s["low"]

        # 峰：之前UP，现在DOWN（趋势反转，出现局部峰值）
        if prev_trend == Trend.UP and trend == Trend.DOWN:
            if prev_price is not None:
                # 计算与当前波峰的变化幅度
                if peak["price"] is not None and peak["price"] != 0:
                    price_diff = abs(peak["price"] - prev_price)
                    percent = price_diff / peak["price"]
                else:
                    percent = 1.0  # 首次设置波峰

                if percent > self.change_percent or peak["price"] is None:
                    time_str = self._now()
                    old_peak = {"time": peak["time"], "price": peak["price"]}
                    s["high"] = {"time": time_str, "price": prev_price}
                    if need_notify:
                        msg = (f"现在是：{time_str}\n"
                               f"{name}出现新波峰📈，涨完开始下降了!\n"
                               f"上个波峰在{old_peak['time']}，价格{old_peak['price']}。\n"
                               f"当前波峰值：{prev_price}, 当前价格：{price}")
                        # qq_robot.send_msg(msg)

        # 谷：之前DOWN，现在UP（趋势反转，出现局部谷值）
        elif prev_trend == Trend.DOWN and trend == Trend.UP:
            if prev_price is not None:
                # 计算与当前波谷的变化幅度
                if trough["price"] is not None and trough["price"] != 0:
                    price_diff = abs(trough["price"] - prev_price)
                    percent = price_diff / trough["price"]
                else:
                    percent = 1.0  # 首次设置波谷

                if percent > self.change_percent or trough["price"] is None:
                    time_str = self._now()
                    old_trough = {"time": trough["time"], "price": trough["price"]}
                    s["low"] = {"time": time_str, "price": prev_price}
                    if need_notify:
                        msg = (f"现在是：{time_str}\n"
                               f"{name}出现新波谷📈，降完开始涨了!\n"
                               f"上个波谷在{old_trough['time']}，价格{old_trough['price']}。\n"
                               f"当前波谷值：{prev_price}, 当前价格：{price}")
                        # qq_robot.send_msg(msg)

    # ========================
    # 上涨突破
    # ========================
    def _check_up_break(self, item_id, price, name, need_notify):
        if not need_notify:
            return
        s = self.state[item_id]
        trough = s["low"]

        if trough["price"] == 0 or trough["price"] is None:
            return

        percent = (price - trough["price"]) / trough["price"]

        if percent > self.warning_percent:
            if self._should_notify(item_id, price, Trend.UP):
                msg = (f"📈 {name} 上涨!\n"
                       f"波谷在{trough['time']}，价格：{trough['price']}\n"
                       f"当前价格：{price}\n"
                       f"涨幅：{self._normalize_price(percent * 100, 1)}%")
                self._rise_buffer.append((percent, msg))

    # ========================
    # 回调
    # ========================
    def _check_callback(self, item_id, price, name, need_notify):
        if not need_notify:
            return
        s = self.state[item_id]
        peak = s["high"]

        if peak["price"] == 0 or peak["price"] is None:
            return

        percent = (peak["price"] - price) / peak["price"]

        if percent > self.warning_percent:
            if self._should_notify(item_id, price, Trend.DOWN):
                msg = (f"⚠️ {name} 回调!\n"
                       f"波峰在{peak['time']}，价格：{peak['price']}\n"
                       f"现价：{price}\n"
                       f"跌幅：{self._normalize_price(percent * 100, 1)}%")
                self._drop_buffer.append((percent, msg))

    # ========================
    # follow
    # ========================
    def _check_follow(self, item_id, price, name, need_notify):
        if not need_notify:
            return

        with self.lock:
            items = list(self.follow_map.items())

        for qq, ctx in items:
            if ctx.check_need_notify(item_id, price):
                target = ctx.notify(item_id)
                msg = f"[CQ:at,qq={qq}] 你的目标价{target}, {name}价格已经达到了{price}，速速速！"
                self._rise_buffer.append((0, msg))

    # ========================
    # 通知控制
    # ========================
    def _should_notify(self, item_id, price, trend):
        now = datetime.now()

        if item_id not in self.last_notify:
            self.last_notify[item_id] = {"time": now, "price": price}
            return True

        last = self.last_notify[item_id]
        last_time = last["time"]
        last_price = last["price"]

        # 时间间隔判断
        time_diff = (now - last_time).total_seconds()
        if time_diff < self.time_interval:
            return False

        # 价格变化判断
        if last_price == 0:
            self.last_notify[item_id] = {"time": now, "price": price}
            return True

        percent = abs(price - last_price) / last_price

        if percent > self.warning_percent:
            self.last_notify[item_id] = {"time": now, "price": price}
            return True

        return False

    # ========================
    # 在售数量监控
    # ========================
    def _init_sell_num_state(self, item_id, sell_num):
        """初始化在售数量状态"""
        if item_id not in self.sell_num_state:
            self.sell_num_state[item_id] = {
                "last_num": sell_num,
                "prev_num": None,
                "trend": None,
                "prev_trend": None,
                "high": {"time": self._now(), "num": sell_num},
                "low": {"time": self._now(), "num": sell_num},
            }

    def _process_sell_num(self, item_id, sell_num, name, need_notify):
        """在售数量监控主流程"""
        self._init_sell_num_state(item_id, sell_num)
        self._update_sell_num_trend(item_id, sell_num)
        self._check_sell_num_peak_trough(item_id, sell_num, name, need_notify)
        self._check_sell_num_increase(item_id, sell_num, name, need_notify)
        self._check_sell_num_decrease(item_id, sell_num, name, need_notify)

    def _update_sell_num_trend(self, item_id, sell_num):
        """更新在售数量趋势"""
        s = self.sell_num_state[item_id]

        prev = s["last_num"]
        s["prev_num"] = prev

        # 先保存上一轮趋势
        s["prev_trend"] = s["trend"]

        if prev is not None:
            if sell_num > prev:
                s["trend"] = Trend.UP
            elif sell_num < prev:
                s["trend"] = Trend.DOWN

        s["last_num"] = sell_num

    def _check_sell_num_peak_trough(self, item_id, sell_num, name, need_notify):
        """在售数量波峰波谷检测"""
        s = self.sell_num_state[item_id]

        prev_trend = s["prev_trend"]
        trend = s["trend"]
        prev_num = s["prev_num"]

        peak = s["high"]
        trough = s["low"]

        # 峰：在售数量之前增加，现在减少
        if prev_trend == Trend.UP and trend == Trend.DOWN:
            if prev_num is not None and prev_num > peak["num"]:
                num_diff = abs(peak["num"] - prev_num)
                percent = num_diff / prev_num if prev_num != 0 else 0
                if percent > self.sell_num_change_percent:
                    time_str = self._now()
                    s["high"] = {"time": time_str, "num": prev_num}
                    # if need_notify:
                    #     msg = (f"现在是：{time_str}\n"
                    #            f"{name}在售数量出现新峰值📉，上架变少了!\n"
                    #            f"上个峰值在{peak['time']}，数量{peak['num']}。\n"
                    #            f"当前峰值：{prev_num}, 当前数量：{sell_num}")
                    #     qq_robot.send_msg(msg)

        # 谷：在售数量之前减少，现在增加
        elif prev_trend == Trend.DOWN and trend == Trend.UP:
            if prev_num is not None and prev_num < trough["num"]:
                num_diff = abs(trough["num"] - prev_num)
                percent = num_diff / prev_num if prev_num != 0 else 0
                if percent > self.sell_num_change_percent:
                    time_str = self._now()
                    s["low"] = {"time": time_str, "num": prev_num}
                    # if need_notify:
                    #     msg = (f"现在是：{time_str}\n"
                    #            f"{name}在售数量出现新谷值📈，上架变多了!\n"
                    #            f"上个谷值在{trough['time']}，数量{trough['num']}。\n"
                    #            f"当前谷值：{prev_num}, 当前数量：{sell_num}")
                    #     qq_robot.send_msg(msg)

    def _check_sell_num_increase(self, item_id, sell_num, name, need_notify):
        """在售数量激增检测（从谷值大幅上涨）"""
        s = self.sell_num_state[item_id]
        trough = s["low"]

        if trough["num"] == 0 or trough["num"] is None:
            return

        percent = (sell_num - trough["num"]) / trough["num"]

        if percent > self.sell_num_warning_percent:
            if self._should_notify_sell_num(item_id, sell_num):
                msg = (f"📦 {name} 在售数量激增!\n"
                       f"谷值在{trough['time']}，数量：{trough['num']}\n"
                       f"当前数量：{sell_num}\n"
                       f"增幅：{self._normalize_price(percent * 100, 1)}%")
                if need_notify:
                    base_name = self._get_base_name(name)
                    self._sell_buffer.append((base_name, percent, msg, True))

    def _check_sell_num_decrease(self, item_id, sell_num, name, need_notify):
        """在售数量锐减检测（从峰值大幅下降）"""
        s = self.sell_num_state[item_id]
        peak = s["high"]

        if peak["num"] == 0 or peak["num"] is None:
            return

        percent = (peak["num"] - sell_num) / peak["num"]

        if percent > self.sell_num_warning_percent:
            if self._should_notify_sell_num(item_id, sell_num):
                msg = (f"🔥 {name} 在售数量锐减!\n"
                       f"峰值在{peak['time']}，数量：{peak['num']}\n"
                       f"当前数量：{sell_num}\n"
                       f"减幅：{self._normalize_price(percent * 100, 1)}%")
                if need_notify:
                    base_name = self._get_base_name(name)
                    self._sell_buffer.append((base_name, percent, msg, False))

    def _should_notify_sell_num(self, item_id, sell_num):
        """在售数量通知频率控制"""
        now = datetime.now()

        if item_id not in self.sell_num_last_notify:
            self.sell_num_last_notify[item_id] = {"time": now, "num": sell_num}
            return True

        last = self.sell_num_last_notify[item_id]
        last_time = last["time"]
        last_num = last["num"]

        # 时间间隔判断
        time_diff = (now - last_time).total_seconds()
        if time_diff < self.sell_num_time_interval:
            return False

        # 数量变化判断
        if last_num == 0:
            self.sell_num_last_notify[item_id] = {"time": now, "num": sell_num}
            return True

        percent = abs(sell_num - last_num) / last_num

        if percent > self.sell_num_warning_percent:
            self.sell_num_last_notify[item_id] = {"time": now, "num": sell_num}
            return True

        return False

    # ========================
    # 独立在售数量扫描线程
    # ========================
    def _sell_num_scan_loop(self):
        """独立线程：遍历 All_item.json 所有物品，监测在售数量变化"""
        # 第一轮不发通知，只建立基线
        first_round = True
        scan_index = 1

        while self.running:
            try:
                all_items = storage.load_json("data/All_item.json")
                if not all_items or not isinstance(all_items, list):
                    print("[SellScan] All_item.json 加载失败或为空")
                    time.sleep(600)
                    continue

                print(f"[SellScan] 第{scan_index}轮开始，共{len(all_items)}个物品")
                self._sell_buffer = []
                self.curr_sell_num = {}  # 每轮重置，避免堆积

                for item in all_items:
                    if not self.running:
                        break
                    # 等待主线程空闲再继续请求API
                    self._price_idle.wait()
                    item_id = str(item.get("id", ""))
                    item_name = item.get("name", "")
                    if not item_id:
                        continue
                    self._scan_sell_num_item(item_id, item_name, not first_round)

                # 本轮结束，发送在售报告（激增/锐减分两条消息，默认各发前10条）
                if not first_round:
                    time_str = self._now()

                    # 先保存完整报告（无论是否有内容）
                    inc_msgs = self._group_sell_buffer(self._sell_buffer, True)
                    dec_msgs = self._group_sell_buffer(self._sell_buffer, False)
                    self._last_sell_report["time"] = time_str
                    self._last_sell_report["increase"] = inc_msgs
                    self._last_sell_report["decrease"] = dec_msgs

                    # 有告警发报告，没告警发提示
                    if inc_msgs or dec_msgs:
                        # 激增报告
                        if inc_msgs:
                            show = inc_msgs[:2]
                            more = len(inc_msgs) - 2
                            header = f"📦 在售激增报告 ({time_str})\n{'═' * 22}"
                            body = ("\n───────────\n").join(show)
                            footer = f"\n───────────\n...还有{more}条，发送 .checksell all 查看全部" if more > 0 else ""
                            qq_robot.send_msg(f"{header}\n{body}{footer}")

                        # 锐减报告
                        if dec_msgs:
                            show = dec_msgs[:2]
                            more = len(dec_msgs) - 2
                            header = f"🔥 在售锐减报告 ({time_str})\n{'═' * 22}"
                            body = ("\n───────────\n").join(show)
                            footer = f"\n───────────\n...还有{more}条，发送 .checksell all 查看全部" if more > 0 else ""
                            qq_robot.send_msg(f"{header}\n{body}{footer}")
                    else:
                        print(f"[SellScan] 第{scan_index}轮结束，无异常")

                # 清理已不在 All_item.json 中的旧状态
                active_ids = {str(item.get("id", "")) for item in all_items}
                self._cleanup_stale_sell_states(active_ids)

                # 清理在售数量低于100的物品：从 All_item.json 和内存状态中删除
                self._cleanup_low_sell_items(all_items)

                first_round = False
                print(f"[SellScan] 第{scan_index}轮结束")
                scan_index += 1
                time.sleep(600)  # 10分钟

            except Exception:
                traceback.print_exc()
                time.sleep(60)

    def _scan_sell_num_item(self, item_id, item_name, need_notify):
        """扫描单个物品的在售数量"""
        try:
            info = self._safe_api_call(lambda: crawler.get_item_info(item_id))
            if not info or 'goods_info' not in info:
                return

            goods = info.get('goods_info', {})
            sell_num = goods.get("yyyp_sell_num")
            sell_price = goods.get("yyyp_sell_price")
            if sell_num is None:
                return

            # 不在保护列表时，在售数量或价格低于100的物品不加入监控，标记为待清理
            if item_id not in self.sell_watch_ids:
                if sell_num < 100 or (sell_price is not None and sell_price < 100):
                    self.curr_sell_num[item_id] = sell_num  # 记录供后续清理 All_item.json 用
                    return

            self.curr_sell_num[item_id] = sell_num
            self._init_sell_num_state(item_id, sell_num)
            self._update_sell_num_trend(item_id, sell_num)
            self._check_sell_num_peak_trough(item_id, sell_num, item_name, need_notify)
            self._check_sell_num_increase(item_id, sell_num, item_name, need_notify)
            self._check_sell_num_decrease(item_id, sell_num, item_name, need_notify)

        except Exception:
            traceback.print_exc()

    # ========================
    # IO缓存
    # ========================
    def _update_hourly(self, item_id, price):
        if item_id not in self.hourly_cache:
            data = storage.load_json(
                f"data/{item_id}_prices_hourly_last.json"
            ) or {}
            self.hourly_cache[item_id] = data

        key = datetime.now().strftime("%Y-%m-%d %H")

        self.hourly_cache[item_id][key] = {
            "time": self._now(),
            "price": price
        }

    def flush_cache(self):
        for item_id, data in self.hourly_cache.items():
            storage.save_json(
                f"data/{item_id}_prices_hourly_last.json",
                data
            )

    def _cleanup_hourly_cache(self):
        """清理 hourly_cache 中超过7天的旧条目，防止内存无限增长"""
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H")
        for item_id in list(self.hourly_cache.keys()):
            data = self.hourly_cache[item_id]
            stale_keys = [k for k in data if k < cutoff]
            for k in stale_keys:
                del data[k]

    def _cleanup_stale_sell_states(self, active_ids):
        """清理已不在 All_item.json 中的物品的在售状态，释放内存"""
        removed_count = 0
        for store in (self.sell_num_state, self.sell_num_last_notify, self.curr_sell_num):
            stale = [k for k in store if k not in active_ids]
            for k in stale:
                del store[k]
            removed_count += len(stale)
        if removed_count:
            print(f"[SellScan] 已清理 {removed_count} 条过期状态")

    def _cleanup_low_sell_items(self, all_items, threshold=100):
        """清理在售数量或价格低于阈值的物品：从 All_item.json 和内存状态中删除（保护列表内的物品除外）"""
        low_ids = set()
        for item_id, num in self.curr_sell_num.items():
            if item_id in self.sell_watch_ids:
                continue  # 保护列表内的物品不删除
            if num is not None and num < threshold:
                low_ids.add(item_id)

        if not low_ids:
            return

        # 从 All_item.json 中删除
        updated = [item for item in all_items if str(item.get("id", "")) not in low_ids]
        storage.save_json("data/All_item.json", updated)

        # 从内存状态中删除
        for store in (self.sell_num_state, self.sell_num_last_notify, self.curr_sell_num):
            for k in low_ids:
                store.pop(k, None)

        print(f"[SellScan] 已从 All_item.json 删除 {len(low_ids)} 个在售<{threshold}的物品"
              f"（剩余 {len(updated)} 个）")

    def _load_sell_watch(self):
        """[保护列表] 从 data/sell_watch.json 加载保护物品 ID"""
        data = storage.load_json("data/sell_watch.json")
        if isinstance(data, dict):
            ids = data.get("ids", [])
        elif isinstance(data, list):
            ids = data
        else:
            ids = []
        self.sell_watch_ids = set(str(i) for i in ids)
        print(f"[SellWatch] 已加载保护列表，共 {len(self.sell_watch_ids)} 个物品")

    def _save_sell_watch(self):
        """[保护列表] 保存保护物品 ID 到 data/sell_watch.json"""
        storage.save_json("data/sell_watch.json", {"ids": sorted(self.sell_watch_ids)})

    def _handle_addsell(self, send_id, arg):
        """添加物品到在售保护列表"""
        if not arg:
            return f"[CQ:at,qq={send_id}] 格式错误，示例：.addsell 饮品名"

        target_id, target_name, candidates = self._search_item(arg)
        if target_id == -1:
            msg = "名字不完全对，猜你喜欢：\n"
            for item in candidates:
                msg += f"{item}\n"
            return msg

        self.sell_watch_ids.add(str(target_id))
        self._save_sell_watch()
        return f"[CQ:at,qq={send_id}] 已将 {target_name} 添加到在售保护列表，不会因价格/数量低于100而被删除。"

    def _handle_delsell(self, send_id, arg):
        """将物品从在售保护列表删除"""
        if not arg:
            return f"[CQ:at,qq={send_id}] 格式错误，示例：.delsell 饮品名"

        target_id, target_name, candidates = self._search_item(arg)
        if target_id == -1:
            msg = "名字不完全对，猜你喜欢：\n"
            for item in candidates:
                msg += f"{item}\n"
            return msg

        item_id_str = str(target_id)
        if item_id_str not in self.sell_watch_ids:
            return f"[CQ:at,qq={send_id}] {target_name} 不在保护列表中。"

        self.sell_watch_ids.discard(item_id_str)
        self._save_sell_watch()
        return f"[CQ:at,qq={send_id}] 已将 {target_name} 从在售保护列表移除。"

    def _handle_checksellwatch(self, send_id):
        """查看在售保护列表"""
        if not self.sell_watch_ids:
            return f"[CQ:at,qq={send_id}] 在售保护列表为空。"
        lines = []
        for item_id in sorted(self.sell_watch_ids):
            name = config.get_item_name(item_id)
            lines.append(f"{name}")
        return f"[CQ:at,qq={send_id}] 在售保护列表（{len(lines)}个）：\n" + "\n".join(lines)

    # ========================
    # 历史数据初始化
    # ========================
    def _init_history(self, items):
        msg = "监控启动！"

        for item_id in items:
            print(f"初始化历史价格 {item_id}")
            name = config.get_item_name(item_id)

            result, now_price = self._time_to_price_record(item_id)
            if result is None or now_price is None:
                continue

            self.hourly_prices[item_id] = result
            data_list = self._dict_to_sorted_list(result)
            peak = self._find_last_peak(data_list)
            trough = self._find_last_trough(data_list)

            self._init_state(item_id, now_price)
            self.state[item_id]["high"] = {"time": peak[0], "price": peak[1]}
            self.state[item_id]["low"] = {"time": trough[0], "price": trough[1]}

        qq_robot.send_msg(msg)

    def _init_item_history(self, item_id):
        print(f"初始化历史价格 {item_id}")
        name = config.get_item_name(item_id)

        result, now_price = self._time_to_price_record(item_id)
        if result is None or now_price is None:
            return f"初始化 {name} 历史数据失败"

        self.hourly_prices[item_id] = result
        self.curr_price[item_id] = now_price

        data_list = self._dict_to_sorted_list(result)
        peak = self._find_last_peak(data_list)
        trough = self._find_last_trough(data_list)

        self._init_state(item_id, now_price)
        self.state[item_id]["high"] = {"time": peak[0], "price": peak[1]}
        self.state[item_id]["low"] = {"time": trough[0], "price": trough[1]}

        msg = (f"{name}:\n现价: {now_price} ;上个波峰在{peak[0]}，价格：{peak[1]}\n"
               f"上个波谷在{trough[0]}，价格：{trough[1]}\n")
        qq_robot.send_msg(msg)
        return None

    def _time_to_price_record(self, item_id):
        data = crawler.post_item_sell_price_chart(item_id, 7)
        if data is None:
            return None, None
        times = data["timestamp"]
        main_data = data["main_data"]

        dic = {}
        index = 0
        now_price = 0
        for t in times:
            date = self._ts_to_date(t)
            price = main_data[index]
            dic[date] = price
            index += 1
            now_price = price

        result = self._hourly_last(dic)
        return result, now_price

    def _find_last_trough(self, data):
        for i in range(len(data) - 2, 0, -1):
            prev_price = data[i - 1][1]
            curr_price = data[i][1]
            next_price = data[i + 1][1]

            if prev_price[1] > curr_price[1] < next_price[1]:
                return data[i][1]  # (time, price)

        return data[0][1]

    def _find_last_peak(self, data):
        for i in range(len(data) - 2, 0, -1):
            prev_price = data[i - 1][1]
            curr_price = data[i][1]
            next_price = data[i + 1][1]

            if prev_price[1] < curr_price[1] > next_price[1]:
                return data[i][1]  # (time, price)

        return data[0][1]

    def _dict_to_sorted_list(self, data):
        return sorted(data.items(), key=lambda x: x[0])

    def _hourly_last(self, data):
        result = {}

        for t, price in data.items():
            dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
            hour = dt.strftime("%Y-%m-%d %H")

            # 直接覆盖，保留最后一个
            if hour not in result or t > result[hour][0]:
                result[hour] = (t, price)

        return result

    def _ts_to_date(self, ts):
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")

    # ========================
    # 工具
    # ========================
    def _flush_msg_buffer(self, index):
        """将本轮收集到的价格告警消息分两拨发送：涨幅报告 + 跌幅报告"""
        time_str = self._now()

        # 第一条：涨幅报告（按涨幅从大到小排序）
        if self._rise_buffer:
            self._rise_buffer.sort(key=lambda x: x[0], reverse=True)
            header = f"📈 涨幅报告 ({time_str})\n{'═' * 18}"
            body = ("\n───────────\n").join(msg for _, msg in self._rise_buffer)
            qq_robot.send_msg(f"{header}\n{body}")

        # 第二条：跌幅报告（按跌幅从大到小排序）
        if self._drop_buffer:
            self._drop_buffer.sort(key=lambda x: x[0], reverse=True)
            header = f"⚠️ 跌幅报告 ({time_str})\n{'═' * 18}"
            body = ("\n───────────\n").join(msg for _, msg in self._drop_buffer)
            qq_robot.send_msg(f"{header}\n{body}")

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _normalize_price(self, price, digits=1):
        q = '0.' + '0' * (digits - 1) + '1'
        return float(
            Decimal(str(price)).quantize(Decimal(q), rounding=ROUND_HALF_UP)
        )

    def _get_base_name(self, name):
        """提取去掉磨损等级后的基础名称，用于分组
        例如：'AK-47 | 红线 (崭新出厂)' -> 'AK-47 | 红线'
        """
        return re.sub(
            r'\s*\((?:崭新出厂|略有磨损|久经沙场|破损不堪|战痕累累)\)\s*$',
            '', name
        ).strip()

    def _group_sell_buffer(self, buffer, is_increase):
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
    # ========================
    def _save_follow_map(self):
        # storage.save_json("follow_map.json", {"follow_map": self.follow_map})
        return

    def _load_follow_map(self):
        # data = storage.load_json("follow_map.json")
        # if "follow_map" in data:
        #     self.follow_map = data["follow_map"]
        # else:
        #     self.follow_map = {}
        return

    # ========================
    # 外部接口
    # ========================
    def add_item(self, item_id):
        with self.lock:
            if item_id not in self.items:
                self.items.append(item_id)
                self._init_item_history(item_id)
                return "添加成功"
            return "这个饰品已经加过了，要干嘛。。。"

    def remove_item(self, item_id):
        with self.lock:
            if item_id in self.items:
                self.items.remove(item_id)
                return f"已删除监控道具 {item_id}"
            return "这个饰品没在监控列表，要干嘛。。。"

    def follow(self, qq_id, item_id, price, follow_type):
        with self.lock:
            if qq_id not in self.follow_map:
                self.follow_map[qq_id] = special_monitor_context(qq_id, {})

            return self.follow_map[qq_id].add_item(item_id, price, follow_type)

    # ========================
    # 机器人命令处理
    # ========================
    def handle_robot_msg(self, send_id, msg):
        command, arg = self._parse_command(msg)
        print(f"命令: {command}, 参数: {arg}")

        if command is None:
            return (f"[CQ:at,qq={send_id}] 没听懂你在说啥，可用命令：\n"
                    f".add 饰品全名 - 添加饰品\n"
                    f".del 饰品全名 - 删除饰品\n"
                    f".check - 查看监控列表\n"
                    f".checksell <n/all> - 查看在售报告前n条或全部\n"
                    f".addsell 饮品全名 - 添加到在售保护列表\n"
                    f".delsell 饮品全名 - 从在售保护列表移除\n"
                    f".checksellwatch - 查看在售保护列表\n"
                    f".follow 饮品全名 价格 <up/down> - 订阅目标价\n"
                    f".modify 参数名 参数值 - 修改参数\n"
                    f".restart - 重启\n"
                    f"（也可以使用 @机器人 代替 . ）")

        if command == "add":
            return self._handle_add(send_id, arg)
        elif command == "del":
            return self._handle_del(send_id, arg)
        elif command == "check":
            return self._handle_check()
        elif command == "checksell":
            return self._handle_checksell(send_id, arg)
        elif command == "addsell":
            return self._handle_addsell(send_id, arg)
        elif command == "delsell":
            return self._handle_delsell(send_id, arg)
        elif command == "checksellwatch":
            return self._handle_checksellwatch(send_id)
        elif command == "restart":
            self._send_restart()
            return "收到重启命令"
        elif command == "follow":
            return self._handle_follow(send_id, arg)
        elif command == "modify":
            return self._handle_modify(send_id, arg)
        else:
            return (f"[CQ:at,qq={send_id}] 未知命令：{command}\n"
                    f"可用命令：.add/.del/.check/.checksell/.addsell/.delsell/.checksellwatch/.follow/.modify/.restart\n"
                    f"（也可以使用 @机器人 代替 . ）")

    def _send_restart(self):
        """重启服务：先发消息，再启动新进程，最后退出当前进程"""
        try:
            qq_robot.send_msg("罗伯特重启中")
        except Exception:
            pass
        time.sleep(1)  # 等待消息发送完成
        # 启动新进程后退出当前进程
        subprocess.Popen(
            [sys.executable] + sys.argv,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        os._exit(0)

    def _parse_command(self, msg_text):
        """
        返回 (command, item_name)
        例子：
        "@机器人 add 新星 | 灼木 (崭新出厂)" -> ("add", "新星 | 灼木 (崭新出厂)")
        ".add 新星 | 灼木 (崭新出厂)" -> ("add", "新星 | 灼木 (崭新出厂)")
        """
        self_id = "2092836515"
        
        # 移除 @机器人 前缀
        at_pattern = fr"^\[CQ:at,qq={self_id}\]\s*"
        content = re.sub(at_pattern, "", msg_text, count=1).strip()
        
        # 移除开头的 "." 
        if content.startswith("."):
            content = content[1:].strip()

        pattern = r"^([\w\u4e00-\u9fff]+)(?:\s+(.+))?$"
        m = re.match(pattern, content)
        if m:
            command = m.group(1).lower()
            arg = m.group(2).strip() if m.group(2) else None
            return command, arg

        return None, None

    def _handle_add(self, send_id, arg):
        if not arg:
            return f"[CQ:at,qq={send_id}] 格式错误，示例：.add 饰品全名"

        target_id, target_name, target_item_list = self._search_item(arg)

        if target_id == -1:
            msg = "名字不完全对，猜你喜欢：\n"
            for item in target_item_list:
                msg += f"{item}\n"
            return msg

        config.modify_watch_item(target_id, target_name, 1)
        return self.add_item(target_id)

    def _handle_del(self, send_id, arg):
        if not arg:
            return f"[CQ:at,qq={send_id}] 格式错误，示例：.del 饰品全名"

        target_id, target_name, target_item_list = self._search_item(arg)

        if target_id == -1:
            msg = "名字不完全对，猜你喜欢：\n"
            for item in target_item_list:
                msg += f"{item}\n"
            return msg

        config.modify_watch_item(target_id, target_name, 0)
        return self.remove_item(target_id)

    def _handle_check(self):
        reply = "监控列表如下：\n"
        for key, value in config.items_id_to_name.items():
            msg = f"{value}，现价："
            if key in self.curr_price:
                msg += f"{self.curr_price[key]}"
            else:
                msg += f"别急好吗牢大，这个饰品的价格还没更新过，等个几分钟"
            # 在售数量
            if key in self.curr_sell_num:
                msg += f"，在售：{self.curr_sell_num[key]}"
            msg += "\n"
            reply += msg
        return reply

    def _handle_checksell(self, send_id, arg):
        """查询最新在售报告：.checksell n 或 .checksell all"""
        report = self._last_sell_report
        if not report["time"]:
            return f"[CQ:at,qq={send_id}] 暂无在售报告，请等待一轮扫描结束。"

        # 解析参数
        n = 2  # 默认前2条
        if arg:
            arg = arg.strip().lower()
            if arg == "all":
                n = None
            else:
                try:
                    n = int(arg)
                    if n <= 0:
                        n = 10
                except ValueError:
                    n = 10

        time_str = report["time"]
        reply = f"[CQ:at,qq={send_id}] 在售报告 ({time_str})\n{'═' * 22}\n"

        # 激增部分
        inc = report["increase"]
        if inc:
            show_inc = inc if n is None else inc[:n]
            reply += "\n📦 激增:\n"
            reply += ("\n───────────\n").join(show_inc)
            reply += "\n"
        else:
            reply += "\n📦 激增: 无\n"

        # 锐减部分
        dec = report["decrease"]
        if dec:
            show_dec = dec if n is None else dec[:n]
            reply += "\n🔥 锐减:\n"
            reply += ("\n───────────\n").join(show_dec)
            reply += "\n"
        else:
            reply += "\n🔥 锐减: 无\n"

        return reply

    def _handle_follow(self, send_id, arg):
        if not arg:
            return (f"[CQ:at,qq={send_id}] 格式错误，示例："
                    f".follow AK-47 | 红线 (崭新出厂) 100 <up或者down/不写默认现价到这个的趋势>")

        parts = arg.split()
        if len(parts) < 2:
            return (f"[CQ:at,qq={send_id}] 格式错误，示例："
                    f".follow AK-47 | 红线 (崭新出厂) 100 <up或者down/不写默认现价到这个的趋势>")

        if parts[-1] in ["up", "down"]:
            follow_type = 1 if parts[-1] == "up" else -1
            try:
                price = float(parts[-2])
            except ValueError:
                return (f"[CQ:at,qq={send_id}] 格式错误，价格不对？现在是{parts[-2]},应该是一个数字\n"
                        f"示例：.follow AK-47 | 红线 (崭新出厂) 100 <up或者down>")
            item_name = " ".join(parts[:-2])
        else:
            try:
                price = float(parts[-1])
            except ValueError:
                return (f"[CQ:at,qq={send_id}] 格式错误，价格不对？现在是{parts[-1]},应该是一个数字\n"
                        f"示例：.follow AK-47 | 红线 (崭新出厂) 100 <up或者down>")
            item_name = " ".join(parts[:-1])
            follow_type = 0  # 默认逻辑

        if not item_name:
            return (f"[CQ:at,qq={send_id}] 格式错误，名字不对？\n"
                    f"示例：.follow AK-47 | 红线 (崭新出厂) 100 <up或者down>")

        # 搜索 item_id
        target_id = config.tye_get_item_name(item_name)
        target_name = ""
        target_item_list = []

        if target_id == -1:
            result = crawler.search_item(item_name)
            if result is not None:
                datas = result.get('data', {})
                for key, value in datas.items():
                    name = value['name']
                    if item_name == name:
                        target_id = key
                        target_name = name
                        break
                    else:
                        target_item_list.append(name)

            # 只有找到精确匹配才添加
            if target_id != -1:
                config.modify_watch_item(target_id, target_name, 1)
                self.add_item(target_id)

        if target_id == -1:
            msg = f"[CQ:at,qq={send_id}] 名字不完全对，猜你喜欢：\n"
            for item in target_item_list:
                msg += f"{item}\n"
            return msg

        # 默认 follow_type：根据当前价格判断
        if follow_type == 0:
            if target_id in self.curr_price:
                curr_price = self.curr_price[target_id]
                if curr_price < price:
                    follow_type = 1
                else:
                    follow_type = -1
            else:
                follow_type = 1  # 无当前价格时默认上涨

        code = self.follow(send_id, target_id, price, follow_type)
        target_name = config.get_item_name(target_id)
        if code == 1:
            return f"[CQ:at,qq={send_id}] 添加成功，开始监控{target_name}，在价格为{price}会进行通知"
        elif code == -1:
            return f"[CQ:at,qq={send_id}] 干嘛。。。又要监控一样的价格"
        elif code == 0:
            return f"[CQ:at,qq={send_id}] 更新价格成功，{target_name}在价格为{price}会进行通知"
        else:
            return f"[CQ:at,qq={send_id}] 未知返回码：{code}，请联系管理员"

    def _search_item(self, arg):
        """搜索物品，返回 (target_id, target_name, target_item_list)"""
        target_id = -1
        target_name = ""
        target_item_list = []

        result = crawler.search_item(arg)
        if result is None:
            return target_id, target_name, target_item_list
        datas = result.get('data', {})
        if not datas:
            return target_id, target_name, target_item_list
        print(f"search items: {datas}")
        for key, value in datas.items():
            name = value['name']
            if arg == name:
                target_id = key
                target_name = name
                break
            else:
                target_item_list.append(name)

        return target_id, target_name, target_item_list

    def _handle_modify(self, send_id, arg):
        if not arg:
            return self._modify_help(send_id)

        # 解析参数名和值，用第一个空格分割
        parts = arg.strip().split(None, 1)
        if len(parts) < 2:
            return self._modify_help(send_id)

        param_name = parts[0]
        param_value_str = parts[1]

        # 查找参数
        if param_name not in config.MODIFIABLE_PARAMS:
            return (f"[CQ:at,qq={send_id}] 未知参数：{param_name}\n"
                    + self._modify_param_list())

        json_key, param_type, description = config.MODIFIABLE_PARAMS[param_name]

        # 类型转换
        try:
            param_value = param_type(param_value_str)
        except ValueError:
            return (f"[CQ:at,qq={send_id}] 参数值格式错误，{param_name}需要{param_type.__name__}类型\n"
                    f"你输入的是：{param_value_str}")

        # 保存到 config.json
        config.set_param(json_key, param_value)

        # 同步更新内存中的值
        self._apply_param(json_key, param_value)

        return (f"[CQ:at,qq={send_id}] 修改成功！\n"
                f"{param_name}（{description}）已改为 {param_value}")

    def _modify_help(self, send_id):
        return (f"[CQ:at,qq={send_id}] 格式：.modify 参数名 参数值\n"
                + self._modify_param_list())

    def _modify_param_list(self):
        msg = (""
               ""
               ""
               ".0可修改的参数列表：\n")
        for name, (json_key, param_type, desc) in config.MODIFIABLE_PARAMS.items():
            current = self._get_param_current_value(json_key)
            msg += f"  {name} = {current}（{desc}，类型：{param_type.__name__}）\n"
        return msg

    def _get_param_current_value(self, json_key):
        """获取参数当前值"""
        mapping = {
            "warning_percent": self.warning_percent,
            "change_percent": self.change_percent,
            "sell_num_warning_percent": self.sell_num_warning_percent,
            "sell_num_change_percent": self.sell_num_change_percent,
            "time_interval": self.time_interval,
            "sell_num_time_interval": self.sell_num_time_interval,
            "check_interval": config.get_param("check_interval"),
            "alert_rise": config.get_param("alert_rise"),
            "alert_drop": config.get_param("alert_drop"),
        }
        return mapping.get(json_key, "未知")

    def _load_params_from_config(self):
        """启动时从 config.json 加载参数到内存"""
        for name, (json_key, param_type, _) in config.MODIFIABLE_PARAMS.items():
            value = config.get_param(json_key)
            if value is not None:
                self._apply_param(json_key, param_type(value))

    def _apply_param(self, json_key, value):
        """将参数值应用到内存"""
        if json_key == "warning_percent":
            self.warning_percent = value
        elif json_key == "change_percent":
            self.change_percent = value
        elif json_key == "sell_num_warning_percent":
            self.sell_num_warning_percent = value
        elif json_key == "sell_num_change_percent":
            self.sell_num_change_percent = value
        elif json_key == "time_interval":
            self.time_interval = value
        elif json_key == "sell_num_time_interval":
            self.sell_num_time_interval = value
