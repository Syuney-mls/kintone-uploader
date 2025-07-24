import tkinter as tk
from tkinter import filedialog, messagebox
import json
import os
import threading

# --- ここから下は、前回作成した upload_tool.py の関数を少し改変して流用 ---
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import requests

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CONFIG_FILE = 'config.json'

def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def upload_video_to_drive(service, file_path, folder_id):
    file_name = os.path.basename(file_path)
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='video/*', resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
    return file.get('id')

def update_kintone_record(domain, api_token, app_id, record_id, field_code, url):
    api_url = f"https://{domain}/k/v1/record.json"
    headers = {"X-Cybozu-API-Token": api_token}
    payload = {"app": app_id, "id": record_id, "record": {field_code: {"value": url}}}
    resp = requests.put(api_url, headers=headers, json=payload)
    resp.raise_for_status()
# --- ここまで流用部分 ---


# --- ここから下がGUIアプリの本体 ---
class KintoneUploaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("kintone動画アップローダー")
        
        # kintone風のカラーテーマ
        kintone_yellow = "#F7D553"
        self.root.configure(bg=kintone_yellow)

        # 設定項目を定義
        self.config_vars = {
            "drive_folder_id": tk.StringVar(),
            "kintone_domain": tk.StringVar(),
            "kintone_app_id": tk.StringVar(),
            "kintone_record_id": tk.StringVar(),
            "kintone_field_code": tk.StringVar(),
            "kintone_api_token": tk.StringVar()
        }
        
        # 設定をファイルから読み込む
        self.load_config()

        # --- UI部品の作成 ---
        # メインフレーム
        main_frame = tk.Frame(root, padx=15, pady=15, bg=kintone_yellow)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 設定入力フィールドの作成
        fields = [
            ("Google Drive フォルダID", "drive_folder_id"),
            ("kintone ドメイン", "kintone_domain"),
            ("kintone アプリID", "kintone_app_id"),
            ("kintone レコード番号", "kintone_record_id"),
            ("kintone フィールドコード", "kintone_field_code"),
            ("kintone APIトークン", "kintone_api_token")
        ]
        for i, (text, var_name) in enumerate(fields):
            tk.Label(main_frame, text=text, bg=kintone_yellow).grid(row=i, column=0, sticky=tk.W, pady=2)
            tk.Entry(main_frame, textvariable=self.config_vars[var_name], width=50).grid(row=i, column=1, pady=2)

        # ファイル選択ボタン
        self.file_path_label = tk.Label(main_frame, text="動画ファイルが選択されていません", bg=kintone_yellow, width=60, anchor=tk.W)
        self.file_path_label.grid(row=len(fields), column=0, columnspan=2, pady=5)
        
        tk.Button(main_frame, text="1. 動画ファイルを選択", command=self.select_file).grid(row=len(fields)+1, column=0, pady=10)

        # 実行ボタン
        self.upload_button = tk.Button(main_frame, text="2. アップロードしてkintone更新", command=self.start_upload)
        self.upload_button.grid(row=len(fields)+1, column=1, pady=10)

        self.selected_file_path = ""

    def select_file(self):
        # ファイル選択ダイアログを開く
        self.selected_file_path = filedialog.askopenfilename(title="動画ファイルを選択", filetypes=[("Video files", "*.mp4 *.mov *.avi")])
        if self.selected_file_path:
            self.file_path_label.config(text=os.path.basename(self.selected_file_path))

    def start_upload(self):
        # 入力チェック
        if not self.selected_file_path:
            messagebox.showerror("エラー", "動画ファイルを選択してください。")
            return
        for key, var in self.config_vars.items():
            if not var.get():
                messagebox.showerror("エラー", f"設定項目「{key}」が入力されていません。")
                return

        # 実行中はボタンを無効化
        self.upload_button.config(state=tk.DISABLED, text="処理中...")
        
        # 設定を保存
        self.save_config()
        
        # 処理がUIを固まらせないように、別スレッドで実行
        threading.Thread(target=self.run_process).start()

    def run_process(self):
        try:
            # Google Driveへの認証とアップロード
            drive_service = get_drive_service()
            folder_id = self.config_vars["drive_folder_id"].get()
            file_id = upload_video_to_drive(drive_service, self.selected_file_path, folder_id)
            
            # kintoneの更新
            embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
            update_kintone_record(
                domain=self.config_vars["kintone_domain"].get(),
                api_token=self.config_vars["kintone_api_token"].get(),
                app_id=self.config_vars["kintone_app_id"].get(),
                record_id=self.config_vars["kintone_record_id"].get(),
                field_code=self.config_vars["kintone_field_code"].get(),
                url=embed_url
            )
            messagebox.showinfo("成功", "すべての処理が完了しました！")
        except Exception as e:
            messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{e}")
        finally:
            # ボタンを元に戻す
            self.upload_button.config(state=tk.NORMAL, text="2. アップロードしてkintone更新")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config_data = json.load(f)
            for key, var in self.config_vars.items():
                var.set(config_data.get(key, ""))
    
    def save_config(self):
        config_data = {key: var.get() for key, var in self.config_vars.items()}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)

if __name__ == '__main__':
    root = tk.Tk()
    app = KintoneUploaderApp(root)
    root.mainloop()