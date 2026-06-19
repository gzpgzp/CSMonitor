import storage
import csqaq_api as crawler

API_TOKEN = ""
watch_items = {}
items_id = []
items_id_to_name = {}

# 可通过 modify 命令修改的参数定义
# key: 中文参数名, value: (json_key, 类型, 说明)
MODIFIABLE_PARAMS = {
    "检查间隔":  ("check_interval",             int,   "监控轮询间隔（秒）"),
    "价格警告百分比": ("alert_rise",               float, "价格上涨告警百分比（如0.05表示5%）"),
    "价格回调百分比": ("alert_drop",               float, "价格下跌告警百分比（如0.05表示5%）"),
    "在售百分比警告": ("sell_num_warning_percent", float, "在售数量增减告警百分比（如0.1表示10%）"),
    "在售波峰阈值": ("sell_num_change_percent",   float, "在售数量波峰波谷过滤阈值（如0.05表示5%）"),
    "价格通知间隔": ("time_interval",             int,   "价格通知最小间隔（秒）"),
    "在售通知间隔": ("sell_num_time_interval",    int,   "在售数量通知最小间隔（秒）"),
    "波峰波谷阈值": ("change_percent",            float, "价格波峰波谷过滤阈值（如0.05表示5%）"),
    "上涨警告百分比": ("warning_percent",          float, "价格上涨突破告警百分比（如0.05表示5%）"),
}

def init_config():
    data = storage.load_json("config.json")

    global watch_items
    watch_items = storage.load_json("watch_items.json")['watch_items']
    global API_TOKEN
    API_TOKEN = data['api_token']

def init_data():
    global items_id
    global items_id_to_name
    items_id, items_id_to_name = get_items_id(watch_items)

def get_items_id(watch_items):
    print(watch_items)
    watch_items_id = []
    watch_items_id_to_name = {}
    for item in watch_items:
        result = crawler.search_item(item)
        if result is None:
            print(f"[Config] 搜索饰品失败，跳过: {item}")
            continue
        datas = result.get('data', {})
        if not datas:
            print(f"[Config] 搜索饰品无结果，跳过: {item}")
            continue
        for key, value in datas.items():
            print(value)
            if item == value['name']:
                watch_items_id.append(key)
                watch_items_id_to_name[key] = item
                break
    return watch_items_id, watch_items_id_to_name

def get_item_name(item_id):
    if item_id in items_id_to_name:
        return items_id_to_name[item_id]
    return ""

def tye_get_item_name(item_name):
    for key, value in items_id_to_name.items():
        if value == item_name:
            return key
        
    return -1

def modify_watch_item(item_id, item_name, isAdd):
    if isAdd == 1:
        if item_id in items_id_to_name:
            return
        items_id_to_name[item_id] = item_name
        watch_items.append(item_name)
    else:
        if item_id not in items_id_to_name:
            return
        del items_id_to_name[item_id]
        watch_items.remove(item_name)

    storage.save_json("watch_items.json", {"watch_items":watch_items})

def get_param(key):
    """获取参数值，优先从 config.json 读取"""
    data = storage.load_json("config.json")
    return data.get(key)

def set_param(key, value):
    """设置参数值并保存到 config.json"""
    data = storage.load_json("config.json")
    data[key] = value
    storage.save_json("config.json", data)
