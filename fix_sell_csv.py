import re

with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换在售报告发送逻辑
old_code = '''                # 本轮结束，发送在售报告（激增/锐减分两条消息，默认各发前10条）
                if not first_round:
                    time_str = self._now()

                    # 先保存完整报告（无论是否有内容）
                    inc_msgs = self._group_sell_buffer(self._sell_buffer, True)
                    dec_msgs = self._group_sell_buffer(self._sell_buffer, False)
                    self._last_sell_report["time"] = time_str
                    self._last_sell_report["increase"] = inc_msgs
                    self._last_sell_report["decrease"] = dec_msgs

                    # 有告警发报告，没告警发提示
                    if inc_msgs or dec_msgs:
                        # 激增报告
                        if inc_msgs:
                            show = inc_msgs[:2]
                            more = len(inc_msgs) - 2
                            header = f"📦 在售激增报告 ({time_str})\\n{'═' * 22}"
                            body = ("\\n───────────\\n").join(show)
                            footer = f"\\n───────────\\n...还有{more}条，发送 .checksell all 查看全部" if more > 0 else ""
                            qq_robot.send_sell_msg(f"{header}\\n{body}{footer}")

                        # 锐减报告
                        if dec_msgs:
                            show = dec_msgs[:2]
                            more = len(dec_msgs) - 2
                            header = f"🔥 在售锐减报告 ({time_str})\\n{'═' * 22}"
                            body = ("\\n───────────\\n").join(show)
                            footer = f"\\n───────────\\n...还有{more}条，发送 .checksell all 查看全部" if more > 0 else ""
                            qq_robot.send_sell_msg(f"{header}\\n{body}{footer}")
                    else:
                        print(f"[SellScan] 第{scan_index}轮结束，无异常")'''

new_code = '''                # 本轮结束，生成并发送 CSV 报告
                if not first_round:
                    time_str = self._now()

                    # 生成 CSV 文件
                    csv_path = self._generate_sell_csv(time_str)
                    if csv_path:
                        # 发送 CSV 文件到在售监控群
                        qq_robot.send_sell_file(csv_path, f"在售监控报告_{time_str.replace(':', '-')}.csv")

                    # 保存完整报告供 .checksell 命令查询
                    inc_msgs = self._group_sell_buffer(self._sell_buffer, True)
                    dec_msgs = self._group_sell_buffer(self._sell_buffer, False)
                    self._last_sell_report["time"] = time_str
                    self._last_sell_report["increase"] = inc_msgs
                    self._last_sell_report["decrease"] = dec_msgs'''

content = content.replace(old_code, new_code)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
