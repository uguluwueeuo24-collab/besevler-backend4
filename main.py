import os
import sqlite3
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB_NAME = "kurye_sistem.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Kullanıcılar Tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            jeton INTEGER DEFAULT 50
        )
    ''')
    # Siparişler Tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            market TEXT,
            address TEXT,
            items TEXT,
            total_jeton INTEGER,
            status TEXT DEFAULT 'Hazırlanıyor',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Sistem Ayarları Tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('kilitli', '0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('duyuru', 'Beşevler Jet Kurye hizmetinizdedir!')")
    
    # Varsayılan Admin/Demo Kullanıcısı
    cursor.execute("INSERT OR IGNORE INTO users (username, password, name, jeton) VALUES ('adar', '1234', 'Adar', 100)")
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def calisma_saati_mi():
    now = datetime.now()
    gun = now.weekday()
    saat = now.hour
    if gun in [5, 6]:
        return 13 <= saat < 20
    else:
        return 19 <= saat < 21

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ok", "mesaj": "Beşevler Jet Kurye Sunucusu Aktif!"})

@app.route('/durum', methods=['GET'])
def durum():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='kilitli'")
    kilitli = cursor.fetchone()['value'] == '1'
    cursor.execute("SELECT value FROM settings WHERE key='duyuru'")
    duyuru = cursor.fetchone()['value']
    conn.close()

    acik_mi = calisma_saati_mi() and not kilitli
    return jsonify({
        "siparis_acik": acik_mi,
        "kilitli": kilitli,
        "duyuru": duyuru,
        "mesaj": "Siparişler açık!" if acik_mi else "Şu an sipariş kabul edilmiyor."
    })

@app.route('/kayit', methods=['POST'])
def kayit():
    data = request.json or {}
    u, p, a = data.get("kullanici_adi"), data.get("sifre"), data.get("ad")
    if not u or not p or not a:
        return jsonify({"success": False, "mesaj": "Eksik bilgi girdiniz!"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, name, jeton) VALUES (?, ?, ?, 50)", (u, p, a))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "mesaj": "Kayıt başarılı! 50 Hediye Jeton tanımlandı."})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "mesaj": "Bu kullanıcı adı zaten kullanılıyor!"}), 400

@app.route('/giris', methods=['POST'])
def giris():
    data = request.json or {}
    u, p = data.get("kullanici_adi"), data.get("sifre")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p))
    user = cursor.fetchone()
    conn.close()

    if user:
        return jsonify({"success": True, "username": user['username'], "ad": user['name'], "bakiye": user['jeton']})
    return jsonify({"success": False, "mesaj": "Hatalı kullanıcı adı veya şifre!"}), 401

@app.route('/hesap-sil', methods=['POST'])
def hesap_sil():
    data = request.json or {}
    u = data.get("kullanici_adi")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username=?", (u,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "mesaj": "Hesabınız başarıyla silindi."})

@app.route('/jeton-yukle', methods=['POST'])
def jeton_yukle():
    data = request.json or {}
    u, miktar = data.get("username"), data.get("miktar", 0)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET jeton = jeton + ? WHERE username=?", (miktar, u))
    conn.commit()
    cursor.execute("SELECT jeton FROM users WHERE username=?", (u,))
    yeni_bakiye = cursor.fetchone()['jeton']
    conn.close()
    return jsonify({"success": True, "yeni_bakiye": yeni_bakiye})

@app.route('/siparis-ver', methods=['POST'])
def siparis_ver():
    data = request.json or {}
    u = data.get("username")
    market = data.get("market")
    adres = data.get("adres")
    items = data.get("siparis")
    maliyet = data.get("jeton_maliyeti", 20)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT jeton FROM users WHERE username=?", (u,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Kullanıcı bulunamadı!"}), 404

    if row['jeton'] < maliyet:
        conn.close()
        return jsonify({"success": False, "error": "Yetersiz Jeton Bakiyesi!"}), 400

    cursor.execute("UPDATE users SET jeton = jeton - ? WHERE username=?", (maliyet, u))
    cursor.execute("INSERT INTO orders (username, market, address, items, total_jeton) VALUES (?, ?, ?, ?, ?)",
                   (u, market, adres, items, maliyet))
    conn.commit()
    cursor.execute("SELECT jeton FROM users WHERE username=?", (u,))
    kalan = cursor.fetchone()['jeton']
    conn.close()

    return jsonify({"success": True, "kalan_bakiye": kalan})

@app.route('/siparislerim', methods=['POST'])
def siparislerim():
    data = request.json or {}
    u = data.get("username")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE username=? ORDER BY id DESC LIMIT 10", (u,))
    rows = cursor.fetchall()
    conn.close()
    orders = [{"id": r['id'], "market": r['market'], "items": r['items'], "status": r['status'], "date": r['created_at']} for r in rows]
    return jsonify({"orders": orders})

@app.route('/kilitle', methods=['POST'])
def kilitle():
    data = request.json or {}
    kilit = "1" if data.get("kilit", True) else "0"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value=? WHERE key='kilitli'", (kilit,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
                   
