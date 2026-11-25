import os
import sqlite3
import hashlib
import secrets
from datetime import datetime
from flask import (
    Flask, request, jsonify, render_template,
    send_file, abort, redirect, url_for, session
)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5GB max upload

BASE_DIR = '/opt/filehub'
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'files.db')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

GLOBAL_ADMIN_PIN = os.environ.get('FILEHUB_ADMIN_PIN', '123456')

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                admin_pin_hash TEXT NOT NULL,
                admin_salt TEXT NOT NULL,
                download_pin_hash TEXT,
                download_salt TEXT,
                has_download_pin INTEGER NOT NULL DEFAULT 0,
                download_count INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.commit()

init_db()

def hash_pin(pin: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(8)
    h = hashlib.sha256((pin + salt).encode('utf-8')).hexdigest()
    return h, salt

def verify_pin(pin: str, stored_hash: str, salt: str) -> bool:
    if not pin or not stored_hash or not salt:
        return False
    h, _ = hash_pin(pin, salt)
    return secrets.compare_digest(h, stored_hash)

def format_size(bytes_size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}" if unit != 'B' else f"{bytes_size} B"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"

@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM files ORDER BY datetime(upload_time) DESC")
        files = cur.fetchall()

    file_list = []
    for f in files:
        file_list.append({
            'id': f['id'],
            'filename': f['filename'],
            'file_size_fmt': format_size(f['file_size']),
            'upload_time_fmt': f['upload_time'][:16].replace('T', ' '),
            'has_download_pin': bool(f['has_download_pin']),
            'download_count': f['download_count']
        })
    return render_template('index.html', files=file_list, title="FileHub - 极简文件传输")

@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': '未包含文件'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    admin_pin = request.form.get('admin_pin', '').strip()
    download_pin = request.form.get('download_pin', '').strip()

    if admin_pin != GLOBAL_ADMIN_PIN:
        return jsonify({'error': '管理员密码错误，只有管理员可以上传文件'}), 403

    has_download_pin = 0
    dl_hash = None
    dl_salt = None
    if download_pin:
        if not download_pin.isdigit() or len(download_pin) != 6:
            return jsonify({'error': '下载密码若设置必须为 6 位数字'}), 400
        dl_hash, dl_salt = hash_pin(download_pin)
        has_download_pin = 1

    admin_hash, admin_salt = hash_pin(admin_pin)

    file_id = secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:8]
    safe_filename = os.path.basename(file.filename)
    dest_path = os.path.join(UPLOAD_DIR, f"{file_id}_{safe_filename}")
    file.save(dest_path)
    file_size = os.path.getsize(dest_path)

    upload_time = datetime.now().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO files (
                id, filename, file_size, file_path, upload_time,
                admin_pin_hash, admin_salt, download_pin_hash, download_salt,
                has_download_pin, download_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (file_id, safe_filename, file_size, dest_path, upload_time,
              admin_hash, admin_salt, dl_hash, dl_salt, has_download_pin))
        conn.commit()

    return jsonify({
        'id': file_id,
        'filename': safe_filename,
        'size': format_size(file_size),
        'has_download_pin': bool(has_download_pin),
        'download_page': f"/f/{file_id}",
        'manage_page': f"/f/{file_id}/manage"
    })

@app.route('/f/<file_id>')
def file_page(file_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cur.fetchone()
    if not row:
        abort(404, description="文件未找到或已被删除")

    return render_template(
        'download.html',
        file=row,
        file_size_fmt=format_size(row['file_size']),
        error=request.args.get('error'),
        title=f"下载: {row['filename']}"
    )

@app.route('/f/<file_id>/download', methods=['POST'])
def handle_download(file_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cur.fetchone()
    if not row:
        abort(404)

    if row['has_download_pin']:
        pin = request.form.get('pin', '').strip()
        if not verify_pin(pin, row['download_pin_hash'], row['download_salt']):
            return redirect(url_for('file_page', file_id=file_id, error="下载密码错误，请重新输入"))

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE files SET download_count = download_count + 1 WHERE id = ?", (file_id,))
        conn.commit()

    return send_file(
        row['file_path'],
        as_attachment=True,
        download_name=row['filename']
    )

@app.route('/f/<file_id>/manage', methods=['GET', 'POST'])
def manage_page(file_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cur.fetchone()
    if not row:
        abort(404)

    authed = session.get(f"auth_manage_{file_id}") is True
    error = None

    if request.method == 'POST':
        pin = request.form.get('admin_pin', '').strip()
        if pin == GLOBAL_ADMIN_PIN or verify_pin(pin, row['admin_pin_hash'], row['admin_salt']):
            session[f"auth_manage_{file_id}"] = True
            authed = True
        else:
            error = "管理员密码错误，无权管理此文件"

    return render_template(
        'manage.html',
        file=row,
        file_size_fmt=format_size(row['file_size']),
        authed=authed,
        error=error,
        success_msg=request.args.get('msg'),
        title=f"管理: {row['filename']}"
    )

@app.route('/f/<file_id>/manage/update_pin', methods=['POST'])
def update_pin(file_id):
    if not session.get(f"auth_manage_{file_id}"):
        abort(403)

    new_pin = request.form.get('new_download_pin', '').strip()
    with sqlite3.connect(DB_PATH) as conn:
        if new_pin:
            if not new_pin.isdigit() or len(new_pin) != 6:
                return redirect(url_for('manage_page', file_id=file_id, error="新密码必须为 6 位数字"))
            h, s = hash_pin(new_pin)
            conn.execute("UPDATE files SET download_pin_hash = ?, download_salt = ?, has_download_pin = 1 WHERE id = ?", (h, s, file_id))
            msg = "下载密码已成功更新"
        else:
            conn.execute("UPDATE files SET download_pin_hash = NULL, download_salt = NULL, has_download_pin = 0 WHERE id = ?", (file_id,))
            msg = "已清除下载密码，文件已设为公开下载"
        conn.commit()

    return redirect(url_for('manage_page', file_id=file_id, msg=msg))

@app.route('/f/<file_id>/manage/delete', methods=['POST'])
def delete_file(file_id):
    if not session.get(f"auth_manage_{file_id}"):
        abort(403)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT file_path FROM files WHERE id = ?", (file_id,))
        row = cur.fetchone()
        if row:
            if os.path.exists(row['file_path']):
                try:
                    os.remove(row['file_path'])
                except Exception:
                    pass
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            conn.commit()

    session.pop(f"auth_manage_{file_id}", None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8123)
