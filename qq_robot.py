import http.client
import json
import os

import websocket
import json
import threading
import traceback
import time
import monitor_service

base_dir = os.path.dirname(os.path.abspath(__file__))

ws_url = "ws://127.0.0.1:3000/ws"
token = "07xQUqq18.rLfo5h" 
price_monitor_groups = set()   # 价格监控群（接收涨幅/跌幅报告）
sell_monitor_groups = set()    # 在售监控群（接收在售激增/锐减报告）
self_id = "2092836515"
debug = False

def load_group_ids():
    """从 data/monitor_groups.json 加载价格监控群，从 data/sell_monitor_groups.json 加载在售监控群"""
    global price_monitor_groups, sell_monitor_groups
    try:
        import storage
        # 价格监控群
        data = storage.load_json("data/monitor_groups.json")
        ids = data.get("group_ids", []) if isinstance(data, dict) else []
        price_monitor_groups = set(str(i) for i in ids)
        if price_monitor_groups:
            print(f"[Robot] 已加载价格监控群: {price_monitor_groups}")
        else:
            print("[Robot] 暂无价格监控群，请在群内发送 .addmonitor 添加")
        # 在售监控群
        data2 = storage.load_json("data/sell_monitor_groups.json")
        ids2 = data2.get("group_ids", []) if isinstance(data2, dict) else []
        sell_monitor_groups = set(str(i) for i in ids2)
        if sell_monitor_groups:
            print(f"[Robot] 已加载在售监控群: {sell_monitor_groups}")
        else:
            print("[Robot] 暂无在售监控群，请在群内发送 .addsellmonitor 添加")
    except Exception as e:
        print(f"[Robot] 加载监控群失败: {e}")

def save_price_groups():
    """保存价格监控群"""
    try:
        import storage
        storage.save_json("data/monitor_groups.json", {"group_ids": sorted(price_monitor_groups)})
    except Exception as e:
        print(f"[Robot] 保存价格监控群失败: {e}")

def save_sell_groups():
    """保存在售监控群"""
    try:
        import storage
        storage.save_json("data/sell_monitor_groups.json", {"group_ids": sorted(sell_monitor_groups)})
    except Exception as e:
        print(f"[Robot] 保存在售监控群失败: {e}")

def add_price_group(group_id):
    group_id = str(group_id)
    if group_id in price_monitor_groups:
        return False
    price_monitor_groups.add(group_id)
    save_price_groups()
    return True

def remove_price_group(group_id):
    group_id = str(group_id)
    if group_id not in price_monitor_groups:
        return False
    price_monitor_groups.discard(group_id)
    save_price_groups()
    return True

def add_sell_group(group_id):
    group_id = str(group_id)
    if group_id in sell_monitor_groups:
        return False
    sell_monitor_groups.add(group_id)
    save_sell_groups()
    return True

def remove_sell_group(group_id):
    group_id = str(group_id)
    if group_id not in sell_monitor_groups:
        return False
    sell_monitor_groups.discard(group_id)
    save_sell_groups()
    return True

def start_ws():
    ws = websocket.WebSocketApp(
        ws_url,
        header={"Authorization": f"Bearer {token}"},
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    ws.run_forever(ping_interval=20, ping_timeout=10)

def on_message(ws, message):
    try:
        data = json.loads(message)
        handle_message(data)
    except Exception as e:
        print("[WS MESSAGE ERROR]", e)
        traceback.print_exc()

def on_error(ws, error):
    print("[WS ERROR]", error)

def on_close(ws, close_status_code, close_msg):
    print("[WS CLOSED]", close_status_code, close_msg)
    # 尝试重连
    time.sleep(3)
    start_ws()
    
def on_open(ws):
    print("[WS CONNECTED] 机器人已连接")

def send_price_msg(message):
    """发送价格监控消息到所有价格监控群"""
    if debug or not message:
        return
    for gid in list(price_monitor_groups):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 3000, timeout=10)
            payload = json.dumps({"group_id": gid, "message": message})
            headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {token}"}
            conn.request("POST", "/send_group_msg", payload, headers)
            res = conn.getresponse()
            print(res.read().decode("utf-8"))
        except Exception as e:
            print("[SEND ERROR]", e)
        finally:
            try:
                conn.close()
            except:
                pass

def send_sell_msg(message):
    """发送在售监控消息到所有在售监控群"""
    if debug or not message:
        return
    for gid in list(sell_monitor_groups):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 3000, timeout=10)
            payload = json.dumps({"group_id": gid, "message": message})
            headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {token}"}
            conn.request("POST", "/send_group_msg", payload, headers)
            res = conn.getresponse()
            print(res.read().decode("utf-8"))
        except Exception as e:
            print("[SEND ERROR]", e)
        finally:
            try:
                conn.close()
            except:
                pass

def send_sell_file(file_path, file_name):
    """发送文件到所有在售监控群"""
    if debug or not file_path:
        return
    for gid in list(sell_monitor_groups):
        try:
            # OneBot 11 上传文件 API
            conn = http.client.HTTPConnection("127.0.0.1", 3000, timeout=30)
            payload = json.dumps({
                "group_id": gid,
                "file": file_path,
                "name": file_name
            })
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {token}"
            }
            conn.request("POST", "/upload_group_file", payload, headers)
            res = conn.getresponse()
            result = res.read().decode("utf-8")
            print(f"[Upload {gid}] {result}")
        except Exception as e:
            print("[UPLOAD ERROR]", e)
            traceback.print_exc()
        finally:
            try:
                conn.close()
            except:
                pass

def send_msg(message):
    """兼容旧接口：同时发到价格监控群和在售监控群"""
    if debug or not message:
        return
    for gid in list(price_monitor_groups | sell_monitor_groups):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 3000, timeout=10)
            payload = json.dumps({"group_id": gid, "message": message})
            headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {token}"}
            conn.request("POST", "/send_group_msg", payload, headers)
            res = conn.getresponse()
            print(res.read().decode("utf-8"))
        except Exception as e:
            print("[SEND ERROR]", e)
        finally:
            try:
                conn.close()
            except:
                pass

def handle_message(message_data):
    if message_data.get("post_type") != "message":
        return
    if message_data.get("message_type") != "group":
        return

    raw_msg = message_data.get("raw_message", "")
    group_id = str(message_data.get("group_id", ""))
    is_price_monitor = group_id in price_monitor_groups
    is_sell_monitor = group_id in sell_monitor_groups

    # 价格监控命令
    if raw_msg.strip() == ".addmonitor" or raw_msg.strip() == f"[CQ:at,qq={self_id}] addmonitor":
        if add_price_group(group_id):
            _send_to_group(group_id, f"✅ 已将本群（{group_id}）加入价格监控，之后的涨跌告警将推送到这里。")
        else:
            _send_to_group(group_id, f"本群（{group_id}）已在价格监控列表中。")
        return

    if raw_msg.strip() == ".delmonitor" or raw_msg.strip() == f"[CQ:at,qq={self_id}] delmonitor":
        if remove_price_group(group_id):
            _send_to_group(group_id, f"✅ 已将本群（{group_id}）从价格监控列表移除。")
        else:
            _send_to_group(group_id, f"本群（{group_id}）不在价格监控列表中。")
        return

    # 在售监控命令
    if raw_msg.strip() == ".addsellmonitor" or raw_msg.strip() == f"[CQ:at,qq={self_id}] addsellmonitor":
        if add_sell_group(group_id):
            _send_to_group(group_id, f"✅ 已将本群（{group_id}）加入在售监控，之后的在售增减告警将推送到这里。")
        else:
            _send_to_group(group_id, f"本群（{group_id}）已在在售监控列表中。")
        return

    if raw_msg.strip() == ".delsellmonitor" or raw_msg.strip() == f"[CQ:at,qq={self_id}] delsellmonitor":
        if remove_sell_group(group_id):
            _send_to_group(group_id, f"✅ 已将本群（{group_id}）从在售监控列表移除。")
        else:
            _send_to_group(group_id, f"本群（{group_id}）不在在售监控列表中。")
        return

    # 其他命令只处理已监控的群（价格或在售至少一个）
    if not is_price_monitor and not is_sell_monitor:
        return

    # 判断是否以 . 开头或者被 @
    if is_mentioned(message_data) or raw_msg.startswith("."):
        user_id = message_data.get("user_id")

        print(raw_msg)
        if monitor_service.service is None:
            send_msg("监控服务未启动")
            return
        try:
            reply = monitor_service.service.handle_robot_msg(user_id, raw_msg)
        except Exception as e:
            print("[HANDLE ERROR]", e)
            traceback.print_exc()
            reply = f"处理命令时出错了: {e}"
        if reply:
            send_msg(reply)

def _send_to_group(group_id, message):
    """发消息到指定群（不依赖任何监控列表）"""
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 3000, timeout=10)
        payload = json.dumps({"group_id": group_id, "message": message})
        headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {token}"}
        conn.request("POST", "/send_group_msg", payload, headers)
        res = conn.getresponse()
        print(res.read().decode("utf-8"))
    except Exception as e:
        print("[SEND ERROR]", e)
    finally:
        try:
            conn.close()
        except:
            pass

def is_mentioned(message_data):
    msg = message_data.get("message", "")
    return f"[CQ:at,qq={self_id}]" in msg
