# api/index.py — ИСПРАВЛЕННАЯ ВЕРСИЯ (без двойного JSON)
from flask import Flask, request, jsonify, Response
import os
import sys
import traceback
from datetime import datetime
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

logger.info("=" * 50)
logger.info("RentBot API starting...")

# DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL', '')
if 'channel_binding' in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split('&channel_binding')[0]

logger.info(f"DATABASE_URL exists: {bool(DATABASE_URL)}")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    logger.info(f"psycopg2: {psycopg2.__version__}")
except ImportError as e:
    logger.error(f"psycopg2 error: {e}")
    psycopg2 = None

def get_db():
    if not psycopg2:
        raise Exception("psycopg2 not installed")
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")
    
    conn = psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=10)
    conn.autocommit = False
    return conn

def seed_data(conn):
    c = conn.cursor()
    items = [
        ("Футбольный мяч", "футбол", 10, 10, 500, 2500),
        ("Теннисная ракетка", "теннис", 8, 8, 750, 4000),
        ("Баскетбольный мяч", "баскетбол", 6, 6, 500, 2500),
        ("Горный велосипед", "вело", 4, 4, 1500, 7500),
        ("Хоккейные коньки", "хоккей", 12, 12, 1000, 5000),
        ("Скейтборд", "скейт", 5, 5, 750, 3500),
        ("Роликовые коньки", "ролики", 15, 15, 750, 3500),
        ("Гантели 10 кг", "фитнес", 20, 20, 250, 1500),
    ]
    c.executemany(
        """INSERT INTO inventory (name, sport, total_quantity, available_quantity, price_per_hour, price_per_day) 
           VALUES (%s, %s, %s, %s, %s, %s) 
           ON CONFLICT (name) DO UPDATE SET 
           total_quantity = EXCLUDED.total_quantity,
           available_quantity = EXCLUDED.available_quantity,
           price_per_hour = EXCLUDED.price_per_hour,
           price_per_day = EXCLUDED.price_per_day""",
        items
    )
    conn.commit()
    logger.info(f"Seeded {len(items)} items")

def init_db():
    if not psycopg2:
        return False
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                sport TEXT NOT NULL,
                total_quantity INTEGER DEFAULT 0,
                available_quantity INTEGER DEFAULT 0,
                price_per_hour REAL DEFAULT 0,
                price_per_day REAL DEFAULT 0
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                item_id INTEGER REFERENCES inventory(id),
                quantity INTEGER DEFAULT 1,
                rent_type TEXT CHECK (rent_type IN ('hour', 'day')),
                booking_date TEXT,
                booking_time TEXT DEFAULT '00:00',
                duration INTEGER DEFAULT 1,
                return_datetime TEXT,
                total_price REAL DEFAULT 0,
                booked_at TEXT,
                reminder_sent INTEGER DEFAULT 0,
                returned INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        seed_data(conn)
        
        c.execute("SELECT COUNT(*) FROM inventory")
        count = c.fetchone()[0]
        logger.info(f"Total items: {count}")
        
        return True
    except Exception as e:
        logger.error(f"Init error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

init_db()

# HTML админка (упрощённая, надёжная)
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RentBot Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 16px; }
        .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; border: 1px solid #334155; }
        .btn { background: #7c3aed; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .btn:hover { background: #6d28d9; }
        .btn-secondary { background: #334155; }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .stat-value { font-size: 24px; font-weight: bold; color: #a78bfa; }
        .stat-label { font-size: 12px; color: #94a3b8; }
        .tabs { display: flex; gap: 8px; margin-bottom: 16px; background: #1e293b; padding: 4px; border-radius: 8px; }
        .tab { flex: 1; padding: 8px; text-align: center; border-radius: 6px; cursor: pointer; color: #94a3b8; }
        .tab.active { background: #7c3aed; color: white; }
        .item-name { font-weight: 600; color: white; }
        .item-sport { font-size: 12px; color: #a78bfa; text-transform: capitalize; }
        .price-tag { background: #0f172a; padding: 8px 12px; border-radius: 6px; text-align: center; }
        .price-label { font-size: 11px; color: #64748b; }
        .price-value { font-size: 14px; font-weight: 600; color: #34d399; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
        .status-online { background: #22c55e; }
        .status-offline { background: #ef4444; }
        #error { background: #ef4444; color: white; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; }
        .loading { text-align: center; padding: 40px; color: #64748b; }
    </style>
</head>
<body>
    <div id="error"></div>
    
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h1 style="margin: 0; color: #a78bfa;">RentBot Admin</h1>
        <div style="font-size: 12px; color: #94a3b8;">
            <span id="status-dot" class="status-dot status-offline"></span>
            <span id="status-text">Оффлайн</span>
        </div>
    </div>

    <div class="grid-2" id="stats">
        <div class="card">
            <div class="stat-label">Выручка</div>
            <div class="stat-value" id="revenue">0 ₸</div>
        </div>
        <div class="card">
            <div class="stat-label">Активные</div>
            <div class="stat-value" id="active">0</div>
        </div>
        <div class="card">
            <div class="stat-label">Просрочено</div>
            <div class="stat-value" id="overdue" style="color: #34d399;">0</div>
        </div>
        <div class="card">
            <div class="stat-label">Доступно</div>
            <div class="stat-value" id="available" style="color: #34d399;">0</div>
        </div>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="switchTab('bookings')">Брони</div>
        <div class="tab" onclick="switchTab('inventory')">Склад</div>
    </div>

    <div id="content">
        <div class="loading">Загрузка...</div>
    </div>

    <script>
        let currentTab = 'bookings';
        let data = { stats: {}, bookings: [], inventory: [] };

        function showError(msg) {
            const el = document.getElementById('error');
            el.textContent = msg;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }

        function setOnline(online) {
            const dot = document.getElementById('status-dot');
            const text = document.getElementById('status-text');
            if (online) {
                dot.className = 'status-dot status-online';
                text.textContent = 'Онлайн';
            } else {
                dot.className = 'status-dot status-offline';
                text.textContent = 'Оффлайн';
            }
        }

        async function loadData() {
            try {
                const [statsRes, bookingsRes, inventoryRes] = await Promise.all([
                    fetch('/api/stats'),
                    fetch('/api/bookings'),
                    fetch('/api/inventory')
                ]);

                if (!statsRes.ok) throw new Error('Stats failed: ' + await statsRes.text());
                if (!bookingsRes.ok) throw new Error('Bookings failed: ' + await bookingsRes.text());
                if (!inventoryRes.ok) throw new Error('Inventory failed: ' + await inventoryRes.text());

                // ВАЖНО: Парсим JSON один раз
                data.stats = await statsRes.json();
                data.bookings = await bookingsRes.json();
                data.inventory = await inventoryRes.json();

                // Проверяем что данные - объекты, не строки
                if (typeof data.stats === 'string') data.stats = JSON.parse(data.stats);
                if (typeof data.bookings === 'string') data.bookings = JSON.parse(data.bookings);
                if (typeof data.inventory === 'string') data.inventory = JSON.parse(data.inventory);

                updateUI();
                setOnline(true);
            } catch (e) {
                console.error('Load error:', e);
                showError('Ошибка загрузки: ' + e.message);
                setOnline(false);
            }
        }

        function updateUI() {
            // Stats
            document.getElementById('revenue').textContent = (data.stats.total_revenue || 0).toLocaleString() + ' ₸';
            document.getElementById('active').textContent = data.stats.active_bookings || 0;
            document.getElementById('overdue').textContent = data.stats.overdue_bookings || 0;
            document.getElementById('overdue').style.color = (data.stats.overdue_bookings > 0) ? '#ef4444' : '#34d399';
            document.getElementById('available').textContent = data.stats.available_items || 0;

            // Content
            const content = document.getElementById('content');
            if (currentTab === 'inventory') {
                renderInventory(content);
            } else {
                renderBookings(content);
            }
        }

        function renderInventory(container) {
            if (!data.inventory || data.inventory.length === 0) {
                container.innerHTML = '<div class="loading">Нет товаров</div>';
                return;
            }
            
            container.innerHTML = data.inventory.map(item => `
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                        <div>
                            <div class="item-name">${escapeHtml(item.name)}</div>
                            <div class="item-sport">${escapeHtml(item.sport)}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 20px; font-weight: bold; color: ${item.available_quantity > 0 ? '#34d399' : '#ef4444'};">
                                ${item.available_quantity}<span style="color: #64748b; font-size: 14px;">/${item.total_quantity}</span>
                            </div>
                            <div style="font-size: 11px; color: #64748b;">доступно</div>
                        </div>
                    </div>
                    <div class="grid-2">
                        <div class="price-tag">
                            <div class="price-label">Час</div>
                            <div class="price-value">${item.price_per_hour.toLocaleString()} ₸</div>
                        </div>
                        <div class="price-tag">
                            <div class="price-label">День</div>
                            <div class="price-value">${item.price_per_day.toLocaleString()} ₸</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function renderBookings(container) {
            const active = data.bookings.filter(b => !b.returned);
            if (active.length === 0) {
                container.innerHTML = '<div class="loading">Нет активных бронирований</div>';
                return;
            }
            
            container.innerHTML = active.map(b => {
                const isOverdue = new Date(b.return_datetime) < new Date() && !b.returned;
                return `
                <div class="card" style="${isOverdue ? 'border-color: #ef4444; background: rgba(239, 68, 68, 0.1);' : ''}">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <div>
                            <div class="item-name">${escapeHtml(b.item_name)}</div>
                            <div style="font-size: 12px; color: #64748b;">ID: ${b.user_id}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="color: #34d399; font-weight: bold;">${b.total_price.toLocaleString()} ₸</div>
                            <div style="font-size: 12px; color: #64748b;">${b.quantity} шт.</div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">
                        ${b.booking_date} ${b.booking_time} • ${b.duration} ${b.rent_type === 'hour' ? 'ч.' : 'дн.'}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="font-size: 12px; ${isOverdue ? 'color: #ef4444; font-weight: bold;' : 'color: #64748b;'}">
                            ${isOverdue ? '⚠️ ' : ''}Возврат: ${formatDate(b.return_datetime)}
                        </div>
                        <button class="btn" onclick="returnBooking(${b.id})" style="font-size: 12px; padding: 6px 12px;">Вернуть</button>
                    </div>
                </div>
                `;
            }).join('');
        }

        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            updateUI();
        }

        async function returnBooking(id) {
            if (!confirm('Подтвердить возврат?')) return;
            try {
                const res = await fetch(`/api/bookings/${id}/return`, { method: 'POST' });
                if (!res.ok) throw new Error(await res.text());
                await loadData();
            } catch (e) {
                showError('Ошибка возврата: ' + e.message);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatDate(dt) {
            const d = new Date(dt);
            return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
        }

        // Load and refresh
        loadData();
        setInterval(loadData, 10000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return HTML_PAGE

@app.route('/api/stats')
def get_stats():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*), COALESCE(SUM(available_quantity), 0) FROM inventory")
        total_items, available = c.fetchone()
        
        c.execute("SELECT COUNT(*), COALESCE(SUM(total_price), 0) FROM bookings WHERE returned = 0")
        active, revenue = c.fetchone()
        
        now = datetime.now().isoformat()
        c.execute("SELECT COUNT(*) FROM bookings WHERE returned = 0 AND return_datetime < %s", (now,))
        overdue = c.fetchone()[0]
        
        result = {
            "total_items": total_items or 0,
            "active_bookings": active or 0,
            "total_revenue": float(revenue or 0),
            "available_items": int(available or 0),
            "overdue_bookings": overdue or 0
        }
        
        # ВАЖНО: Возвращаем чистый JSON без обёртки
        return Response(json.dumps(result), mimetype='application/json')
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/bookings')
def get_bookings():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT b.*, i.name as item_name 
            FROM bookings b 
            JOIN inventory i ON b.item_id = i.id 
            ORDER BY b.booked_at DESC NULLS LAST
        """)
        rows = c.fetchall()
        result = [dict(r) for r in rows]
        return Response(json.dumps(result), mimetype='application/json')
    except Exception as e:
        logger.error(f"Bookings error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/inventory')
def get_inventory():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM inventory ORDER BY id")
        rows = c.fetchall()
        result = [dict(r) for r in rows]
        return Response(json.dumps(result), mimetype='application/json')
    except Exception as e:
        logger.error(f"Inventory error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/bookings/<int:booking_id>/return', methods=['POST'])
def return_booking(booking_id):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT item_id, quantity FROM bookings WHERE id = %s AND returned = 0", (booking_id,))
        r = c.fetchone()
        if not r:
            return Response(json.dumps({"error": "Not found"}), status=404, mimetype='application/json')
        
        c.execute("UPDATE inventory SET available_quantity = available_quantity + %s WHERE id = %s", (r['quantity'], r['item_id']))
        c.execute("UPDATE bookings SET returned = 1 WHERE id = %s", (booking_id,))
        conn.commit()
        
        return Response(json.dumps({"ok": True}), mimetype='application/json')
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Return error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/health')
def health():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT 1")
        conn.close()
        return Response(json.dumps({"status": "ok", "database": "connected"}), mimetype='application/json')
    except Exception as e:
        return Response(json.dumps({"status": "error", "database": str(e)}), status=500, mimetype='application/json')

@app.route('/api/seed', methods=['POST'])
def force_seed():
    try:
        conn = get_db()
        seed_data(conn)
        conn.close()
        return Response(json.dumps({"ok": True}), mimetype='application/json')
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')
