import config
import monitor_service
import csqaq_api as crawler
import qq_robot as robot
import storage
import time
import threading

def run():    
    config.init_config()
    crawler.init()
     
    threading.Thread(target=robot.start_ws).start()
     
    config.init_data()
    
    # 创建并启动 MonitorService
    svc = monitor_service.MonitorService(config.items_id)
    monitor_service.service = svc
    svc.start(5)

if __name__ == "__main__":
    run()
