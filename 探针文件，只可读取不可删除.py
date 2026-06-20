import uiautomation as auto
import re

dy_pane = auto.PaneControl(searchDepth=1, ClassName="Chrome_WidgetWin_1", Name="抖音")

if not dy_pane.Exists(0):
    print("未找到抖音窗口")
    exit()

print("=" * 80)
print("精确提取 v5 - 修复：同时获取当前播放时间 + 视频总时长")
print("策略：提取同进度条行全部时间控件，区分当前/总时长")
print("=" * 80)

# 1. 收集所有有真实坐标的文本控件
all_controls = []
for control, depth in auto.WalkControl(dy_pane):
    name = control.Name or ""
    name_stripped = name.strip()
    if not name_stripped:
        continue
    
    try:
        rect = control.BoundingRectangle
        top = rect.top
        left = rect.left
        if top == 0 and left == 0 and rect.right == 0 and rect.bottom == 0:
            continue
    except:
        continue
    
    all_controls.append({
        'text': name_stripped,
        'top': top,
        'left': left,
        'depth': depth,
        'type': control.ControlTypeName or ""
    })

# 2. 筛选所有时间格式控件 xx:xx
time_controls_all = [c for c in all_controls if re.match(r'^\d{1,2}:\d{1,2}(:\d{2})?$', c['text'])]
if not time_controls_all:
    print("\n找不到任何时间文本！兜底打印底部控件：")
    all_controls.sort(key=lambda x: x['top'], reverse=True)
    for c in all_controls[:15]:
        print(f"  top={c['top']:<6} left={c['left']:<8} '{c['text'][:40]}'")
    exit()

# 按垂直位置分组：同一行进度条top差值<10视为一组
time_groups = {}
for tc in time_controls_all:
    matched = False
    for group_top in list(time_groups.keys()):
        if abs(tc['top'] - group_top) < 10:
            time_groups[group_top].append(tc)
            matched = True
            break
    if not matched:
        time_groups[tc['top']] = [tc]

# 取最底部的一组（视频进度条，排除倍速1.5x等无关时间）
sorted_tops = sorted(time_groups.keys(), reverse=True)
progress_time_group = None
for t in sorted_tops:
    # 过滤掉只有单个时间的无关行（比如弹幕、历史记录）
    if len(time_groups[t]) >= 2:
        progress_time_group = time_groups[t]
        break

if not progress_time_group:
    print("未找到包含两个时间的进度条行！")
    exit()

# 按left从小到大排序：靠左=当前时间，靠右=总时长
progress_time_group.sort(key=lambda x: x['left'])
cur_text = progress_time_group[0]['text']
total_text = progress_time_group[1]['text']
progress_top = progress_time_group[0]['top']

print(f"✓ 进度条行top={progress_top}")
print(f"  当前时间: {cur_text}")
print(f"  总时长: {total_text}")

# 时间转秒函数
def time2sec(s):
    parts = s.split(":")
    if len(parts) == 2:
        # mm:ss
        m, sec = map(int, parts)
        return m * 60 + sec
    elif len(parts) == 3:
        # hh:mm:ss
        h, m, sec = map(int, parts)
        return h * 3600 + m * 60 + sec
    return 0

cur_sec = time2sec(cur_text)
total_sec = time2sec(total_text)
progress_rate = cur_sec / total_sec if total_sec > 0 else 0
print(f"  当前秒数: {cur_sec} | 总秒数: {total_sec} | 进度: {progress_rate:.1%}")

# 3. 找博主名（进度条上方，包含 @）
author = None
author_top = None
author_left = None
for c in sorted(all_controls, key=lambda x: x['top']):
    if c['top'] < progress_top - 300 or c['top'] > progress_top - 50:
        continue
    text = c['text']
    if text.startswith('@') or (len(text) < 50 and '@' in text):
        match = re.search(r'@\s*([^\s@·]+)', text)
        if match:
            author = match.group(1)
            author_top = c['top']
            author_left = c['left']
            print(f"\n✓ 博主: @{author} (top={c['top']}, left={c['left']})")
            break

if not author:
    print("未找到博主名")
    exit()

# 4. 在博主正下方找标题
left_range = (author_left - 50, author_left + 200)
top_range = (author_top + 20, progress_top - 80)

print(f"\n--- 搜索标题区域: top {top_range[0]}~{top_range[1]}, left {left_range[0]}~{left_range[1]} ---")

title_parts = []
for c in sorted(all_controls, key=lambda x: (x['top'], x['left'])):
    if not (top_range[0] <= c['top'] <= top_range[1]):
        continue
    if not (left_range[0] <= c['left'] <= left_range[1]):
        continue
    
    text = c['text']
    
    if re.match(r'^[\·\s]*\d+月\d+日[\s]*$', text):
        continue
    if text.startswith('#') and len(text) < 40:
        continue
    if text in ['展开', '收起', '点击推荐', '相关搜索', '：']:
        continue
    if any(kw in text for kw in ['要获取', '上下文菜单', '图片说明', '请打开', '下载抖音']):
        continue
    if re.match(r'^[\，\。\！\？\,\.\!\?\s]+$', text):
        continue
    
    title_parts.append(c)
    print(f"  + top={c['top']:<6} left={c['left']:<8} '{text[:60]}'")

# 5. 拼接标题
cleaned_title = "未识别"
if title_parts:
    sorted_parts = sorted(title_parts, key=lambda x: (x['top'], x['left']))
    rows = []
    current_row = []
    prev_top = None
    for part in sorted_parts:
        if prev_top is None or abs(part['top'] - prev_top) < 10:
            current_row.append(part)
        else:
            rows.append(current_row)
            current_row = [part]
        prev_top = part
    if current_row:
        rows.append(current_row)
    
    full_title = ""
    for row in rows:
        row.sort(key=lambda x: x['left'])
        row_text = "".join([p['text'] for p in row])
        if full_title and not full_title.rstrip().endswith(('。', '！', '？', ',', '，', ':', '：', ' ')):
            full_title += " "
        full_title += row_text
    cleaned_title = full_title.strip()

print(f"\n{'='*60}")
print(f"  最终识别结果")
print(f"{'='*60}")
print(f"  博主: @{author}")
print(f"  标题: {cleaned_title}")
print(f"  播放进度: {cur_text}/{total_text} ({progress_rate:.1%})")
print(f"{'='*60}")

# 6. 抓取听抖音坐标，计算点赞按钮
listen_left = None
listen_top = None
for c in all_controls:
    if c['text'] == "听抖音":
        listen_left = c['left']
        listen_top = c['top']
        break

if listen_left is not None and listen_top is not None:
    offset_x = 40
    offset_y = -340
    like_x = listen_left + offset_x
    like_y = listen_top + offset_y
    print(f"\n[点赞自动坐标] 听抖音({listen_left},{listen_top}) → 红心({like_x},{like_y})")

# 7. 打印右侧互动数据
print(f"\n--- 视频互动数据 (右侧区域) ---")
for c in sorted(all_controls, key=lambda x: x['left'], reverse=True):
    if c['left'] > -1000 and abs(c['top'] - author_top) < 300:
        text = c['text']
        if re.match(r'^[\d\.]+[万亿万]?$', text) or text.isdigit() or len(text) <= 8:
            print(f"  top={c['top']:<6} left={c['left']:<8} '{text}'")