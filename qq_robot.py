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
target_group_ids = set()  # 监控的群组列表，启动时从 config.json 加载
self_id = "2092836515"
debug = False

def load_group_ids():
    """从 data/monitor_groups.json 加载监控群列表"""
    global target_group_ids
    try:
        import storage
        data = storage.load_json("data/monitor_groups.json")
        ids = data.get("group_ids", []) if isinstance(data, dict) else []
        target_group_ids = set(str(i) for i in ids)
        if not target_group_ids:
            print("[Robot] 暂无监控群，请在群内发送 .addmonitor 添加")
        else:
            print(f"[Robot] 已加载监控群: {target_group_ids}")
    except Exception as e:
        print(f"[Robot] 加载监控群失败: {e}")

def save_group_ids():
    """保存监控群列表到 data/monitor_groups.json"""
    try:
        import storage
        storage.save_json("data/monitor_groups.json", {"group_ids": sorted(target_group_ids)})
    except Exception as e:
        print(f"[Robot] 保存监控群失败: {e}")

def add_monitor_group(group_id):
    """添加群到监控列表"""
    group_id = str(group_id)
    if group_id in target_group_ids:
        return False
    target_group_ids.add(group_id)
    save_group_ids()
    return True

def remove_monitor_group(group_id):
    """从监控列表移除群"""
    group_id = str(group_id)
    if group_id not in target_group_ids:
        return False
    target_group_ids.discard(group_id)
    save_group_ids()
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

def send_msg(message):
    if debug:
        return

    if not message:
        return

    for gid in list(target_group_ids):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 3000, timeout=10)
            payload = json.dumps({
                "group_id": gid,
                "message": message
            })
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {token}"
            }
            conn.request("POST", "/send_group_msg", payload, headers)
            res = conn.getresponse()
            print(res.read().decode("utf-8"))
        except Exception as e:
            print("[SEND ERROR]", e)
            traceback.print_exc()
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

    # .addmonitor / .delmonitor 命令：任何群都能触发
    if raw_msg.strip() == ".addmonitor" or raw_msg.strip() == f"[CQ:at,qq={self_id}] addmonitor":
        if add_monitor_group(group_id):
            _send_to_group(group_id, f"✅ 已将本群（{group_id}）加入监控，之后的告警消息将推送到这里。")
        else:
            _send_to_group(group_id, f"本群（{group_id}）已在监控列表中。")
        return

    if raw_msg.strip() == ".delmonitor" or raw_msg.strip() == f"[CQ:at,qq={self_id}] delmonitor":
        if remove_monitor_group(group_id):
            _send_to_group(group_id, f"✅ 已将本群（{group_id}）从监控列表移除，不再推送告警消息。")
        else:
            _send_to_group(group_id, f"本群（{group_id}）不在监控列表中。")
        return

    # 其他命令只处理已监控的群
    if group_id not in target_group_ids:
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
    """发消息到指定群（不依赖 target_group_ids）"""
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
