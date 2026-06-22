import re
import time

import win32con
import win32gui
import win32ui
from PIL import Image

try:
    import uiautomation as auto
except ImportError:
    auto = None


class VideoTracker:
    def __init__(self, threshold=0.60, cooldown=3.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.liked_for_current = False
        self.last_known_total = None
        self.last_like_time = 0
        self.last_cur = None
        self.prev_progress = 0.0

    def check(self, cur, total, author, title):
        if cur is None or total is None or total <= 0:
            return False, None

        now = time.time()
        progress = cur / total

        # 新视频判断：总时长变化超过2秒，或进度回落
        is_new = False
        if self.last_known_total is not None:
            if abs(self.last_known_total - total) > 2:
                is_new = True
            elif self.prev_progress > 0.5 and progress < self.prev_progress - 0.15:
                is_new = True

        if self.last_known_total is None or is_new:
            self.last_known_total = total
            self.liked_for_current = False
            self.last_cur = None
            self.prev_progress = 0.0
            return ("new_video", f"@{author} {title} 总时长: {total//60}:{total%60:02d}")

        self.prev_progress = progress

        # 点赞判断
        if (not self.liked_for_current) and progress >= self.threshold and (now - self.last_like_time) > self.cooldown:
            self.liked_for_current = True
            self.last_like_time = now
            return (True, progress)

        return (False, progress)

    def mark_liked(self):
        self.liked_for_current = True


class LikeEngine:
    def __init__(self, on_log=None, on_state_update=None, threshold=0.60, cooldown=3.0):
        self.hwnd = None
        self.ctrl = None
        self.running = False
        self.paused = False
        self.on_log = on_log or (lambda msg: None)
        self.on_state_update = on_state_update or (lambda **kw: None)

        self.current_author = ""
        self.current_title = ""
        self.cur_sec = 0
        self.total_sec = 0
        self.progress = 0.0
        self.like_count = 0
        self.watch_count = 0
        self.like_x = None
        self.like_y = None

        self.tracker = VideoTracker(threshold=threshold, cooldown=cooldown)

    def log(self, msg):
        self.on_log(msg)

    def find_window(self, keyword="抖音", class_name="Chrome_WidgetWin_1"):
        if auto is not None:
            try:
                dy_pane = auto.PaneControl(searchDepth=1, ClassName=class_name, Name=keyword)
                if dy_pane.Exists(0):
                    self.hwnd = dy_pane.NativeWindowHandle
                    self.ctrl = dy_pane
                    if self.hwnd:
                        self.log(f"找到抖音窗口: {win32gui.GetWindowText(self.hwnd)}")
                        return True
            except Exception:
                pass

            try:
                desktop = auto.GetRootControl()
                for item in desktop.GetChildren():
                    name = item.Name or ""
                    if keyword in name:
                        try:
                            rect = item.BoundingRectangle
                            if rect and rect.width() > 200 and rect.height() > 200:
                                self.hwnd = item.NativeWindowHandle
                                self.ctrl = item
                                if self.hwnd:
                                    self.log(f"找到抖音窗口: {name}")
                                    return True
                        except Exception:
                            continue
            except Exception:
                pass

        self.hwnd = self._find_win32(keyword)
        self.ctrl = None
        if self.hwnd:
            self.log(f"Win32 找到抖音窗口: {win32gui.GetWindowText(self.hwnd)}")
            return True

        self.log("未找到抖音窗口，请先打开抖音")
        return False

    def _find_win32(self, keyword="抖音"):
        hwnds = []

        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
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

    def _collect_controls(self):
        if auto is None or self.ctrl is None:
            return []
        all_controls = []
        try:
            if not self.ctrl.Exists(0):
                return []
        except Exception:
            return []

        try:
            for control, depth in auto.WalkControl(self.ctrl):
                name = control.Name or ""
                name_stripped = name.strip()
                if not name_stripped:
                    continue
                try:
                    rect = control.BoundingRectangle
                    top = rect.top
                    left = rect.left
                    if top == 0 and left == 0 and rect.right() == 0 and rect.bottom() == 0:
                        continue
                except Exception:
                    continue
                all_controls.append(
    {
        "text": name_stripped,
        "top": top,
        "left": left,
        "width": rect.width(),
        "height": rect.height(),
        "depth": depth
    }
)
        except Exception:
            return []
        return all_controls

    def get_time(self):
        controls = self._collect_controls()
        if not controls:
            return None, None

        time_controls = [c for c in controls if re.match(r"^\d{1,2}:\d{1,2}(:\d{2})?$", c["text"])]
        if not time_controls:
            return None, None

        time_groups = {}
        for tc in time_controls:
            matched = False
            for group_top in list(time_groups.keys()):
                if abs(tc["top"] - group_top) < 10:
                    time_groups[group_top].append(tc)
                    matched = True
                    break
            if not matched:
                time_groups[tc["top"]] = [tc]

        sorted_tops = sorted(time_groups.keys(), reverse=True)
        progress_group = None
        for t in sorted_tops:
            if len(time_groups[t]) >= 2:
                progress_group = time_groups[t]
                break

        if not progress_group:
            return None, None

        progress_group.sort(key=lambda x: x["left"])
        cur_text = progress_group[0]["text"]
        total_text = progress_group[1]["text"]
        return self._parse_time(cur_text), self._parse_time(total_text)

    def _parse_time(self, time_str):
        if not time_str:
            return None
        parts = time_str.strip().split(":")
        if len(parts) == 2:
            try:
                m, sec = map(int, parts)
                return m * 60 + sec
            except (ValueError, TypeError):
                return None
        elif len(parts) == 3:
            try:
                h, m, sec = map(int, parts)
                return h * 3600 + m * 60 + sec
            except (ValueError, TypeError):
                return None
        return None

    def get_video_info(self):
        controls = self._collect_controls()
        if not controls:
            return None, None, (None, None)

        time_controls = [c for c in controls if re.match(r"^\d{1,2}:\d{1,2}(:\d{2})?$", c["text"])]
        if not time_controls:
            return None, None, (None, None)

        time_groups = {}
        for tc in time_controls:
            matched = False
            for group_top in list(time_groups.keys()):
                if abs(tc["top"] - group_top) < 10:
                    time_groups[group_top].append(tc)
                    matched = True
                    break
            if not matched:
                time_groups[tc["top"]] = [tc]

        sorted_tops = sorted(time_groups.keys(), reverse=True)
        progress_top = None
        for t in sorted_tops:
            if len(time_groups[t]) >= 2:
                progress_top = t
                break

        if progress_top is None:
            return None, None, (None, None)

        author = None
        author_top = None
        author_left = None
        for c in sorted(controls, key=lambda x: x["top"]):
            if not (progress_top - 300 < c["top"] < progress_top - 50):
                continue
            text = c["text"]
            if text.startswith("@") or (len(text) < 50 and "@" in text):
                match = re.search(r"@\s*([^\s@·]+)", text)
                if match:
                    author = match.group(1)
                    author_top = c["top"]
                    author_left = c["left"]
                    break

        if not author:
            return None, None, (None, None)

        left_range = (author_left - 50, author_left + 200)
        top_range = (author_top + 20, progress_top - 80)

        title_parts = []
        for c in sorted(controls, key=lambda x: (x["top"], x["left"])):
            if not (top_range[0] <= c["top"] <= top_range[1]):
                continue
            if not (left_range[0] <= c["left"] <= left_range[1]):
                continue
            text = c["text"]
            if text.startswith("@"):
                continue
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
            if len(text) <= 1:
                continue
            title_parts.append(c)

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
                if full_title and not full_title.rstrip().endswith(
                    ("。", "！", "？", ",", "，", ":", "：", " ")
                ):
                    full_title += " "
                full_title += row_text
            full_title = full_title.strip()

        if not full_title:
            for c in sorted(controls, key=lambda x: (x["top"], x["left"])):
                if not (progress_top - 200 < c["top"] < progress_top - 60):
                    continue
                if not (-2000 < c["left"] < -1500):
                    continue
                text = c["text"]
                if text.startswith("@"):
                    continue
                if len(text) > 5 and len(text) < 200:
                    full_title = text
                    break

        # 根据"听抖音"计算点赞坐标
        like_x, like_y = None, None
        for item in controls:
            if item["text"] == "听抖音":
                listen_cx = item["left"] + item["width"] / 2
                listen_cy = item["top"] + item["height"] / 2
                scale_y = 15  
                like_x = listen_cx
                like_y = listen_cy - scale_y * item["height"]
                break

        return f"@{author}", full_title if full_title else "无标题", (like_x, like_y)

    def _screen_to_client(self, screen_x, screen_y):
        win_left, win_top, _, _ = win32gui.GetWindowRect(self.hwnd)
        cx = int(screen_x - win_left)
        cy = int(screen_y - win_top)
        return cx, cy

    def _capture_region(self, x, y, size=30):
        """x, y 是屏幕坐标，内部自动转成窗口坐标后截图"""
        import os
        import time
        if self.hwnd is None:
            return None
        cx, cy = self._screen_to_client(x, y)
        half_size = size // 2
        left = max(0, cx - half_size)
        top = max(0, cy - half_size)
        right = left + size
        bottom = top + size
        try:
            wDC = win32gui.GetDC(self.hwnd)
            dcObj = win32ui.CreateDCFromHandle(wDC)
            cDC = dcObj.CreateCompatibleDC()
            dataBitMap = win32ui.CreateBitmap()
            dataBitMap.CreateCompatibleBitmap(dcObj, size, size)
            cDC.SelectObject(dataBitMap)
            cDC.BitBlt((0, 0), (size, size), dcObj, (left, top), win32con.SRCCOPY)

            bmpinfo = dataBitMap.GetInfo()
            bmpstr = dataBitMap.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGB",
                (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                bmpstr,
                "raw",
                "BGRX",
                0,
                1,
            )

            dcObj.DeleteDC()
            cDC.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, wDC)
            win32gui.DeleteObject(dataBitMap.GetHandle())
                        # 保存调试截图
            try:
                save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_shots")
                os.makedirs(save_dir, exist_ok=True)
                ts = time.strftime("%H%M%S")
                filepath = os.path.join(save_dir, f"like_debug_{ts}_{int(x)}_{int(y)}.png")
                img.save(filepath)
                self.log(f"[截图] 已保存 {os.path.basename(filepath)} "
                         f"(窗口坐标 {cx},{cy}, 截图区域 {left},{top}~{right},{bottom})")
            except Exception as e:
                self.log(f"[截图保存失败] {e}")
            return img
        except Exception:
            return None

    def is_already_liked(self, screen_x, screen_y):
        """检测点赞按钮是否已经被点亮（红色）
        screen_x, screen_y 是屏幕坐标
        """
        if self.hwnd is None:
            return False
        img = self._capture_region(screen_x,screen_y, size=30)
        if img is None:
            return False
        width, height = img.size
        if width < 5 or height < 5:
            return False

        center_x, center_y = width // 2, height // 2
        r_sum, g_sum, b_sum = 0, 0, 0
        count = 0
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
        return r_avg > g_avg + 50 and r_avg > b_avg + 50

    def click(self, screen_x, screen_y):
        """后台点击：屏幕坐标 → 窗口客户区坐标 → PostMessage"""
        if self.hwnd is None:
            return False
        try:
            cx, cy = self._screen_to_client(screen_x, screen_y)
            lparam = (cy & 0xFFFF) << 16 | (cx & 0xFFFF)
            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            time.sleep(0.06)
            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            return True
        except Exception as e:
            self.log(f"点击异常: {e}")
            return False

    def tick_once(self):
        """一次检查循环：获取时间 → 判断是否要点赞 → 执行点赞"""
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            self.log("抖音窗口已关闭，尝试重新查找...")
            self.find_window()
            return False

        cur, total = self.get_time()

        # 每次都获取视频信息 + 刷新点赞坐标
        if self.ctrl is not None:
            author, title, lp = self.get_video_info()
            if author:
                self.current_author = author
                self.current_title = title if title else "无标题"
            if lp and lp[0] is not None:
                self.like_x, self.like_y = lp[0], lp[1]

        if cur is not None and total is not None and total > 0:
            self.cur_sec = cur
            self.total_sec = total
            self.progress = cur / total

        # VideoTracker 判断
        result = self.tracker.check(
            cur, total,
            self.current_author or "未知博主",
            self.current_title or "无标题",
        )

        if result[0] == "new_video":
            self.watch_count += 1
            self.log(f"新视频: {result[1]}")
        elif result[0] is True or result[0] == True:
            pct = int(result[1] * 100) if result[1] else 0
            if self.like_x is not None and self.like_y is not None:
                already_liked = self.is_already_liked(self.like_x, self.like_y)
                if already_liked:
                    self.log(f"检测到已点赞，跳过: 【{self.current_author}】{self.current_title} ({pct}%)")
                    self.tracker.mark_liked()
                else:
                    self.log(f"触发点赞: 【{self.current_author}】{self.current_title} ({pct}%)")
                    self.click(self.like_x, self.like_y)
                    self.like_count += 1
            else:
                self.log(f"无点赞坐标，跳过: 【{self.current_author}】{self.current_title}")

        return True
