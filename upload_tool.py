import os
import requests # kintone連携のために追加
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    """Google Drive APIへの認証を行い、操作用のサービスオブジェクトを返す"""
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
    """指定された動画ファイルをGoogle Driveの特定フォルダにアップロードする"""
    if not os.path.exists(file_path):
        print(f"エラー: ファイルが見つかりません - {file_path}")
        return None
    file_name = os.path.basename(file_path)
    print(f"「{file_name}」をアップロードしています...")
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='video/*', resumable=True)
    try:
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print("アップロードが完了しました！")
        service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
        print("共有設定を「リンクを知っている全員」に変更しました。")
        return file.get('id')
    except HttpError as error:
        print(f"アップロード中にエラーが発生しました: {error}")
        return None

# ▼▼▼ここから下が新しく追加・変更された部分▼▼▼

def update_kintone_record(domain, api_token, app_id, record_id, field_code, url):
    """kintoneの特定レコードのフィールドを更新する"""
    api_url = f"https://{domain}/k/v1/record.json"
    
    headers = {
        "X-Cybozu-API-Token": api_token
    }
    
    payload = {
        "app": app_id,
        "id": record_id,
        "record": {
            field_code: {
                "value": url
            }
        }
    }
    
    print("\nkintoneレコードを更新しています...")
    
    try:
        resp = requests.put(api_url, headers=headers, json=payload)
        resp.raise_for_status()  # エラーがあれば例外を発生させる
        print("kintoneの更新が完了しました！")
        return True
    except requests.exceptions.RequestException as e:
        print(f"kintoneの更新中にエラーが発生しました: {e}")
        print(f"サーバーからの応答: {e.response.text}")
        return False

if __name__ == '__main__':
    # 1. Google Driveへの認証とアップロード
    drive_service = get_drive_service()
    target_file = input("アップロードする動画ファイルのフルパスを入力してください: ")
    target_folder_id = input("アップロード先のGoogle DriveフォルダIDを入力してください: ")
    
    file_id = upload_video_to_drive(drive_service, target_file, target_folder_id)
    
    # アップロードが成功した場合のみ、kintoneの更新処理に進む
    if file_id:
        embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
        print("\n--- Google Drive処理結果 ---")
        print(f"kintone埋め込み用URL: {embed_url}")
        
        print("\n--- kintone情報入力 ---")
        kintone_domain = input("kintoneのドメインを入力してください (例: example.cybozu.com): ")
        kintone_app_id = input("kintoneのアプリIDを入力してください: ")
        kintone_record_id = input("更新するレコード番号を入力してください: ")
        kintone_field_code = input("URLを保存するフィールドコードを入力してください: ")
        kintone_api_token = input("kintoneのAPIトークンを入力してください: ")
        
        # 2. kintoneレコードの更新
        update_kintone_record(
            kintone_domain,
            kintone_api_token,
            kintone_app_id,
            kintone_record_id,
            kintone_field_code,
            embed_url
        )
        
        print("\nすべての処理が完了しました。")