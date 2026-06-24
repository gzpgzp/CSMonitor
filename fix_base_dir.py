with open('monitor_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 import 之后添加 base_dir
old_code = '''from monitor_context import special_monitor_context


class Trend(Enum):'''

new_code = '''from monitor_context import special_monitor_context

base_dir = os.path.dirname(os.path.abspath(__file__))


class Trend(Enum):'''

content = content.replace(old_code, new_code)

with open('monitor_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
