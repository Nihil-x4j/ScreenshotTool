import os
import shutil
from datetime import datetime
from typing import List, Dict

import gradio as gr
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse

# --- 配置 ---
UPLOAD_DIR = "uploads"
ALL_USERS_OPTION = "所有用户"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- 全局状态管理 ---
class AppState:
    def __init__(self):
        self._last_update_time = datetime.now()

    @property
    def last_update_time(self) -> datetime:
        return self._last_update_time

    def mark_updated(self):
        self._last_update_time = datetime.now()
        print(f"FileSystem updated at: {self._last_update_time}")

app_state = AppState()

# --- FastAPI 应用实例 ---
app = FastAPI(
    title="图片浏览与管理服务器",
    description="一个使用 FastAPI 和 Gradio 搭建的图片展示与删除服务器。"
)

# --- 核心逻辑函数 (后端) ---
def get_all_users() -> List[str]:
    if not os.path.exists(UPLOAD_DIR): return []
    users = [d for d in os.listdir(UPLOAD_DIR) if os.path.isdir(os.path.join(UPLOAD_DIR, d))]
    return sorted(users)

def get_user_images(username: str) -> List[str]:
    image_paths = []
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    if username == ALL_USERS_OPTION:
        for user in get_all_users():
            user_dir = os.path.join(UPLOAD_DIR, user)
            for f in os.listdir(user_dir):
                if os.path.splitext(f)[1].lower() in image_extensions:
                    image_paths.append(os.path.join(user_dir, f))
    elif username:
        user_dir = os.path.join(UPLOAD_DIR, username)
        if os.path.exists(user_dir):
            for f in os.listdir(user_dir):
                if os.path.splitext(f)[1].lower() in image_extensions:
                    image_paths.append(os.path.join(user_dir, f))
    return sorted(image_paths, key=os.path.basename, reverse=True)

def delete_user_images(username: str) -> bool:
    if not username or username == ALL_USERS_OPTION: return False
    user_dir = os.path.join(UPLOAD_DIR, username)
    if not os.path.isdir(user_dir): return False
    try:
        shutil.rmtree(user_dir)
        app_state.mark_updated()
        return True
    except Exception as e:
        print(f"删除用户 '{username}' 的目录失败: {e}")
        return False

# --- FastAPI 路由 ---
@app.post("/api/upload", tags=["API"])
async def api_upload_image(username: str = Form(...), timestamp: str = Form(...), image: UploadFile = File(...)):
    if not image.content_type.startswith("image/"): raise HTTPException(status_code=400, detail="文件类型错误，请上传图片。")
    user_dir = os.path.join(UPLOAD_DIR, username)
    os.makedirs(user_dir, exist_ok=True)
    server_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")
    filename = f"{server_timestamp}_{image.filename}"
    filepath = os.path.join(user_dir, filename)
    try:
        with open(filepath, "wb") as buffer: shutil.copyfileobj(image.file, buffer)
        app_state.mark_updated()
    finally:
        image.file.close()
    return JSONResponse(status_code=201, content={"message": "图片上传成功", "server_path": filepath})

# --- Gradio 界面 ---
def create_gradio_ui():
    with gr.Blocks(theme=gr.themes.Soft()) as demo:
        # --- 状态与计时器 ---
        client_last_update = gr.State(value=app_state.last_update_time)
        timer = gr.Timer(2)

        gr.Markdown("## 🖼️ 图片浏览与管理服务器")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 1. 筛选与操作")
                username_dropdown = gr.Dropdown(
                    label="选择用户 (默认为全部)",
                    choices=[ALL_USERS_OPTION] + get_all_users(),
                    value=ALL_USERS_OPTION,
                    interactive=True,
                )
                refresh_button = gr.Button("🔄 手动刷新")
                
                gr.Markdown("---")
                batch_delete_button = gr.Button("🗑️ 批量删除该用户所有图片", variant="stop")

            with gr.Column(scale=4):
                gr.Markdown("### 2. 图片画廊")
                gallery = gr.Gallery(
                    label="图片", show_label=False, elem_id="gallery",
                    columns=6, object_fit="contain", height="auto"
                )

        # --- Gradio 事件处理函数 ---
        def update_ui_components(username: str) -> Dict:
            all_users_from_disk = [ALL_USERS_OPTION] + get_all_users()
            username_to_display = username
            if username not in all_users_from_disk:
                username_to_display = ALL_USERS_OPTION
            images_to_display = get_user_images(username_to_display)
            return {
                username_dropdown: gr.Dropdown(choices=all_users_from_disk, value=username_to_display),
                gallery: gr.Gallery(value=images_to_display),
                client_last_update: app_state.last_update_time
            }
        
        def handle_delete_batch(username: str):
            if not username or username == ALL_USERS_OPTION:
                gr.Warning("请选择一个具体的用户进行批量删除！")
                return update_ui_components(username)
            if delete_user_images(username):
                gr.Info(f"用户 '{username}' 的所有图片已删除！")
                return update_ui_components(ALL_USERS_OPTION)
            else:
                gr.Error(f"批量删除用户 '{username}' 的图片失败！")
                return update_ui_components(username)
        
        def check_for_updates(username: str, last_known_update: datetime):
            if app_state.last_update_time > last_known_update:
                return update_ui_components(username)
            return {
                username_dropdown: gr.skip(), gallery: gr.skip(),
                client_last_update: last_known_update
            }
        
        # --- 绑定事件 ---
        username_dropdown.change(fn=update_ui_components, inputs=username_dropdown, outputs=[username_dropdown, gallery, client_last_update])
        refresh_button.click(fn=update_ui_components, inputs=username_dropdown, outputs=[username_dropdown, gallery, client_last_update])
        batch_delete_button.click(fn=handle_delete_batch, inputs=username_dropdown, outputs=[username_dropdown, gallery, client_last_update])
        
        def initial_load():
            return update_ui_components(ALL_USERS_OPTION)
        demo.load(fn=initial_load, outputs=[username_dropdown, gallery, client_last_update])
        
        timer.tick(fn=check_for_updates, inputs=[username_dropdown, client_last_update], outputs=[username_dropdown, gallery, client_last_update])

    return demo

# --- 挂载与启动 ---
gradio_app = create_gradio_ui()
app = gr.mount_gradio_app(app, gradio_app, path="/")

if __name__ == "__main__":
    print("服务器正在启动...")
    print("访问 Web UI: http://127.0.0.1:7860")
    print("API 文档: http://127.0.0.1:7860/docs")
    uvicorn.run(app, host="0.0.0.0", port=7880)