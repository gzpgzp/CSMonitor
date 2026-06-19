import requests
import http.client
import json
import os

import config as cfg
from enum import Enum
from storage import load_json
from datetime import datetime
import traceback
import time

class WeaponState(Enum):
    Factory_New = 1 # 崭新出厂
    Minimal_Wear = 2 # 略有磨损
    Field_Tested = 3 # 久经沙场
    Well_Worn = 4 # 破损不堪
    Battle_Scarred = 5 # 战痕累累

normal_header = {}
json_request_header = {}

BIND_FILE = "bind_date.txt"
last_request_time = ""

def init():
    global normal_header
    global json_request_header
    global last_request_time
    
    last_request_time = datetime.now()
    
    normal_header = {
        "ApiToken": cfg.API_TOKEN,
        "Connection": "close"
    }
    json_request_header = {
        'ApiToken': cfg.API_TOKEN,
        'Content-Type': 'application/json'
    }
    combine_ip()

# 只做一次初始化
def combine_ip(force = False):
    if need_bind_ip() or force:
        post_request("/api/v1/sys/bind_local_ip","", normal_header)
        mark_bind_done()

def check_need_delay():
    return (datetime.now()- last_request_time).total_seconds() < 2

def need_bind_ip():
    today = datetime.now().strftime("%Y-%m-%d")

    # 如果文件不存在 → 第一次运行
    if not os.path.exists(BIND_FILE):
        return True

    with open(BIND_FILE, "r") as f:
        last_date = f.read().strip()

    return last_date != today


def mark_bind_done():
    today = datetime.now().strftime("%Y-%m-%d")
    with open(BIND_FILE, "w") as f:
        f.write(today)

def get_request(url, payload, header, is_first_request = True):
    if check_need_delay():
        time.sleep(2)
    print(f"get request {url}")
    conn = http.client.HTTPSConnection("api.csqaq.com", timeout=8)
    try:
        conn.request("GET", url, payload, header)
    
        res = conn.getresponse()
        data = res.read()
        data_utf8 = json.loads(data.decode("utf-8"))
        code = data_utf8.get('code', -1)
        global last_request_time
        last_request_time = datetime.now()

        if code == 401 and is_first_request:
            print(f'code error 401')
            combine_ip(True)
            return get_request(url,payload, header, False)
        if code != 200 and is_first_request:
            print(f'code error, code is {code}')
            return get_request(url,payload, header, False)
        if code != 200:
            return None
    except Exception as e:
        print(f"[GET ERROR] {e}")
        traceback.print_exc()
        if is_first_request:
            return get_request(url,payload, header, False)
        return  None
    finally:
        conn.close()
        
    return data_utf8.get('data')

def post_request(url, payload, header, is_first_request = True):
    if check_need_delay():
        time.sleep(2)

    print(f"post request {url}")
    conn = http.client.HTTPSConnection("api.csqaq.com", timeout=8)
    try:
        conn.request("POST", url, payload, header)
        res = conn.getresponse()
        data = res.read()
        data_utf8 = json.loads(data.decode("utf-8"))
        code = data_utf8.get('code', -1)
        
        global last_request_time
        last_request_time = datetime.now()

        if code == 401 and is_first_request:
            combine_ip(True)
            return post_request(url,payload, header, False)
        if code != 200 and is_first_request:
            print(f'code error, code is {code}')
            return post_request(url,payload, header, False)
        if code != 200:
            return None
    except Exception as e:
        print("[POST ERROR]", e)
        traceback.print_exc()
        if is_first_request:
            return post_request(url,payload, header, False)
        return None
    finally:
        conn.close()
        
    return data_utf8.get('data')


# 首页数据
def get_home_data():
    home_data_url = "/api/v1/current_data?type=init"
    get_request(home_data_url, "", normal_header)
    
# 查询物品信息
def search_item(item_name):
    url = "/api/v1/info/get_good_id"
    payload = json.dumps({
        "page_index": 1,
        "page_size": 100,
        "search": item_name
    })

    return post_request(url, payload, json_request_header)
    
# 单个物品请求
def get_item_info(item_id):
    url = f"/api/v1/info/good?id={item_id}"
    return get_request(url, "", normal_header)

# 出售价
def post_item_sell_price_chart(item_id, period = "7"):
    return post_item_chart(item_id, "sell_price", period)

# 在售数
def post_item_sell_num_chart(item_id, period = "7"):
    return post_item_chart(item_id, "sell_num", period)

def post_item_buy_num_chart(item_id, period = "7"):
    return post_item_chart(item_id, "buy_num", period)

# 日成交量
def post_item_turnover_num_chart(item_id, period = "1095"):
    return post_item_chart(item_id, "turnover_number", period,3)

# 请求图表数据
def post_item_chart(item_id, key_word, period="7", platform=2):
    url = "/api/v1/info/chart"
    payload = json.dumps({
        "good_id": f"{item_id}",
        "key": key_word,
        "platform": platform, # 2代表悠悠
        "period": period,
        "style": "all_style"
    })
    
    return post_request(url, payload, json_request_header)










    