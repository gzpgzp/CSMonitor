with open('qq_robot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 send_sell_msg 函数后添加 send_sell_file 函数
old_code = '''def send_sell_msg(message):
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

def send_msg(message):'''

new_code = '''def send_sell_msg(message):
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

def send_msg(message):'''

content = content.replace(old_code, new_code)

with open('qq_robot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
