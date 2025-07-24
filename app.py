import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

# (import部分は変更なし)
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import requests
from werkzeug.utils import secure_filename


SCOPES = ['https://www.googleapis.com/auth/drive.file']
CONFIG_FILE = 'config.json'
UPLOAD_FOLDER = 'uploads'

app = Flask(__name__)
app.secret_key = 'ojt-complete-key' 
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# (設定関数、Google/kintone連携関数は変更なし。ただしiframe対応)
def load_configs():
    if not os.path.exists(CONFIG_FILE): return []
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f).get('apps', [])

def save_configs(configs):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'apps': configs}, f, indent=4, ensure_ascii=False)

def get_drive_service():
    # (この関数は変更なし)
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
    # ▼▼▼ iframe形式で返すように変更 ▼▼▼
    iframe_url = f"https://drive.google.com/file/d/{file.get('id')}/preview"
    return f'<iframe src="{iframe_url}" width="640" height="480" allow="autoplay"></iframe>'

def update_kintone_record(domain, api_token, app_id, record_id, field_code, url):
    api_url = f"https://{domain}/k/v1/record.json"
    headers = {"X-Cybozu-API-Token": api_token}
    payload = {"app": app_id, "id": record_id, "record": {field_code: {"value": url}}}
    resp = requests.put(api_url, headers=headers, json=payload)
    resp.raise_for_status()
    # 更新したレコードのURLを返す
    return f"https://{domain}/k/{app_id}/show#record={record_id}"


# --- Flaskのルーティング部分 ---

@app.route('/')
def index():
    configs = load_configs()
    return render_template('index.html', configs=configs)

# (settings, save_settings は変更なし)
@app.route('/settings')
def settings_page():
    configs = load_configs()
    return render_template('settings.html', configs=configs)

@app.route('/save_settings', methods=['POST'])
def save_new_setting():
    new_config = {
        'app_name': request.form['app_name'],
        'kintone_domain': request.form['kintone_domain'],
        'kintone_app_id': request.form['kintone_app_id'],
        'kintone_field_code': request.form['kintone_field_code'],
        'kintone_api_token': request.form['kintone_api_token'],
        'drive_folder_id': request.form['drive_folder_id']
    }
    configs = load_configs()
    configs.append(new_config)
    save_configs(configs)
    flash(f"設定「{new_config['app_name']}」を保存しました。")
    return redirect(url_for('settings_page'))

# ▼▼▼ 完了ページ用のルートを追加 ▼▼▼
@app.route('/success')
def success_page():
    kintone_url = request.args.get('kintone_url')
    return render_template('success.html', kintone_url=kintone_url)

# ▼▼▼ AJAXに対応するように /upload を改修 ▼▼▼
@app.route('/upload', methods=['POST'])
def handle_upload():
    # ... (入力チェック部分は変更なし)
    app_name = request.form.get('app_name')
    record_id = request.form.get('record_id')
    video_file = request.files.get('video_file')
    if not all([app_name, record_id, video_file and video_file.filename != '']):
        return jsonify({'success': False, 'message': '全ての項目を入力・選択してください。'})
    
    configs = load_configs()
    target_config = next((c for c in configs if c['app_name'] == app_name), None)
    if not target_config:
        return jsonify({'success': False, 'message': f'設定「{app_name}」が見つかりません。'})
        
    required_keys = ['drive_folder_id', 'kintone_domain', 'kintone_api_token', 'kintone_app_id', 'kintone_field_code']
    if not all(target_config.get(key) for key in required_keys):
        return jsonify({'success': False, 'message': f'設定「{app_name}」に必要な情報が不足しています。'})

    filename = secure_filename(video_file.filename)
    temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    video_file.save(temp_file_path)

    try:
        drive_service = get_drive_service()
        iframe_tag = upload_video_to_drive(drive_service, temp_file_path, target_config['drive_folder_id'])
        
        kintone_record_url = update_kintone_record(
            domain=target_config['kintone_domain'],
            api_token=target_config['kintone_api_token'],
            app_id=target_config['kintone_app_id'],
            record_id=record_id,
            field_code=target_config['kintone_field_code'],
            url=iframe_tag
        )
        # 成功したら、完了ページのURLをJSONで返す
        success_redirect_url = url_for('success_page', kintone_url=kintone_record_url)
        return jsonify({'success': True, 'redirect_url': success_redirect_url})

    except Exception as e:
        # エラー詳細をJSONで返す
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    # ▼▼▼ 他のPCからアクセスできるように host='0.0.0.0' を追加 ▼▼▼
    app.run(host='0.0.0.0', port=5000, debug=True)