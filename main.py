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
    robot.load_group_ids()
     
    threading.Thread(target=robot.start_ws).start()
     
    config.init_data()
    
    # 创建并启动 MonitorService
    svc = monitor_service.MonitorService(config.items_id)
    monitor_service.service = svc
    svc.start(5)

    # 主线程保持运行，防止程序退出
    while True:
        time.sleep(60)

if __name__ == "__main__":
    run()
