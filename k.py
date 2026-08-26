from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
from datetime import datetime
import os
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)
DB_NAME = "laundry.db"
app.secret_key = 'freshlaundry_secret_key_2026'

# Konfigurasi Upload Logo
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # Max 2MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== VALIDASI NOMOR WHATSAPP INDONESIA ====================
def normalize_indonesia_phone(value):
    if value is None:
        return None
    raw = str(value).strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("62"):
        digits = "0" + digits[2:]
    elif not digits.startswith("0"):
        return None
    if not re.fullmatch(r"08[1-9]\d{7,10}", digits):
        return None
    return digits

def whatsapp_number(value):
    local = normalize_indonesia_phone(value)
    # WhatsApp wa.me wajib memakai kode negara 62, tanpa tanda + dan tanpa 0 depan.
    return '62' + local[1:] if local else None

# ==================== DATABASE ====================
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS pengaturan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kunci TEXT UNIQUE NOT NULL,
        nilai TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS layanan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL,
        harga REAL NOT NULL,
        satuan TEXT NOT NULL,
        deskripsi TEXT,
        ikon TEXT DEFAULT 'fa-tshirt'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS pesanan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_pelanggan TEXT NOT NULL,
        no_hp TEXT,
        nama_layanan TEXT,
        jumlah REAL NOT NULL,
        total_harga REAL NOT NULL,
        metode_bayar TEXT NOT NULL,
        status TEXT DEFAULT 'Diterima',
        tanggal DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL,
        stok REAL NOT NULL,
        unit TEXT NOT NULL,
        stok_min REAL DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        nama TEXT
    )''')
    
    # Default Admin
    c.execute("SELECT COUNT(*) FROM admin")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO admin (username, password, nama) VALUES (?, ?, ?)",
                  ('admin', 'admin123', 'Administrator'))
    
    # Default Pengaturan
    c.execute("SELECT COUNT(*) FROM pengaturan")
    if c.fetchone()[0] == 0:
        default = [
            ('nama_website', 'FreshLaundry'),
            ('tagline', 'Cucian Bersih, Hidup Lebih Segar'),
            ('deskripsi', 'Layanan laundry kiloan profesional dengan hasil bersih maksimal, wangi tahan lama, dan harga terjangkau.'),
            ('nomor_wa', '081234567890'),
            ('alamat', 'Jl. Kebersihan No. 123, Kota Sejahtera'),
            ('jam_operasional', 'Senin - Sabtu: 08:00 - 20:00 | Minggu: 09:00 - 17:00'),
            ('stat_pelanggan', '5K+'),
            ('stat_cucian', '50K+'),
            ('stat_rating', '4.9'),
            ('hero_subtitle', 'Laundry Terpercaya Sejak 2020'),
            ('warna_utama', '#0d9669'),
            ('warna_sekunder', '#d4724a'),
            ('logo_path', ''),
            ('hero_icon_path', ''),
            ('hero_icon_path_2', '')
        ]
        c.executemany("INSERT INTO pengaturan (kunci, nilai) VALUES (?, ?)", default)
    
    c.execute("INSERT OR IGNORE INTO pengaturan (kunci,nilai) VALUES ('hero_icon_path','')")
    c.execute("INSERT OR IGNORE INTO pengaturan (kunci,nilai) VALUES ('hero_icon_path_2','')")

    # Default Layanan
    c.execute("SELECT COUNT(*) FROM layanan")
    if c.fetchone()[0] == 0:
        default = [
            ('Cuci Kiloan Reguler', 8000, 'Kg', 'Cuci, kering, lipat rapi dengan parfum premium. Selesai 2-3 hari.', 'fa-tshirt'),
            ('Cuci Kiloan Express', 14000, 'Kg', 'Layanan cepat selesai dalam 1 hari.', 'fa-bolt'),
            ('Dry Cleaning', 25000, 'Pcs', 'Perawatan khusus untuk jas, kebaya, bahan sensitif.', 'fa-spray-can'),
            ('Cuci Bedcover', 25000, 'Pcs', 'Pembersihan mendalam untuk bedcover & selimut.', 'fa-bed'),
            ('Cuci Sepatu Premium', 40000, 'Pasang', 'Deep cleaning sepatu tampak seperti baru.', 'fa-shoe-prints'),
            ('Layanan Antar-Jemput', 0, 'Pcs', 'Gratis antar-jemput radius 5 km.', 'fa-truck')
        ]
        c.executemany("INSERT INTO layanan (nama, harga, satuan, deskripsi, ikon) VALUES (?, ?, ?, ?, ?)", default)
    
    # Default Inventory
    c.execute("SELECT COUNT(*) FROM inventory")
    if c.fetchone()[0] == 0:
        default = [
            ('Deterjen Bubuk', 25, 'Kg', 10),
            ('Softener Pewangi', 15, 'Liter', 5),
            ('Pemutih Pakaian', 8, 'Liter', 3),
            ('Plastik Packing', 200, 'Pcs', 50),
            ('Hanger', 80, 'Pcs', 30),
            ('Parfum Laundry', 12, 'Botol', 5)
        ]
        c.executemany("INSERT INTO inventory (nama, stok, unit, stok_min) VALUES (?, ?, ?, ?)", default)
    
    conn.commit()
    conn.close()

def get_pengaturan():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT kunci, nilai FROM pengaturan")
    data = {row['kunci']: row['nilai'] for row in c.fetchall()}
    conn.close()
    if 'logo_path' not in data: data['logo_path'] = ''
    return data

# ==================== HALAMAN UTAMA ====================
@app.route('/')
def home():
    p = get_pengaturan()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM layanan ORDER BY id")
    layanan = [dict(row) for row in c.fetchall()]
    conn.close()
    from datetime import datetime  # ← tambahkan baris ini
    p['nomor_wa_wa'] = whatsapp_number(p.get('nomor_wa', '')) or ''
    return render_template('index.html', p=p, layanan=layanan, now=datetime.now())

@app.route('/api/cek-laundry', methods=['POST'])
def cek_laundry():
    data = request.json or {}
    nama = data.get('nama', '').strip().lower()
    no_hp = normalize_indonesia_phone(data.get('no_hp', ''))
    if not nama:
        return jsonify({'error':'Nama wajib diisi'}), 400
    if not no_hp:
        return jsonify({'error':'Nomor WhatsApp wajib nomor Indonesia, contoh 081234567890'}), 400
    conn = get_db()
    c = conn.cursor()
    intl = whatsapp_number(no_hp)
    c.execute("SELECT * FROM pesanan WHERE LOWER(nama_pelanggan) LIKE ? AND (REPLACE(REPLACE(REPLACE(no_hp,'+',''),' ',''),'-','') LIKE ? OR REPLACE(REPLACE(REPLACE(no_hp,'+',''),' ',''),'-','') LIKE ?) ORDER BY id DESC", (f'%{nama}%', f'%{no_hp}%', f'%{intl}%'))
    hasil = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(hasil)

# ==================== LOGIN ADMIN ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM admin WHERE username = ? AND password = ?", (username, password))
        admin = c.fetchone()
        conn.close()
        if admin:
            session['admin_logged'] = True
            session['admin_nama'] = admin['nama']
            return redirect(url_for('admin'))
        return render_template('login.html', error="Username atau password salah!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/admin')
def admin():
    if not session.get('admin_logged'):
        return redirect(url_for('login'))
    p = get_pengaturan()
    return render_template('admin.html', p=p, admin_nama=session.get('admin_nama', 'Admin'))

# ==================== API LAYANAN ====================
@app.route('/api/layanan', methods=['GET', 'POST'])
def api_layanan():
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json
        c.execute("INSERT INTO layanan (nama, harga, satuan, deskripsi, ikon) VALUES (?, ?, ?, ?, ?)",
                  (d['nama'], d['harga'], d['satuan'], d.get('deskripsi',''), d.get('ikon','fa-tshirt')))
        conn.commit()
        conn.close()
        return jsonify({'message':'Layanan ditambahkan'})
    else:
        c.execute("SELECT * FROM layanan ORDER BY id")
        data = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(data)

@app.route('/api/layanan/<int:id>', methods=['DELETE'])
def hapus_layanan(id):
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    conn.cursor().execute("DELETE FROM layanan WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({'message':'Layanan dihapus'})

# ==================== API PESANAN ====================
@app.route('/api/pesanan', methods=['GET', 'POST'])
def api_pesanan():
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json
        no_hp = normalize_indonesia_phone(d.get('no_hp', ''))
        if not no_hp:
            conn.close()
            return jsonify({'error':'Nomor WhatsApp wajib nomor Indonesia, contoh 081234567890'}), 400
        c.execute('''INSERT INTO pesanan 
            (nama_pelanggan, no_hp, nama_layanan, jumlah, total_harga, metode_bayar, status)
            VALUES (?, ?, ?, ?, ?, ?, 'Diterima')''',
            (d['nama_pelanggan'], no_hp, d['nama_layanan'], d['jumlah'], d['total_harga'], d['metode_bayar']))
        conn.commit()
        conn.close()
        return jsonify({'message':'Pesanan dibuat'})
    else:
        c.execute("SELECT * FROM pesanan ORDER BY id DESC")
        data = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(data)

@app.route('/api/pesanan/<int:id>', methods=['PUT', 'DELETE'])
def api_pesanan_detail(id):
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    if request.method == 'DELETE':
        c.execute("DELETE FROM pesanan WHERE id = ?", (id,))
    else:
        d = request.json
        c.execute("UPDATE pesanan SET status=? WHERE id=?", (d.get('status','Diterima'), id))
    conn.commit()
    conn.close()
    return jsonify({'message':'Berhasil'})

# ==================== API INVENTORY ====================
@app.route('/api/inventory', methods=['GET', 'POST'])
def api_inventory():
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json
        c.execute("INSERT INTO inventory (nama, stok, unit, stok_min) VALUES (?, ?, ?, ?)",
                  (d['nama'], d['stok'], d['unit'], d.get('stok_min',0)))
        conn.commit()
        conn.close()
        return jsonify({'message':'Item ditambahkan'})
    else:
        c.execute("SELECT * FROM inventory ORDER BY id")
        data = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(data)

@app.route('/api/inventory/<int:id>', methods=['PUT', 'DELETE'])
def api_inventory_detail(id):
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    if request.method == 'DELETE':
        c.execute("DELETE FROM inventory WHERE id = ?", (id,))
    else:
        d = request.json
        c.execute("UPDATE inventory SET nama=?, stok=?, unit=?, stok_min=? WHERE id=?",
                  (d['nama'], d['stok'], d['unit'], d.get('stok_min',0), id))
    conn.commit()
    conn.close()
    return jsonify({'message':'Berhasil'})

# ==================== API LAPORAN ====================
@app.route('/api/laporan')
def api_laporan():
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(total_harga),0) as total, COUNT(*) as cnt FROM pesanan WHERE DATE(tanggal) = DATE('now','localtime')")
    harian = c.fetchone()
    c.execute("SELECT COALESCE(SUM(total_harga),0) as total, COUNT(*) as cnt FROM pesanan WHERE strftime('%W', tanggal) = strftime('%W', 'now')")
    mingguan = c.fetchone()
    c.execute("SELECT COALESCE(SUM(total_harga),0) as total, COUNT(*) as cnt FROM pesanan WHERE strftime('%m-%Y', tanggal) = strftime('%m-%Y', 'now')")
    bulanan = c.fetchone()
    conn.close()
    return jsonify({
        'harian': {'total': harian['total'], 'count': harian['cnt']},
        'mingguan': {'total': mingguan['total'], 'count': mingguan['cnt']},
        'bulanan': {'total': bulanan['total'], 'count': bulanan['cnt']}
    })

# ==================== API PENGATURAN ====================
@app.route('/api/pengaturan', methods=['GET', 'POST'])
def api_pengaturan():
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        d = request.json or {}
        if 'nomor_wa' in d:
            nomor = normalize_indonesia_phone(d.get('nomor_wa'))
            if not nomor:
                conn.close()
                return jsonify({'error':'Nomor WhatsApp wajib nomor Indonesia. Gunakan contoh 081234567890 atau +6281234567890.'}), 400
            d['nomor_wa'] = nomor
        for kunci, nilai in d.items():
            c.execute("INSERT OR REPLACE INTO pengaturan (kunci, nilai) VALUES (?, ?)", (kunci, str(nilai)))
        conn.commit()
        conn.close()
        return jsonify({'message':'Pengaturan disimpan'})
    else:
        c.execute("SELECT kunci, nilai FROM pengaturan")
        data = {row['kunci']: row['nilai'] for row in c.fetchall()}
        conn.close()
        return jsonify(data)


# ==================== API UPLOAD 2 IKON INDEX ====================
def _save_index_icon(setting_key, field_name, prefix):
    if not session.get('admin_logged'):
        return jsonify({'error':'Unauthorized'}), 401
    file=request.files.get(field_name)
    if not file or not file.filename:
        return jsonify({'error':'Tidak ada file ikon'}),400
    if not allowed_file(file.filename):
        return jsonify({'error':'Format tidak diizinkan (PNG/JPG/JPEG/GIF/SVG/WEBP)'}),400
    os.makedirs(app.config['UPLOAD_FOLDER'],exist_ok=True)
    ext=file.filename.rsplit('.',1)[1].lower()
    filename=f"{prefix}.{ext}"
    filepath=os.path.join(app.config['UPLOAD_FOLDER'],filename)
    conn=get_db(); c=conn.cursor()
    c.execute("SELECT nilai FROM pengaturan WHERE kunci=?",(setting_key,))
    old=c.fetchone()
    if old and old['nilai'] and str(old['nilai']).startswith('/static/uploads/'):
        old_path=os.path.join(app.config['UPLOAD_FOLDER'],os.path.basename(old['nilai']))
        if os.path.abspath(old_path)!=os.path.abspath(filepath) and os.path.exists(old_path):
            try: os.remove(old_path)
            except OSError: pass
    file.save(filepath)
    url=f'/static/uploads/{filename}'
    c.execute("INSERT OR REPLACE INTO pengaturan (kunci,nilai) VALUES (?,?)",(setting_key,url))
    conn.commit(); conn.close()
    return jsonify({'message':'Ikon berhasil diupload','path':url})

def _reset_index_icon(setting_key):
    if not session.get('admin_logged'):
        return jsonify({'error':'Unauthorized'}),401
    conn=get_db(); c=conn.cursor()
    c.execute("SELECT nilai FROM pengaturan WHERE kunci=?",(setting_key,)); old=c.fetchone()
    if old and old['nilai'] and str(old['nilai']).startswith('/static/uploads/'):
        old_path=os.path.join(app.config['UPLOAD_FOLDER'],os.path.basename(old['nilai']))
        if os.path.exists(old_path):
            try: os.remove(old_path)
            except OSError: pass
    c.execute("INSERT OR REPLACE INTO pengaturan (kunci,nilai) VALUES (?,?)",(setting_key,''))
    conn.commit(); conn.close()
    return jsonify({'message':'Ikon dikembalikan'})

@app.route('/api/upload-hero-icon',methods=['POST'])
def upload_hero_icon(): return _save_index_icon('hero_icon_path','hero_icon','hero_icon')

@app.route('/api/delete-hero-icon',methods=['POST'])
def delete_hero_icon(): return _reset_index_icon('hero_icon_path')

@app.route('/api/upload-hero-icon-2',methods=['POST'])
def upload_hero_icon_2(): return _save_index_icon('hero_icon_path_2','hero_icon_2','hero_icon_2')

@app.route('/api/delete-hero-icon-2',methods=['POST'])
def delete_hero_icon_2(): return _reset_index_icon('hero_icon_path_2')

# ==================== API UPLOAD LOGO ====================
@app.route('/api/upload-logo', methods=['POST'])
def upload_logo():
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    if 'logo' not in request.files: return jsonify({'error':'Tidak ada file'}), 400
    file = request.files['logo']
    if file.filename == '': return jsonify({'error':'Tidak ada file dipilih'}), 400
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"logo.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Hapus logo lama
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT nilai FROM pengaturan WHERE kunci = 'logo_path'")
        old = c.fetchone()
        if old and old['nilai']:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(old['nilai']))
            if os.path.exists(old_path): os.remove(old_path)
        
        file.save(filepath)
        logo_path = f'/static/uploads/{filename}'
        c.execute("INSERT OR REPLACE INTO pengaturan (kunci, nilai) VALUES (?, ?)", ('logo_path', logo_path))
        conn.commit()
        conn.close()
        return jsonify({'message':'Logo berhasil diupload', 'path': logo_path})
    return jsonify({'error':'Format tidak diizinkan (PNG/JPG/JPEG/GIF/SVG)'}), 400

@app.route('/api/delete-logo', methods=['POST'])
def delete_logo():
    if not session.get('admin_logged'): return jsonify({'error':'Unauthorized'}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT nilai FROM pengaturan WHERE kunci = 'logo_path'")
    old = c.fetchone()
    if old and old['nilai']:
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(old['nilai']))
        if os.path.exists(old_path): os.remove(old_path)
    c.execute("DELETE FROM pengaturan WHERE kunci = 'logo_path'")
    conn.commit()
    conn.close()
    return jsonify({'message':'Logo dihapus'})


# ==================== API UPLOAD IKON LAYANAN ====================
@app.route('/api/upload-ikon-layanan', methods=['POST'])
def upload_ikon_layanan():
    if not session.get('admin_logged'):
        return jsonify({'error':'Unauthorized'}), 401
    if 'ikon' not in request.files:
        return jsonify({'error':'Tidak ada file ikon'}), 400
    file = request.files['ikon']
    layanan_id = request.form.get('layanan_id')
    if not layanan_id:
        return jsonify({'error':'ID layanan tidak ditemukan'}), 400
    if file.filename == '':
        return jsonify({'error':'Tidak ada file dipilih'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error':'Format tidak diizinkan (PNG/JPG/JPEG/GIF/SVG)'}), 400
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT ikon FROM layanan WHERE id=?", (layanan_id,))
        old = c.fetchone()
        ext = file.filename.rsplit('.',1)[1].lower()
        filename = f"layanan_{layanan_id}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        if old and old['ikon'] and str(old['ikon']).startswith('/static/uploads/'):
            old_file = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(old['ikon']))
            if os.path.exists(old_file):
                os.remove(old_file)

        file.save(filepath)
        icon_path = f'/static/uploads/{filename}'
        c.execute("UPDATE layanan SET ikon=? WHERE id=?", (icon_path, layanan_id))
        conn.commit()
        conn.close()
        return jsonify({'message':'Ikon layanan berhasil diupload','path':icon_path})
    except Exception as e:
        return jsonify({'error':str(e)}), 500

# ==================== RUN ====================
if __name__ == '__main__':
    init_db()
    print("\n" + "="*60)
    print("🚀 FRESHLAUNDRY SERVER BERJALAN!")
    print("="*60)
    print("📱 Akses lokal: http://localhost:5000")
    print("🌐 Akses LAN: http://<IP-KAMU>:5000")
    print("🔑 Login Admin: /login   (admin / admin123)")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
