import json
import os
import re
import sys
import time

import win32con
import win32gui
import win32ui
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import uiautomation as auto
except ImportError:
    auto = None

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "window_title_keyword": "抖音",
    "window_class": "Chrome_WidgetWin_1",
    "time_region": {"left": 0, "top": 0, "right": 150, "bottom": 40},
    "like_button": {"x": 0, "y": 0},
    "auto_like_threshold": 0.60,
    "check_interval": 0.5,
    "new_video_cooldown": 3.0,
    "tesseract_cmd": "",
    "use_uiautomation": True,
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(data)
        return cfg
    except Exception as e:
        print(f"[警告] 读取配置文件失败，使用默认配置: {e}")
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def find_douyin_window_uia(keyword="抖音", class_name="Chrome_WidgetWin_1"):
    """使用 uiautomation 精确锁定抖音窗口控件"""
    if auto is None:
        return None, None

    try:
        dy_pane = auto.PaneControl(searchDepth=1, ClassName=class_name, Name=keyword)
        if not dy_pane.Exists(0):
            return None, None
        hwnd = dy_pane.NativeWindowHandle
        if hwnd:
            print(f"[UIA] 精确锁定抖音窗口成功! hwnd={hwnd}")
            return hwnd, dy_pane
    except Exception:
        pass

    desktop = auto.GetRootControl()
    candidates = []

    for item in desktop.GetChildren():
        item_name = item.Name or ""
        item_class = item.ClassName or ""

        if keyword in item_name or "Douyin" in item_name:
            candidates.append((item, item_name, item_class, "name_match"))
        if class_name and class_name in item_class:
            candidates.append((item, item_name, item_class, "class_match"))

    if not candidates:
        return None, None

    for ctrl, name, cls, match_type in candidates:
        try:
            rect = ctrl.BoundingRectangle
            if rect and rect.width() > 200 and rect.height() > 200:
                hwnd = ctrl.NativeWindowHandle
                if hwnd:
                    print(f"[UIA] 找到窗口: '{name}' | 类: {cls} | 匹配: {match_type}")
                    return hwnd, ctrl
        except Exception:
            continue

    return None, None


def find_douyin_window_win32(keyword="抖音"):
    """使用 win32gui 查找抖音窗口（备用方案）"""
    hwnds = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if keyword in title:
            hwnds.append(hwnd)

    win32gui.EnumWindows(callback, None)
    if not hwnds:
        return None
    hwnds.sort(
        key=lambda h: (win32gui.GetWindowRect(h)[2] - win32gui.GetWindowRect(h)[0])
                      * (win32gui.GetWindowRect(h)[3] - win32gui.GetWindowRect(h)[1]),
        reverse=True,
    )
    return hwnds[0]


def find_douyin_window(config):
    """综合查找抖音窗口"""
    hwnd = None
    ctrl = None

    if config.get("use_uiautomation", True) and auto is not None:
        hwnd, ctrl = find_douyin_window_uia(
            config.get("window_title_keyword", "抖音"),
            config.get("window_class", "Chrome_WidgetWin_1"),
        )

    if hwnd is None:
        hwnd = find_douyin_window_win32(config.get("window_title_keyword", "抖音"))
        if hwnd:
            print(f"[Win32] 找到窗口: '{win32gui.GetWindowText(hwnd)}'")

    return hwnd, ctrl


def get_time_from_uia_ctrl(dy_pane):
    """从抖音 UI 控件提取当前播放时间和总时长
    同步探针逻辑：提取同进度条行全部时间控件，区分当前/总时长
    """
    if auto is None:
        return None, None
    try:
        if not dy_pane.Exists(0):
            return None, None
    except Exception:
        return None, None

    # 1. 收集所有有真实坐标的文本控件
    all_controls = []
    try:
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
                "text": name_stripped,
                "top": top,
                "left": left,
                "depth": depth,
                "type": control.ControlTypeName or ""
            })
    except Exception:
        return None, None

    if not all_controls:
        pass  # 未找到任何控件
        return None, None

    # 2. 筛选所有时间格式控件 xx:xx
    time_controls_all = [c for c in all_controls if re.match(r"^\d{1,2}:\d{2}$", c["text"])]
    if not time_controls_all:
        pass  # 找不到任何时间文本
        return None, None

    # 3. 按垂直位置分组：同一行进度条 top 差值 < 10 视为一组
    time_groups = {}
    for tc in time_controls_all:
        matched = False
        for group_top in list(time_groups.keys()):
            if abs(tc["top"] - group_top) < 10:
                time_groups[group_top].append(tc)
                matched = True
                break
        if not matched:
            time_groups[tc["top"]] = [tc]

    # 4. 取最底部的一组（视频进度条，排除倍速1.5x等无关时间）
    sorted_tops = sorted(time_groups.keys(), reverse=True)
    progress_time_group = None
    for t in sorted_tops:
        if len(time_groups[t]) >= 2:
            progress_time_group = time_groups[t]
            pass  # 进度条行 top=...
            break

    if not progress_time_group:
        pass  # 未找到包含两个时间的进度条行
        return None, None

    # 5. 按 left 从小到大排序：靠左 = 当前时间，靠右 = 总时长
    progress_time_group.sort(key=lambda x: x["left"])
    cur_text = progress_time_group[0]["text"]
    total_text = progress_time_group[1]["text"]
    progress_top = progress_time_group[0]["top"]

    cur_sec = parse_seconds(cur_text)
    total_sec = parse_seconds(total_text)

    if cur_sec is None or total_sec is None:
        return None, None

    pass  # 时间识别: {cur_text}/{total_text}
    return cur_sec, total_sec


def get_video_info(dy_pane):
    """从抖音 UI 控件获取当前视频的博主和标题
    同步探针逻辑：自动抓取「听抖音」坐标，动态计算点赞按钮坐标
    返回: (author, title, like_button_pos) 或 (None, None, None)
    """
    if auto is None:
        return None, None, None

    try:
        if not dy_pane.Exists(0):
            return None, None, None
    except Exception:
        return None, None, None

    # 1. 收集所有有真实坐标的文本控件
    all_controls = []
    try:
        for control, depth in auto.WalkControl(dy_pane):
            name = control.Name or ""
            name_stripped = name.strip()
            if not name_stripped:
                continue

            rect = control.BoundingRectangle
            top = rect.top
            left = rect.left
            if top == 0 and left == 0 and rect.right == 0 and rect.bottom == 0:
                continue

            all_controls.append({
                "text": name_stripped,
                "top": top,
                "left": left,
                "depth": depth,
                "type": control.ControlTypeName or ""
            })
    except Exception:
        return None, None, None

    if not all_controls:
        pass  # get_video_info: 未找到任何控件
        return None, None, None

    # 2. 筛选时间控件，找进度条
    time_controls_all = [c for c in all_controls if re.match(r"^\d{1,2}:\d{2}$", c["text"])]
    if not time_controls_all:
        pass  # get_video_info: 找不到时间控件
        return None, None, None

    # 按 top 分组
    time_groups = {}
    for tc in time_controls_all:
        matched = False
        for group_top in list(time_groups.keys()):
            if abs(tc["top"] - group_top) < 10:
                time_groups[group_top].append(tc)
                matched = True
                break
        if not matched:
            time_groups[tc["top"]] = [tc]

    # 取最下方包含至少2个时间的组
    sorted_tops = sorted(time_groups.keys(), reverse=True)
    progress_top = None
    for t in sorted_tops:
        if len(time_groups[t]) >= 2:
            progress_top = t
            break

    if progress_top is None:
        pass  # get_video_info: 未找到进度条
        return None, None, None

    # 3. 找博主名（进度条上方 300~50 像素）
    author = None
    author_top = None
    author_left = None
    for c in sorted(all_controls, key=lambda x: x["top"]):
        if not (progress_top - 300 < c["top"] < progress_top - 50):
            continue
        text = c["text"]
        if text.startswith("@") or (len(text) < 50 and "@" in text):
            match = re.search(r"@\s*([^\s@·]+)", text)
            if match:
                author = match.group(1)
                author_top = c["top"]
                author_left = c["left"]
                pass  # 博主: @{author}
                break

    if not author:
        pass  # get_video_info: 未找到博主
        return None, None, None

    # 4. 在博主正下方找标题
    left_range = (author_left - 50, author_left + 200)
    top_range = (author_top + 20, progress_top - 80)

    pass  # 标题搜索区域: top...

    title_parts = []
    for c in sorted(all_controls, key=lambda x: (x["top"], x["left"])):
        if not (top_range[0] <= c["top"] <= top_range[1]):
            continue
        if not (left_range[0] <= c["left"] <= left_range[1]):
            continue

        text = c["text"]

        # 过滤噪音
        if re.match(r"^[\·\s]*\d+月\d+日[\s]*$", text):
            continue
        if text.startswith("#") and len(text) < 40:
            continue
        if text in ["展开", "收起", "点击推荐", "相关搜索", "："]:
            continue
        if any(kw in text for kw in ["要获取", "上下文菜单", "图片说明", "请打开", "下载抖音"]):
            continue
        if re.match(r"^[\，\。\！\？\,\.\!\?\s]+$", text):
            continue

        title_parts.append(c)
        pass  # 标题片段: top=...

    full_title = ""
    if title_parts:
        sorted_parts = sorted(title_parts, key=lambda x: (x["top"], x["left"]))
        rows = []
        current_row = []
        prev_top = None
        for part in sorted_parts:
            if prev_top is None or abs(part["top"] - prev_top) < 10:
                current_row.append(part)
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [part]
            prev_top = part["top"]
        if current_row:
            rows.append(current_row)

        for row in rows:
            row.sort(key=lambda x: x["left"])
            row_text = "".join([p["text"] for p in row])
            if full_title and not full_title.rstrip().endswith(("。", "！", "？", ",", "，", ":", "：", " ")):
                full_title += " "
            full_title += row_text
        full_title = full_title.strip()

    pass  # 最终标题: {full_title}

    # 5. 抓取「听抖音」坐标，计算点赞按钮位置
    like_x, like_y = None, None
    for item in all_controls:
        if item["text"] == "听抖音":
            listen_left = item["left"]
            listen_top = item["top"]
            offset_x = 40
            offset_y = -340
            like_x = listen_left + offset_x
            like_y = listen_top + offset_y
            pass  # 听抖音 → 点赞
            break

    return f"@{author}", full_title if full_title else None, (like_x, like_y)


def parse_seconds(time_str):
    """解析 MM:SS 或 H:MM:SS 格式的时间字符串"""
    if not time_str:
        return None
    parts = time_str.strip().split(":")
    if len(parts) == 2:
        m, s = int(parts[0]), int(parts[1])
        return m * 60 + s
    elif len(parts) == 3:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        return h * 3600 + m * 60 + s
    return None


def capture_button_region(hwnd, x, y, size=30):
    """截取点赞按钮周围区域的截图"""
    half_size = size // 2
    left = max(0, x - half_size)
    top = max(0, y - half_size)
    right = left + size
    bottom = top + size

    try:
        wDC = win32gui.GetWindowDC(hwnd)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        cDC = dcObj.CreateCompatibleDC()
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, size, size)
        cDC.SelectObject(dataBitMap)
        cDC.BitBlt((0, 0), (size, size), dcObj, (left, top), win32con.SRCCOPY)

        bmpinfo = dataBitMap.GetInfo()
        bmpstr = dataBitMap.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)

        dcObj.DeleteDC()
        cDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, wDC)
        win32gui.DeleteObject(dataBitMap.GetHandle())
        return img
    except Exception:
        return None


def is_already_liked(hwnd, x, y):
    """检测点赞按钮是否已经被点亮（红色）
    通过检测按钮中心区域的颜色判断：
    - 红色分量 > 蓝色分量 且 红色分量 > 绿色分量 → 已点赞（红心）
    - 否则 → 未点赞（白心）
    """
    img = capture_button_region(hwnd, x, y, size=30)
    if img is None:
        pass  # is_already_liked: 截图失败
        return False

    width, height = img.size
    if width < 5 or height < 5:
        pass  # is_already_liked: 图片太小
        return False

    center_x, center_y = width // 2, height // 2

    r_sum, g_sum, b_sum = 0, 0, 0
    count = 0

    # 检测中心 5x5 区域的颜色
    for dx in [-2, -1, 0, 1, 2]:
        for dy in [-2, -1, 0, 1, 2]:
            cx = center_x + dx
            cy = center_y + dy
            if 0 <= cx < width and 0 <= cy < height:
                r, g, b = img.getpixel((cx, cy))
                r_sum += r
                g_sum += g
                b_sum += b
                count += 1

    if count == 0:
        return False

    r_avg = r_sum / count
    g_avg = g_sum / count
    b_avg = b_sum / count

    # 红色判断：r > g + 50 且 r > b + 50
    is_liked = r_avg > g_avg + 50 and r_avg > b_avg + 50
    pass  # is_already_liked: R=... G=... B=...
    return is_liked


def capture_window_region(hwnd, region):
    left, top, right, bottom = region["left"], region["top"], region["right"], region["bottom"]
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None

    try:
        wDC = win32gui.GetWindowDC(hwnd)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        cDC = dcObj.CreateCompatibleDC()
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, width, height)
        cDC.SelectObject(dataBitMap)
        cDC.BitBlt((0, 0), (width, height), dcObj, (left, top), win32con.SRCCOPY)

        bmpinfo = dataBitMap.GetInfo()
        bmpstr = dataBitMap.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)

        dcObj.DeleteDC()
        cDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, wDC)
        win32gui.DeleteObject(dataBitMap.GetHandle())
        return img
    except Exception as e:
        return None


def ocr_time_text(img, tesseract_cmd=""):
    if pytesseract is None:
        return None
    # 优先使用配置传入的路径，强制覆盖
    if tesseract_cmd and os.path.exists(tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    try:
        gray = img.convert("L")
        w, h = gray.size
        scale = 3 if w < 200 else 2
        gray = gray.resize((w * scale, h * scale), Image.LANCZOS)
        text = pytesseract.image_to_string(
            gray, config="--psm 7 -c tessedit_char_whitelist=0123456789:/"
        )
        return text.strip()
    except pytesseract.TesseractNotFoundError:
        return "NOT_FOUND"
    except Exception:
        return None


def parse_time(text):
    if not text:
        return None, None
    pattern = re.search(r"(\d{1,2}):(\d{2})\s*/\s*(\d{1,2}):(\d{2})", text)
    if pattern:
        cur_m, cur_s, total_m, total_s = pattern.groups()
        cur = int(cur_m) * 60 + int(cur_s)
        total = int(total_m) * 60 + int(total_s)
        if total > 0 and cur <= total + 1:
            return cur, total
    pattern2 = re.search(r"(\d{1,2}):(\d{2})", text)
    if pattern2:
        m, s = pattern2.groups()
        return int(m) * 60 + int(s), None
    return None, None


def screen_to_client(hwnd, screen_x, screen_y):
    win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)
    cx = int(screen_x - win_left)
    cy = int(screen_y - win_top)
    return cx, cy

def silent_background_click(hwnd, screen_x, screen_y):
    try:
        cx, cy = screen_to_client(hwnd, screen_x, screen_y)
        print(f"[点击调试] 屏幕坐标({screen_x},{screen_y}) → 窗口内坐标({cx},{cy})")
        lparam = (cy & 0xFFFF) << 16 | (cx & 0xFFFF)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(0.06)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
        return True
    except Exception as e:
        print(f"[点击异常] {e}")
        return False


class VideoTracker:
    def __init__(self, threshold=0.60, cooldown=3.0):
        self.threshold = threshold
        self.cooldown = cooldown

        self.liked_total_for_video = None
        self.last_known_total = None
        self.last_like_time = time.time() - cooldown

        self.highest_progress = 0.0
        self.last_cur = None
        self.stable_count = 0

    def check(self, cur, total):
        now = time.time()

        if total is not None and total > 0:
            if self.last_known_total is None:
                self.last_known_total = total
            elif abs(self.last_known_total - total) > 2:
                self.last_known_total = total
                self.liked_total_for_video = None
                self.highest_progress = 0.0
                self.last_cur = None
                self.stable_count = 0
                print(f"\n[新视频] 总时长: {total // 60}:{total % 60:02d}")

        if cur is not None and total is not None and total > 0:
            progress = cur / total

            if cur == self.last_cur:
                self.stable_count += 1
            else:
                self.stable_count = 0
            self.last_cur = cur

            if progress > self.highest_progress:
                self.highest_progress = progress

            if (
                    self.liked_total_for_video != total
                    and progress >= self.threshold
                    and (now - self.last_like_time) > self.cooldown
            ):
                self.liked_total_for_video = total
                self.last_like_time = now
                return True, progress

        return False, (cur / total if (cur is not None and total is not None and total > 0) else None)

    def mark_liked(self):
        """标记当前视频已点赞"""
        self.last_like_time = time.time()


def main():
    global config
    print("=" * 60)
    print("  抖音自动点赞工具 v4 - 修复双时间+自动锚定听抖音点赞坐标")
    print("=" * 60)

    config = load_config()
    print(f"\n[配置] 窗口关键词: {config['window_title_keyword']}")
    print(f"[配置] 窗口类名: {config.get('window_class', 'Chrome_WidgetWin_1')}")
    print(f"[配置] 自动点赞阈值: {int(config['auto_like_threshold'] * 100)}%")
    print(f"[配置] 检查间隔: {config['check_interval']} 秒")
    print(f"[配置] 新视频冷却: {config['new_video_cooldown']} 秒")
    print(f"[配置] 使用 uiautomation: {config.get('use_uiautomation', True)}")

    if auto is None:
        print("\n[警告] uiautomation 未安装，将使用 win32gui 查找窗口")
        print("        建议: pip install uiautomation")

    hwnd, ctrl = find_douyin_window(config)
    if hwnd is None:
        print(f"\n[错误] 未找到抖音窗口。")
        print("        请先打开抖音桌面版。")
        input("\n按回车键退出...")
        return

    title = win32gui.GetWindowText(hwnd)
    rect = win32gui.GetWindowRect(hwnd)
    print(f"\n[成功] 窗口句柄: {hwnd}")
    print(f"        窗口标题: {title}")
    print(f"        窗口矩形: {rect}")
    print(f"        时间识别区域(相对窗口): {config['time_region']}")
    print(f"        动态点赞坐标(随听抖音更新): {config['like_button']}")

    if config["time_region"]["right"] <= 0:
        print("\n[警告] 时间识别区域未配置！")
        print("        请先运行 config_helper.py 框选时间区域。")
        input("按回车键退出...")
        return

    print("\n" + "=" * 60)
    print("  开始监控（按 Ctrl+C 退出）")
    print("=" * 60 + "\n")

    tracker = VideoTracker(
        threshold=config["auto_like_threshold"],
        cooldown=config["new_video_cooldown"],
    )
    like_count = 0
    ocr_fail_count = 0
    last_display_time = 0
    last_uia_log_time = 0
    last_video_info_time = 0
    last_total = None
    current_author = None
    current_title = None

    # 创建日志文件
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, "like_log.txt")
    log_fp = open(log_file, "a", encoding="utf-8")
    log_fp.write(f"\n{'='*60}\n")
    log_fp.write(f"抖音自动点赞日志 - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_fp.write(f"{'='*60}\n")
    log_fp.flush()

    try:
        while True:
            loop_start = time.time()
            time.sleep(0.1)

            if not win32gui.IsWindow(hwnd):
                print("\n[警告] 抖音窗口已关闭，尝试重新查找...")
                hwnd, ctrl = find_douyin_window(config)
                if hwnd:
                    print(f"[恢复] 重新找到窗口: {win32gui.GetWindowText(hwnd)}")
                else:
                    print("[错误] 无法找到抖音窗口，5秒后重试...")
                    time.sleep(5)
                    continue

            cur, total = None, None
            now = time.time()

            if ctrl is not None and config.get("use_uiautomation", True):
                cur, total = get_time_from_uia_ctrl(ctrl)

                # 每 3 秒获取一次视频信息（同步更新点赞坐标）
                if now - last_video_info_time > 3.0:
                    last_video_info_time = now
                    if total != last_total:
                        # 新视频，重新获取博主、标题、刷新点赞坐标
                        author, title, like_pos = get_video_info(ctrl)
                        if author:
                            current_author = author
                            current_title = title
                            last_total = total
                        # 更新点赞坐标（静默更新，不打印）
                        if like_pos and like_pos[0] is not None:
                            config["like_button"]["x"] = like_pos[0]
                            config["like_button"]["y"] = like_pos[1]

                if cur is not None and total is not None:
                    if now - last_uia_log_time > 5.0:
                        last_uia_log_time = now
                        author_info = f" | {current_author}" if current_author else ""
                        print(f"\r[UIA] {cur//60}:{cur%60:02d}/{total//60}:{total%60:02d}{author_info}", end="")

            if cur is None or total is None:
                img = capture_window_region(hwnd, config["time_region"])
                if img is None:
                    ocr_fail_count += 1
                    if ocr_fail_count > 10:
                        print("\n[警告] 连续截图失败，请检查窗口状态")
                        ocr_fail_count = 0
                    continue

                text = ocr_time_text(img, config.get("tesseract_cmd", ""))
                if text == "NOT_FOUND":
                    print("\n[错误] Tesseract 未安装或路径配置错误")
                    input("按回车键退出...")
                    return

                if text:
                    cur, total = parse_time(text)
                    ocr_fail_count = 0
                else:
                    ocr_fail_count += 1

            if cur is not None or total is not None:
                should_like, progress = tracker.check(cur, total)

                cur_str = f"{cur // 60}:{cur % 60:02d}" if cur is not None else "?"
                total_str = f"{total // 60}:{total % 60:02d}" if total is not None else "?"
                pct = int(progress * 100) if progress is not None else -1

                now = time.time()
                if now - last_display_time >= 0.5 or should_like:
                    last_display_time = now

                    # 构建多行状态（固定位置刷新）
                    author_str = current_author if current_author else "未知博主"
                    title_str = current_title if current_title else "未知标题"
                    status_str = "已点赞" if tracker.liked_total_for_video else "未点赞"
                    
                    # 使用 ANSI 转义序列清屏并写入新内容
                    # \033[6F 移动到第6行开头，\033[J 清屏到末尾
                    # 由于不确定终端行数，改用 \r 和 \033[K 清空当前行
                    clear_and_write = "\r\033[K"
                    
                    # 分多行写入，每行独立清空
                    sys.stdout.write(f"\r\033[K博主: {author_str}\n")
                    sys.stdout.write(f"\r\033[K标题: {title_str}\n")
                    sys.stdout.write(f"\r\033[K状态: {status_str}\n")
                    sys.stdout.write(f"\r\033[K时间: {cur_str}/{total_str} 进度: {pct:3d}%\n")
                    # 光标上移5行回到第一行开头
                    sys.stdout.write(f"\033[4A\r")
                    sys.stdout.flush()

                    if should_like:
                        x, y = config["like_button"]["x"], config["like_button"]["y"]
                        already_liked = is_already_liked(hwnd, x, y)
                        if already_liked:
                            # 写入日志：检测到已点赞（可能误判）
                            log_time = time.strftime("%Y-%m-%d %H:%M:%S")
                            log_fp.write(f"[{log_time}] [警告] 检测到已点赞，跳过: 【{current_author}】{current_title} (进度 {pct}%)\n")
                            log_fp.flush()
                            tracker.mark_liked()
                        else:
                            # 光标下移到底部行
                            sys.stdout.write(f"\r\033[B" * 5)
                            sys.stdout.write(f"\r\033[K  → 触发点赞! (坐标: {x}, {y})\n")
                            sys.stdout.flush()
                            silent_background_click(hwnd, x, y)

                            like_count += 1

                            # 写入日志文件
                            log_time = time.strftime("%Y-%m-%d %H:%M:%S")
                            log_entry = f"[{log_time}] [成功] "
                            if current_title:
                                log_entry += f"【{current_author}】{current_title}"
                            elif current_author:
                                log_entry += f"【{current_author}】未知标题"
                            else:
                                log_entry += f"未识别视频"
                            log_entry += f" (进度 {pct}%)\n"
                            log_fp.write(log_entry)
                            log_fp.flush()

            elapsed = time.time() - loop_start
            remaining = config["check_interval"] - elapsed
            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:
        print(f"\n\n[退出] 本次运行共点赞 {like_count} 个视频")
        print(f"        日志已保存到: {log_file}")
        log_fp.close()
        print("        按回车键关闭窗口...")
        input()


if __name__ == "__main__":
    main()