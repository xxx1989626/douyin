import json
import os
import time

import win32con
import win32gui
import win32ui
from PIL import Image, ImageTk

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def list_windows():
    results = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or len(title.strip()) == 0:
            return
        rect = win32gui.GetWindowRect(hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        if w < 200 or h < 200:
            return
        results.append((hwnd, title, rect, w * h))

    win32gui.EnumWindows(callback, None)
    results.sort(key=lambda x: x[3], reverse=True)
    return results


def capture_full_window(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]
    if w <= 0 or h <= 0:
        return None

    wDC = win32gui.GetWindowDC(hwnd)
    dcObj = win32ui.CreateDCFromHandle(wDC)
    cDC = dcObj.CreateCompatibleDC()
    dataBitMap = win32ui.CreateBitmap()
    dataBitMap.CreateCompatibleBitmap(dcObj, w, h)
    cDC.SelectObject(dataBitMap)
    cDC.BitBlt((0, 0), (w, h), dcObj, (0, 0), win32con.SRCCOPY)

    bmpinfo = dataBitMap.GetInfo()
    bmpstr = dataBitMap.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)

    dcObj.DeleteDC()
    cDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, wDC)
    win32gui.DeleteObject(dataBitMap.GetHandle())
    return img


def main():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("[错误] 无法导入 tkinter。请使用带 tkinter 支持的 Python 版本。")
        return

    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    root = tk.Tk()
    root.title("抖音自动点赞 - 配置助手")
    root.geometry("500x500")

    step = tk.IntVar(value=1)
    selected_hwnd = {"value": None}
    time_region = {"value": None}
    full_img_ref = {"value": None}

    frame = ttk.Frame(root, padding=15)
    frame.pack(fill="both", expand=True)

    title_label = ttk.Label(frame, text="步骤 1: 选择抖音窗口", font=("", 12, "bold"))
    title_label.pack(anchor="w", pady=(0, 8))

    hint_label = ttk.Label(
        frame,
        text="请先打开抖音并播放视频，然后在下方列表中选择抖音窗口。",
        wraplength=460,
        foreground="#666",
    )
    hint_label.pack(anchor="w", pady=(0, 10))

    keyword_var = tk.StringVar(value=config.get("window_title_keyword", "抖音"))
    kw_frame = ttk.Frame(frame)
    kw_frame.pack(fill="x", pady=(0, 8))
    ttk.Label(kw_frame, text="窗口关键词: ").pack(side="left")
    ttk.Entry(kw_frame, textvariable=keyword_var, width=20).pack(side="left")
    ttk.Button(kw_frame, text="刷新列表", command=lambda: refresh_windows()).pack(side="left", padx=8)

    list_frame = ttk.Frame(frame)
    list_frame.pack(fill="both", expand=True, pady=(0, 10))

    win_listbox = tk.Listbox(list_frame, height=8)
    win_listbox.pack(side="left", fill="both", expand=True)
    sb = ttk.Scrollbar(list_frame, orient="vertical", command=win_listbox.yview)
    sb.pack(side="right", fill="y")
    win_listbox.configure(yscrollcommand=sb.set)

    window_cache = []

    def refresh_windows():
        window_cache.clear()
        win_listbox.delete(0, "end")
        keyword = keyword_var.get().strip() or "抖音"
        wins = list_windows()
        for hwnd, title, rect, _ in wins:
            if keyword in title or not keyword:
                display = f"{title[:60]}  |  位置: {rect}"
                window_cache.append((hwnd, title, rect))
                win_listbox.insert("end", display)
        if window_cache:
            win_listbox.select_set(0)

    refresh_windows()

    step1_confirm = ttk.Button(
        frame,
        text="选中此窗口，下一步 →",
        command=lambda: go_to_step2(),
    )
    step1_confirm.pack(anchor="e", pady=(5, 10))

    def go_to_step2():
        sel = win_listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个窗口！")
            return
        hwnd, title, rect = window_cache[sel[0]]
        selected_hwnd["value"] = hwnd
        config["window_title_keyword"] = keyword_var.get().strip() or "抖音"

        img = capture_full_window(hwnd)
        if img is None:
            messagebox.showerror("错误", "无法截图抖音窗口！")
            return
        full_img_ref["value"] = img

        show_clicker_window(root, img, "时间识别区域", "time", save_time_region)

    def save_time_region(region):
        time_region["value"] = region
        config["time_region"] = {
            "left": region[0],
            "top": region[1],
            "right": region[2],
            "bottom": region[3],
        }

        # 基于【听抖音】固定坐标自动计算点赞按钮坐标
        listen_left = -83
        listen_top = 1010
        offset_x = 40
        offset_y = -340
        like_x = listen_left + offset_x
        like_y = listen_top + offset_y

        config["like_button"] = {"x": like_x, "y": like_y}

        # 直接保存配置，不再弹出手动点选点赞窗口
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        messagebox.showinfo(
            "完成",
            f"配置已保存到:\n{CONFIG_FILE}\n\n"
            f"时间识别区域: {config['time_region']}\n"
            f"自动计算点赞坐标: {config['like_button']}\n\n"
            "计算逻辑：听抖音(left=-83,top=1010) 横向+40 纵向-340\n"
            "现在可以运行 douyin_auto_like.py 进行自动点赞了！",
        )
        if root.winfo_exists():
            root.destroy()

    root.mainloop()


def show_clicker_window(parent, pil_image, title_text, mode, on_confirm):
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        return

    win = tk.Toplevel(parent)
    def safe_close():
        if win.winfo_exists():
            win.destroy()
    win.protocol("WM_DELETE_WINDOW", safe_close)
    win.title(f"步骤 2: {title_text}")
    win.attributes("-topmost", True)

    img_w, img_h = pil_image.size
    max_w = min(900, img_w)
    max_h = min(700, img_h)
    scale = min(max_w / img_w, max_h / img_h)
    disp_w = int(img_w * scale)
    disp_h = int(img_h * scale)
    disp_img = pil_image.resize((disp_w, disp_h), Image.LANCZOS)

    instructions = "操作: 按下鼠标左键拖动选择一个矩形区域（包含视频时间显示，如 '0:30/1:30'）"

    top = ttk.Frame(win)
    top.pack(fill="x", padx=10, pady=8)
    ttk.Label(top, text=title_text, font=("", 12, "bold")).pack(anchor="w")
    ttk.Label(top, text=instructions, foreground="#666").pack(anchor="w")

    canvas_frame = ttk.Frame(win)
    canvas_frame.pack(padx=10, pady=(0, 5))
    canvas = tk.Canvas(canvas_frame, width=disp_w, height=disp_h, bg="gray")
    canvas.pack()

    tk_img = ImageTk.PhotoImage(disp_img)
    canvas.create_image(0, 0, anchor="nw", image=tk_img)
    canvas._image_ref = tk_img

    selection = {"start": None, "current": None, "rect_id": None}
    status_var = tk.StringVar(value="")

    def on_down(event):
        selection["start"] = (event.x, event.y)
        selection["current"] = (event.x, event.y)
        if selection["rect_id"]:
            canvas.delete(selection["rect_id"])
        selection["rect_id"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="red", width=2
        )
        status_var.set(f"起点: ({event.x}, {event.y}) - 继续拖动...")

    def on_move(event):
        if selection["start"]:
            selection["current"] = (event.x, event.y)
            sx, sy = selection["start"]
            if selection["rect_id"]:
                canvas.delete(selection["rect_id"])
            selection["rect_id"] = canvas.create_rectangle(
                sx, sy, event.x, event.y, outline="red", width=2
            )
            status_var.set(f"拖动中: {sx},{sy} → {event.x},{event.y}")

    def on_up(event):
        if selection["start"] and selection["current"]:
            sx, sy = selection["start"]
            ex, ey = selection["current"]
            left = min(sx, ex)
            top_ = min(sy, ey)
            right = max(sx, ex)
            bottom = max(sy, ey)
            orig_left = int(left / scale)
            orig_top = int(top_ / scale)
            orig_right = int(right / scale)
            orig_bottom = int(bottom / scale)
            if orig_right - orig_left < 5 or orig_bottom - orig_top < 5:
                status_var.set("选择区域太小，请重新拖选")
                return
            selection["final"] = (orig_left, orig_top, orig_right, orig_bottom)
            status_var.set(
                f"选中区域: ({orig_left},{orig_top},{orig_right},{orig_bottom}) - 点击'保存并继续'"
            )

    canvas.bind("<Button-1>", on_down)
    canvas.bind("<B1-Motion>", on_move)
    canvas.bind("<ButtonRelease-1>", on_up)

    bottom = ttk.Frame(win)
    bottom.pack(fill="x", padx=10, pady=(5, 10))
    ttk.Label(bottom, textvariable=status_var, foreground="#0066cc").pack(side="left")

    def confirm():
        try:
            final = selection.get("final")
            if not final:
                from tkinter import messagebox
                messagebox.showwarning("提示", "请先拖选一个矩形区域！")
                return
            on_confirm(final)
            if win.winfo_exists():
                win.destroy()
        except tk.TclError:
            pass

    def retry():
        if selection["rect_id"]:
            canvas.delete(selection["rect_id"])
        selection["start"] = None
        selection["current"] = None
        selection.pop("final", None)
        status_var.set("已重置，请重新选择")

    btn_frame = ttk.Frame(win)
    btn_frame.pack(pady=(0, 12))
    ttk.Button(btn_frame, text="重新选择", command=retry).pack(side="left", padx=8)
    ttk.Button(btn_frame, text="保存并继续", command=confirm).pack(side="left", padx=8)
    ttk.Button(btn_frame, text="取消", command=safe_close).pack(side="left", padx=8)


if __name__ == "__main__":
    main()