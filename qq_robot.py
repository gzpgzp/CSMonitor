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
target_group_id = "620195557"
self_id = "2092836515"
debug = False

def start_ws():
    ws = websocket.WebSocketApp(
        ws_url,
        header={"Authorization": f"Bearer {token}"},
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )

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

    try:
        conn = http.client.HTTPConnection("127.0.0.1", 3000, timeout=10)
        payload = json.dumps({
            "group_id": target_group_id,
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

    # 判断是否以 . 开头或者被 @
    raw_msg = message_data.get("raw_message", "")
    if is_mentioned(message_data) or raw_msg.startswith("."):
        user_id = message_data.get("user_id")
        group_id = message_data.get("group_id")
        
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

def is_mentioned(message_data):
    msg = message_data.get("message", "")
    return f"[CQ:at,qq={self_id}]" in msg
