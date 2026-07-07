with open('config.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加新的配置参数
old_params = '''MODIFIABLE_PARAMS = {
    "检查间隔":  ("check_interval",             int,   "监控轮询间隔（秒）"),
    "价格警告百分比": ("alert_rise",               float, "价格上涨告警百分比（如0.05表示5%）"),
    "价格回调百分比": ("alert_drop",               float, "价格下跌告警百分比（如0.05表示5%）"),
    "在售百分比警告": ("sell_num_warning_percent", float, "在售数量增减告警百分比（如0.1表示10%）"),
    "在售波峰阈值": ("sell_num_change_percent",   float, "在售数量波峰波谷过滤阈值（如0.05表示5%）"),
    "价格通知间隔": ("time_interval",             int,   "价格通知最小间隔（秒）"),
    "在售通知间隔": ("sell_num_time_interval",    int,   "在售数量通知最小间隔（秒）"),
    "波峰波谷阈值": ("change_percent",            float, "价格波峰波谷过滤阈值（如0.05表示5%）"),
    "上涨警告百分比": ("warning_percent",          float, "价格上涨突破告警百分比（如0.05表示5%）"),
}'''

new_params = '''MODIFIABLE_PARAMS = {
    "检查间隔":  ("check_interval",             int,   "监控轮询间隔（秒）"),
    "价格警告百分比": ("alert_rise",               float, "价格上涨告警百分比（如0.05表示5%）"),
    "价格回调百分比": ("alert_drop",               float, "价格下跌告警百分比（如0.05表示5%）"),
    "在售百分比警告": ("sell_num_warning_percent", float, "在售数量增减告警百分比（如0.1表示10%）"),
    "在售波峰阈值": ("sell_num_change_percent",   float, "在售数量波峰波谷过滤阈值（如0.05表示5%）"),
    "价格通知间隔": ("time_interval",             int,   "价格通知最小间隔（秒）"),
    "在售通知间隔": ("sell_num_time_interval",    int,   "在售数量通知最小间隔（秒）"),
    "波峰波谷阈值": ("change_percent",            float, "价格波峰波谷过滤阈值（如0.05表示5%）"),
    "上涨警告百分比": ("warning_percent",          float, "价格上涨突破告警百分比（如0.05表示5%）"),
    "CSV变化阈值": ("csv_change_percent",         float, "在售监控CSV变化幅度阈值（如0.1表示10%）"),
}'''

content = content.replace(old_params, new_params)

with open('config.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
