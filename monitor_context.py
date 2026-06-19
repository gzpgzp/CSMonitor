class monitor_context:
    def __init__(self, sell_price, sell_num, buy_num, buy_price):
        self.sell_price = sell_price
        self.sell_num = sell_num
        self.buy_num = buy_num
        self.buy_price = buy_price
        
class special_monitor_context:
    def __init__(self, qq_id, monitor_items):
        self.qq_id = qq_id
        self.monitor_items = monitor_items
    
    def add_item(self,item_id, price, trend):
        if item_id not in self.monitor_items:
            self.monitor_items[item_id] = monitor_item(item_id, price, trend, False)
            return 1 # 添加成功
        else:
            if price == self.monitor_items[item_id].price:
                return -1 # 已有相同价格
            else:
                self.monitor_items[item_id].price = price
                self.monitor_items[item_id].trend = trend
                self.monitor_items[item_id].is_notify = False
                return 0 # 更新价格成功
    
    def check_need_notify(self, item_id, price):
        if item_id in self.monitor_items:
            target_price = self.monitor_items[item_id].price
            trend = self.monitor_items[item_id].trend
            if trend == 1 and price >= target_price:
                # 等价格上涨到目标价
                return True
            elif trend == -1 and price <= target_price:
                # 等价格下跌到目标价
                return True
            elif trend == 0:
                # 默认：价格到达目标价即通知
                if price == target_price:
                    return True
        return False
    
    def notify(self,item_id):
        item = self.monitor_items[item_id]
        item.is_notify = True
        target_price = item.price
        del self.monitor_items[item_id]
        return target_price
class monitor_item:
    def __init__(self, item_id, price, trend, is_notify):
        self.item_id = item_id
        self.price = price
        self.trend = trend
        self.is_notify = is_notify
        