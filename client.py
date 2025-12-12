import sys
import threading
import json
import os
import io
import time
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageGrab
from pynput import mouse
from pystray import MenuItem as item
import pystray
import tkinter as tk
from tkinter import simpledialog, messagebox

# --- 全局变量 ---
# 【更新】将 click_time 加入到配置字典中
config = {
    "username": "default_user",
    "server_address": "http://127.0.0.1:7860/",
    "click_time": 4  # 默认长按时间为 4 秒
}

left_button_press_time = None
tray_icon = None
mouse_listener_thread = None
root_tk = None
SHUTDOWN_EVENT = threading.Event()

# --- 核心功能 ---
def take_screenshot_and_upload():
    global config
    # 【更新】从 config 字典中读取按压时间用于日志打印
    print(f"[{datetime.now()}] Hold duration >= {config['click_time']}s detected. Triggering screenshot for user: {config['username']}")
    try:
        screenshot = ImageGrab.grab()
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        files = {'image': ('screenshot.png', img_byte_arr, 'image/png')}
        payload = {
            'username': config['username'],
            'timestamp': datetime.now().isoformat()
        }
        upload_url = os.path.join(config['server_address'], 'api/upload').replace('\\', '/')
        response = requests.post(upload_url, data=payload, files=files, timeout=15)
        response.raise_for_status()
        print(f"[{datetime.now()}] Screenshot uploaded successfully. Server response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Error uploading screenshot: {e}")
    except Exception as e:
        print(f"[{datetime.now()}] An unexpected error occurred: {e}")

def on_click(x, y, button, pressed):
    global left_button_press_time, config
    if button == mouse.Button.left:
        if pressed:
            left_button_press_time = time.time()
        else:
            if left_button_press_time is not None:
                hold_duration = time.time() - left_button_press_time
                left_button_press_time = None
                # 【更新】从 config 字典中读取按压时间进行判断
                if hold_duration >= config['click_time']:
                    threading.Thread(target=take_screenshot_and_upload, daemon=True).start()

# --- 配置管理 ---
def show_config_window():
    global config, root_tk
    
    root_tk.deiconify()
    root_tk.lift()
    root_tk.focus_force()

    username = simpledialog.askstring("配置 - 步骤 1/3", "请输入你的用户名:", parent=root_tk, initialvalue=config.get("username", ""))
    if username is not None: config["username"] = username
    
    server_address = simpledialog.askstring("配置 - 步骤 2/3", "请输入服务器地址:", parent=root_tk, initialvalue=config.get("server_address", ""))
    if server_address is not None: config["server_address"] = server_address

    # 【新增】增加一个对话框用于配置按压时间
    click_time_str = simpledialog.askstring("配置 - 步骤 3/3", "请输入长按触发时间（秒）:", parent=root_tk, initialvalue=str(config.get("click_time", 4)))
    if click_time_str is not None:
        try:
            # 尝试将输入转换为浮点数，并确保它大于0
            new_time = float(click_time_str)
            if new_time > 0:
                config["click_time"] = new_time
            else:
                messagebox.showwarning("无效输入", "时间必须是大于0的数字。将使用上一次的有效值。")
        except (ValueError, TypeError):
            messagebox.showwarning("无效输入", "请输入有效的数字作为时间。将使用上一次的有效值。")

    root_tk.withdraw()
    
    # 【更新】在最终的提示信息中也显示按压时间
    root_tk.after(100, lambda: messagebox.showinfo("配置完成", 
        f"配置已设定！\n\n"
        f"用户名: {config['username']}\n"
        f"服务器: {config['server_address']}\n"
        f"长按时间: {config['click_time']} 秒\n\n"
        f"程序将在后台开始工作。"
    ))
    
# --- 系统托盘管理 ---
def create_tray_icon_image():
    width, height = 64, 64
    image = Image.new('RGB', (width, height), 'white')
    dc = ImageDraw.Draw(image)
    cell_size = width // 2
    dc.rectangle((cell_size, 0, width - 1, cell_size - 1), fill='black')
    dc.rectangle((0, cell_size, cell_size - 1, height - 1), fill='black')
    return image

def on_settings_clicked():
    global root_tk
    if root_tk:
        root_tk.after(0, show_config_window)

def on_exit_clicked():
    print("Shutdown signal sent from tray icon.")
    SHUTDOWN_EVENT.set()

# --- 主程序入口 ---
def main():
    global mouse_listener_thread, tray_icon, root_tk
    
    root_tk = tk.Tk()
    root_tk.withdraw()

    show_config_window()

    mouse_listener = mouse.Listener(on_click=on_click)
    mouse_listener.start()
    mouse_listener_thread = mouse_listener
    print("Mouse listener started in the background.")

    image = create_tray_icon_image()
    menu = (item('配置...', on_settings_clicked), item('退出', on_exit_clicked))
    tray_icon = pystray.Icon("ScreenshotUploader", image, "截图上传工具", menu)
    tray_icon.run_detached()
    print("System tray icon started in a background thread.")

    def check_for_shutdown():
        if SHUTDOWN_EVENT.is_set():
            print("Shutdown signal detected. Cleaning up...")
            if mouse_listener_thread is not None:
                mouse_listener_thread.stop()
            if tray_icon is not None:
                tray_icon.stop()
            if root_tk is not None:
                root_tk.destroy()
        else:
            root_tk.after(200, check_for_shutdown)

    print("Main GUI thread is running. Starting shutdown checker.")
    root_tk.after(200, check_for_shutdown)
    
    root_tk.mainloop()
    
    print("Application has been shut down.")

if __name__ == "__main__":
    main()