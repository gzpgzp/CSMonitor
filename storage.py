import json
import os

hourly_prices = {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_json(file_path):
    # 如果文件不存在，创建一个空文件并写入空字典
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
        return {}

    # 如果存在，正常读取
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)