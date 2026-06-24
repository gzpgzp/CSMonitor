with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 _generate_sell_csv 方法，使用固定文件名
old_code = '''    def _generate_sell_csv(self, time_str):
        """生成在售监控 CSV 文件，返回文件路径"""
        import csv
        csv_dir = os.path.join(base_dir, "data", "sell_reports")
        os.makedirs(csv_dir, exist_ok=True)
        
        csv_filename = f"sell_report_{time_str.replace(':', '').replace(' ', '_')}.csv"
        csv_path = os.path.join(csv_dir, csv_filename)'''

new_code = '''    def _generate_sell_csv(self, time_str):
        """生成在售监控 CSV 文件，返回文件路径（只保留一个最新文件）"""
        import csv
        csv_dir = os.path.join(base_dir, "data", "sell_reports")
        os.makedirs(csv_dir, exist_ok=True)
        
        # 固定文件名，每次覆盖
        csv_filename = "sell_report_latest.csv"
        csv_path = os.path.join(csv_dir, csv_filename)'''

content = content.replace(old_code, new_code)

# 同时修改发送时的文件名
old_code2 = '''                    if csv_path:
                        # 发送 CSV 文件到在售监控群
                        qq_robot.send_sell_file(csv_path, f"在售监控报告_{time_str.replace(':', '-')}.csv")'''

new_code2 = '''                    if csv_path:
                        # 发送 CSV 文件到在售监控群
                        qq_robot.send_sell_file(csv_path, f"在售监控报告.csv")'''

content = content.replace(old_code2, new_code2)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
