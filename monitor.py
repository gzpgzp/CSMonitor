import config
import csqaq_api as crawler
import qq_robot
import storage
import monitor_context
import threading
import time
from datetime import datetime
from collections import defaultdict
from enum import Enum
from decimal import Decimal, ROUND_HALF_UP
import traceback
import re
import os

from monitor_context import special_monitor_context

items_id = []           # 全局共享列表
items_lock = threading.Lock()  # 保护列表操作

items_high = {}
items_low = {}
items_state = {}
hourly_prices = {}
warning_percent = 0.05
change_percent = 0.05
last_notify = {}

curr_items_price = {}
follow_map = {}

class Trend(Enum):
    up = 1
    down = 2
    
def start_monitor(items):
    load_follow_map()
    init_history(items)
    start_monitor_thread(items,5)

def start_monitor_thread(items, interval_min):
    global items_id
    items_id = items
    t = threading.Thread(
        target=monitor_loop,
        args=(interval_min,)
    )

    t.daemon = True
    t.start()
    while True:
        time.sleep(1)

def monitor_loop(interval_min):
    index = 1
    global curr_items_price
    while True:
        try:
            print(f"开始第{index}次监控")

            # 复制列表，防止遍历时被修改
            with items_lock:
                current_items = list(items_id)


            for id in current_items:
                monitor(id,index != 1)
                
            print(current_items)
            print(f"第{index}次监控结束")
            index += 1
            time.sleep(interval_min * 60)
        except Exception as e:
            stack = traceback.print_exc()
            qq_robot.send_msg(f"G,报错了，请联系知情人员捏。罗伯特已下线。\n错误信息:{stack}")
            
            os._exit(1)

    os._exit(1)
    
def send_restart():
    qq_robot.send_msg("罗伯特重启中")
    os._exit(1)

def monitor(item_id, need_send_msg):
    item_info = crawler.get_item_info(item_id)
    if item_info is None or 'goods_info' not in item_info:
        return 
    info = item_info['goods_info']
    price = info["yyyp_sell_price"]
    curr_items_price[item_id] = price

    name = config.get_item_name(item_id)
    print(f"{name} 当前价格 {price}")

    # 初始化状态
    if item_id not in items_state:
        items_state[item_id] = {
            "trend": None,
            "last_price": price
        }

    state = items_state[item_id]
    last_price = state["last_price"]
    trend = state["trend"]

    if item_id not in items_high:
        curr_items_price[item_id] = f"不是这玩意怎么没价格"
        return 
    trough = items_low[item_id]["price"]
    trough_time = items_low[item_id]["time"]
    
    peak = items_high[item_id]["price"]
    peak_time = items_high[item_id]["time"]
    hour_key, time_str = get_now_time()

    # --------------------------
    # 1️⃣ 检测上涨突破（突破波峰）
    # --------------------------
    if price > trough:
        increase = price - trough
        percent = increase / trough

        if percent > warning_percent:
            if check_need_send_msg(item_id,time_str, price, Trend.up):
                msg = f"现在是：{time_str}\n{name} 开始上涨了!\n波谷在{trough_time}，价格：{trough}.\n当前价格：{price}\n涨幅：{normalize_price(percent * 100, 1)}%"
                if need_send_msg:
                    qq_robot.send_msg(msg)

    # --------------------------
    # 2️⃣ 趋势判断（核心）
    # --------------------------
    if price > last_price:
        new_trend = Trend.up
    elif price < last_price:
        new_trend = Trend.down
    else:
        new_trend = trend

    # --------------------------
    # 3️⃣ 检测“波峰”（上涨 → 下跌） 顺带监测波谷吧
    # --------------------------

    if trend == Trend.up and new_trend == Trend.down:
        if last_price > peak:
            price_diff = abs(peak - last_price)
            percent = price_diff / last_price if last_price != 0 else 0
            
            if percent > change_percent :
                items_high[item_id] = {"time":time_str ,"price":last_price}
                if need_send_msg:
                    msg = f"现在是：{time_str}\n{name}出现新波峰📈，涨完开始下降了!\n上个波峰在{peak_time}，价格{peak}。\n当前波峰值：{last_price}, 当前价格：{price}"
                    # qq_robot.send_msg(msg)
                
    elif trend == Trend.down and new_trend == Trend.up:
        if last_price < trough:
            price_diff = abs(trough - last_price)
            percent = price_diff / last_price if last_price != 0 else 0
            if percent > change_percent :
                items_low[item_id] = {"time":time_str ,"price":last_price}
                if need_send_msg:
                    msg = f"现在是：{time_str}\n{name}出现新波谷📈，降完开始涨了!\n上个波谷在{trough_time}，价格{trough}。\n当前波谷值：{last_price}, 当前价格：{price}"
                    # qq_robot.send_msg(msg)
    
    # --------------------------
    # 4️⃣ 回调检测
    # --------------------------
    if price < peak:
        interval = peak - price
        percent = interval / peak

        if percent > warning_percent:
            if check_need_send_msg(item_id, time_str, price, Trend.down):
                if need_send_msg:
                    msg = f"现在是：{time_str}\n{name}跌幅超过{warning_percent * 100}%，开始回调⚠️\n波峰在{peak_time}，价格： {peak}。\n现价：{price}\n跌幅：{normalize_price(percent * 100, 1)}%"
                    qq_robot.send_msg(msg)
    
    # --------------------------
    # 5️⃣ 更新状态
    # --------------------------
    state["trend"] = new_trend
    state["last_price"] = price

    # --------------------------
    # 通知
    # --------------------------
    if need_send_msg:
        msg = f"{name}：\n"
        check_send = False
        for key, value in follow_map.items():
            if value.check_need_notify(item_id, price):
                check_send = True
                target_price = value.notify(item_id)
                msg += f"[CQ:at,qq={key}] 你的目标价{target_price},价格已经达到了{price}，速速速！\n"
        if check_send:
            qq_robot.send_msg(msg)
        
    # --------------------------
    # 6️⃣ 更新小时价格
    # --------------------------
    update_hourly_last_price(item_id, price)

def update_hourly_last_price(item_id, price):
    data = storage.load_json(f"data/{item_id}_prices_hourly_last")

    now = datetime.now()

    # 当前小时 key
    hour_key = now.strftime("%Y-%m-%d %H")
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # 直接覆盖这一小时的记录
    data[hour_key] = {
        "time": time_str,
        "price": price
    }
    
    hourly_prices[item_id][hour_key] = price

    storage.save_json(f"data/{item_id}_prices_hourly_last.json", data)

def init_history(items_id):
    # msg = "监控启动，监控饰品列表：\n"
    msg = "监控启动！"
    
    for item_id in items_id:
        print(f"初始化历史价格 {item_id}")
        name = config.get_item_name(item_id)

        # 获取历史价格
        result, now_price = time_to_price_record(item_id)
        if result is None or now_price is None:
            continue
        hourly_prices[item_id] = result
        data_list = dict_to_sorted_list(result)
        peak = find_last_peak(data_list)
        trough = find_last_trough(data_list)
        
        items_low[item_id] = {"time":trough[0],"price":trough[1]}
        items_high[item_id] = {"time":peak[0],"price":peak[1]}
        
        # msg += f"{name}: 现价: {now_price} ;\n上个波峰在{peak[0]}，价格：{peak[1]}\n上个波谷在{trough[0]}，价格：{trough[1]}\n"
        
    qq_robot.send_msg(msg)

def init_item_history(item_id):
    print(f"初始化历史价格 {item_id}")
    name = config.get_item_name(item_id)
    # 获取历史价格
    result, now_price = time_to_price_record(item_id)
    hourly_prices[item_id] = result
    curr_items_price[item_id] = now_price
    data_list = dict_to_sorted_list(result)
    peak = find_last_peak(data_list)
    trough = find_last_trough(data_list)
    
    items_high[item_id] = {"time":peak[0],"price":peak[1]}
    msg = f"{name}:\n现价: {now_price} ;上个波峰在{peak[0]}，价格：{peak[1]}\n上个波谷在{trough[0]}，价格：{trough[1]}\n"
    qq_robot.send_msg(msg)

def find_last_trough(data):
    for i in range(len(data) - 2, 0, -1):
        prev_price = data[i - 1][1]
        curr_price = data[i][1]
        next_price = data[i + 1][1]

        if prev_price[1] > curr_price[1] < next_price[1]:
            return data[i][1]  # (time, price)

    return data[0][1]

def find_last_peak(data):
    for i in range(len(data) - 2, 0, -1):
        prev_price = data[i - 1][1]
        curr_price = data[i][1]
        next_price = data[i + 1][1]

        if prev_price[1] < curr_price[1] > next_price[1]:
            return data[i][1]  # (time, price)

    return data[0][1]

def dict_to_sorted_list(data):
    return sorted(data.items(), key=lambda x: x[0])

def parse_command(msg_text):
    """
    返回 (command, item_name)
    例子：
    "@机器人 add 新星 | 灼木 (崭新出厂)" -> ("add", "新星 | 灼木 (崭新出厂)")
    "@机器人 del 新星 | 灼木 (崭新出厂)" -> ("del", "新星 | 灼木 (崭新出厂)")
    """
    # 去掉开头的 [CQ:at,...]
    self_id = "2092836515"
    at_pattern = fr"^\[CQ:at,qq={self_id}\]\s*"
    content = re.sub(at_pattern, "", msg_text, count=1).strip()

    # 匹配命令和可选参数
    pattern = r"^(\w+)(?:\s+(.+))?$"
    m = re.match(pattern, content)
    if m:
        command = m.group(1).lower()
        arg = m.group(2).strip() if m.group(2) else None
        return command, arg

    return None, None

def follow_item(qq_id, item_id, price, follow_type):
    if qq_id not in follow_map:
        follow_map[qq_id] = special_monitor_context(qq_id, {})
    
    code = follow_map[qq_id].add_item(item_id, price, follow_type)
    save_follow_map()
    return code
    
# isAdd , 1是添加，0是删除
def handle_robot_msg(send_id, msg):
    # 命令格式 "@机器人 add 12345"
    command, arg = parse_command(msg)
    print(f"命令: {command}, 参数: {arg}")
    
    if command == "add":
        isAdd = 1
    elif command == "del":
        isAdd = 0
    elif command == "check":
        reply = "监控列表如下：\n"
        print(config.items_id_to_name)
        for key,value in config.items_id_to_name.items():
            msg = f"{value}，现价："
            if key in curr_items_price:
                msg += f"{curr_items_price[key]}\n"
            else:
                msg += f"别急好吗牢大，这个饰品的价格还没价格，还没更新过，等个几分钟\n"
            reply += msg
        return reply
    elif command == "restart":
        send_restart()
        return "收到重启命令"
    elif command == "follow":
        if not arg:
            return f"[CQ:at,qq={send_id}] 格式错误，示例：@机器人 follow AK-47 | 红线 (崭新出厂) 100 <up或者down/不写默认现价到这个的趋势>"
        parts = arg.split()
        if len(parts) < 2:
            return f"[CQ:at,qq={send_id}] 格式错误，示例：@机器人 follow AK-47 | 红线 (崭新出厂) 100 <up或者down/不写默认现价到这个的趋势>"

        print(f"parts is {parts}")
        if parts[-1] in ["up", "down"]:
            follow_type = 1 if parts[-1] == "up" else -1
            try:
                price = float(parts[-2])
            except:
                return f"[CQ:at,qq={send_id}] 格式错误，价格不对？？？，现在是{parts[-2]},应该是一个数字\n示例：@机器人 follow AK-47 | 红线 (崭新出厂) 100 <up或者down/不写默认现价到这个的趋势>"
            
            item_name = " ".join(parts[:-2])
            
        else:
            try:
                price = float(parts[-1])
            except:
                return f"[CQ:at,qq={send_id}] 格式错误，价格不对？？？，现在是{parts[-1]},应该是一个数字\n示例：@机器人 follow AK-47 | 红线 (崭新出厂) 100 <up或者down/不写默认现价到这个的趋势>"
        
            item_name = " ".join(parts[:-1])
            follow_type = 0  # 默认逻辑
        
        if not item_name:
            return f"[CQ:at,qq={send_id}] 格式错误，名字不对？？？，现在是{item_name}\n示例：@机器人 follow AK-47 | 红线 (崭新出厂) 100 <up或者down/不写默认现价到这个的趋势>"
        
        # 搜索 item_id
        print(f"args is {price},{follow_type},{item_name},{parts}")

        target_id = config.tye_get_item_name(item_name)
        target_name = ""
        target_item_list = []

        print(f"item_id {target_id}")
        
        if target_id == -1:
            datas = crawler.search_item(item_name)['data']

            print(f"data is {datas}")
                
            for key, value in datas.items():
                name = value['name']
                if item_name == name:
                    target_id = key
                    target_name = name
                    break
                else:
                    target_item_list.append(name)

            config.modify_watch_item(target_id,target_name, 1)
            handle_add_item(target_id)
        print(f"target_name is {target_name},item_name is {item_name}")
        
        if target_id == -1:
            msg = f"[CQ:at,qq={send_id}] 名字不完全对，猜你喜欢：\n"
            for item in target_item_list:
                msg += f"{item}\n"
            return msg

        # 在已监控的内容里面
        if follow_type == 0:
            curr_price = curr_items_price[target_id]
            if curr_price < price:
                follow_type = 1
            else:
                follow_type = -1

        code = follow_item(send_id, target_id, price, follow_type)
        if code == 1:
            return f"[CQ:at,qq={send_id}] 添加成功，开始监控{target_name}，在价格为{price}会进行通知"
        elif code == -1:
            return f"[CQ:at,qq={send_id}] 干嘛。。。又要监控一样的价格"
        elif code == 0:
            return f"[CQ:at,qq={send_id}] 更新价格成功，{target_name}在价格为{price}会进行通知"
            
    else:
        return f"[CQ:at,qq={send_id}] 格式不对，改一下.\n格式为：\n添加饰品：@机器人 add 饰品全名；\n删除饰品：@机器人 del 饰品全名\n查看当前监控列表：@机器人 check"
    
    
    target_id = -1
    target_name = ""
    target_item_list = []

    time.sleep(2)
    datas = crawler.search_item(arg)['data']
    for key, value in datas.items():
        name = value['name']
        if arg == name:
            target_id = key
            target_name = name
            break
        else:
            target_item_list.append(name)

    if target_id == -1:
        msg = "名字不完全对，猜你喜欢：\n"
        for item in target_item_list:
            msg += f"{item}\n"
        return msg
    
    config.modify_watch_item(target_id,target_name,isAdd)
    if isAdd == 1:
        return handle_add_item(target_id)
    else:
        return handle_del_item(target_id)

def save_follow_map():
    #storage.save_json("follow_map.json",{"follow_map":follow_map})
    return 
def load_follow_map():
    # global follow_map
    # data = storage.load_json("follow_map.json")
    # if "follow_map" in data:
    #     follow_map = ["follow_map"]
    # else:
    #     follow_map = {}
    return
def handle_add_item(new_id):
    try:
        with items_lock:
            if new_id not in items_id:
                items_id.append(new_id)
                init_item_history(new_id)
                return "添加成功"
            return "这个饰品已经加过了，要干嘛。。。"
        return f"已添加监控道具 {new_id}"
    except Exception as e:
        return f"添加失败: {e}"
    
def handle_del_item(new_id):
    try:
        with items_lock:
            if new_id in items_id:
                items_id.remove(new_id)
                return f"已删除监控道具 {new_id}"
            return "这个饰品没在监控列表，要干嘛。。。"
    except Exception as e:
        return f"删除失败: {e}"

# 配置参数
TIME_INTERVAL = 60 * 30      # 10分钟
def check_need_send_msg(item_id, time, price, trend):
    """
    time_str: "2026-03-18 12:00:00"
    price: float
    """
    now_time = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")

    # --------------------------
    # 1️⃣ 第一次直接发送
    # --------------------------
    if item_id not in last_notify:
        last_notify[item_id] = {
            "time": now_time,
            "price": price
        }
        return True

    last_time = last_notify[item_id]["time"]
    last_price = last_notify[item_id]["price"]

    # --------------------------
    # 2️⃣ 时间间隔判断
    # --------------------------
    time_diff = (now_time - last_time).total_seconds()

    if time_diff < TIME_INTERVAL:
        return False

    # --------------------------
    # 3️⃣ 价格变化判断
    # --------------------------
    price_diff = abs(price - last_price)
    percent = price_diff / last_price if last_price != 0 else 0
    
    if trend == Trend.down:
        if percent > warning_percent:
            last_notify[item_id] = {
                "time": now_time,
                "price": price
            }
            return True
    else:
        if percent > warning_percent:
            last_notify[item_id] = {
                "time": now_time,
                "price": price
            }
            return True

    # --------------------------
    # 4️⃣ 不发送
    # --------------------------
    return False


# 下面的应该全部都是历史数据
# 只有steam有, 数据很怪
# 先不用了
def time_to_turnover_record(item_id):
    data = crawler.post_item_turnover_num_chart(item_id, 1095)
    times = data["timestamp"]
    main_data = data["main_data"]
    
    dic = {}
    index = 0
    for time in times:
        date = ts_to_date(time)
        price = main_data[index]
        dic[date] = price
        index += 1

    result = hourly_high(dic)
    return result
    
def time_to_price_record(item_id):
    data = crawler.post_item_sell_price_chart(item_id, 7)
    if data is None:
        return None,None
    times = data["timestamp"]
    main_data = data["main_data"]

    dic = {}
    index = 0
    now_price = 0
    for time in times:
        date = ts_to_date(time)
        price = main_data[index]
        dic[date] = price
        index += 1
        now_price = price    
    
    result = hourly_last(dic)
    return result, now_price
    
def time_to_sell_num_record(item_id):
    data = crawler.post_item_sell_num_chart(item_id, 7)
    times = data["timestamp"]
    main_data = data["main_data"]
    
    time_to_sell_num = {}
    index = 0
    for time in times:
        date = ts_to_date(time)
        price = main_data[index]
        time_to_sell_num[date] = price
        index += 1
    
    result = hourly_high(time_to_sell_num)
    return result

# 可以得到给定的数据中的每小时最高的价格
def hourly_high(data):
    groups = defaultdict(list)

    for t, price in data.items():
        dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        hour = dt.strftime("%Y-%m-%d %H")

        groups[hour].append((t, price))

    result = {}

    for hour, records in groups.items():
        result[hour] = max(records, key=lambda x: x[1])

    return result

def hourly_last(data):
    result = {}

    for t, price in data.items():
        dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        hour = dt.strftime("%Y-%m-%d %H")

        # 直接覆盖，保留最后一个
        if hour not in result or t > result[hour][0]:
            result[hour] = (t, price)

    return result

def ts_to_date(ts):
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")

def get_now_time():
    now = datetime.now()

    # 当前小时 key
    hour_key = now.strftime("%Y-%m-%d %H")
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    return hour_key, time_str

def normalize_price(price, digits=1):
    q = '0.' + '0' * (digits - 1) + '1'
    return float(
        Decimal(str(price)).quantize(Decimal(q), rounding=ROUND_HALF_UP)
    )