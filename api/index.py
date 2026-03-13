# api/index.py — РАБОЧАЯ ВЕРСИЯ с JSON сериализацией
from flask import Flask, request, Response
import os
import sys
import json
import logging
from datetime import datetime, date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL', '')
if 'channel_binding' in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split('&channel_binding')[0]

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:
    logger.error(f"psycopg2 error: {e}")
    psycopg2 = None

class DateTimeEncoder(json.JSONEncoder):
    """Кастомный JSON encoder для datetime"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

def get_db():
    if not psycopg2:
        raise Exception("psycopg2 not installed")
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=10)

def to_json(data):
    """Безопасная сериализация в JSON"""
    return json.dumps(data, cls=DateTimeEncoder, ensure_ascii=False)

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
                item_id INTEGER REFERENCES inventory(id) ON DELETE CASCADE,
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
        
        # Заполняем данные
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
        
        for item in items:
            c.execute('''
                INSERT INTO inventory (name, sport, total_quantity, available_quantity, price_per_hour, price_per_day)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    total_quantity = EXCLUDED.total_quantity,
                    available_quantity = EXCLUDED.available_quantity,
                    price_per_hour = EXCLUDED.price_per_hour,
                    price_per_day = EXCLUDED.price_per_day
            ''', item)
        
        conn.commit()
        logger.info("DB initialized")
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

# HTML админка (та же)
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
            console.error(msg);
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
                console.log('Loading...');
                const [statsRes, bookingsRes, inventoryRes] = await Promise.all([
                    fetch('/api/stats'),
                    fetch('/api/bookings'),
                    fetch('/api/inventory')
                ]);

                console.log('Status:', statsRes.status, bookingsRes.status, inventoryRes.status);

                if (!statsRes.ok) throw new Error('Stats: ' + await statsRes.text());
                if (!bookingsRes.ok) throw new Error('Bookings: ' + await bookingsRes.text());
                if (!inventoryRes.ok) throw new Error('Inventory: ' + await inventoryRes.text());

                data.stats = await statsRes.json();
                data.bookings = await bookingsRes.json();
                data.inventory = await inventoryRes.json();

                console.log('Loaded:', data.inventory.length, 'items');
                updateUI();
                setOnline(true);
            } catch (e) {
                console.error('Error:', e);
                showError('Ошибка: ' + e.message);
                setOnline(false);
            }
        }

        function updateUI() {
            document.getElementById('revenue').textContent = (data.stats.total_revenue || 0).toLocaleString() + ' ₸';
            document.getElementById('active').textContent = data.stats.active_bookings || 0;
            document.getElementById('overdue').textContent = data.stats.overdue_bookings || 0;
            document.getElementById('overdue').style.color = (data.stats.overdue_bookings > 0) ? '#ef4444' : '#34d399';
            document.getElementById('available').textContent = data.stats.available_items || 0;

            const content = document.getElementById('content');
            if (currentTab === 'inventory') renderInventory(content);
            else renderBookings(content);
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
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatDate(dt) {
            if (!dt) return '-';
            try {
                const d = new Date(dt);
                return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
            } catch(e) {
                return dt;
            }
        }

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
        c = conn.cursor(cursor_factory=RealDictCursor)
        
        c.execute("SELECT COUNT(*) as count, COALESCE(SUM(available_quantity), 0) as avail FROM inventory")
        r = c.fetchone()
        
        c.execute("SELECT COUNT(*) as count, COALESCE(SUM(total_price), 0) as rev FROM bookings WHERE returned = 0")
        r2 = c.fetchone()
        
        now = datetime.now().isoformat()
        c.execute("SELECT COUNT(*) as count FROM bookings WHERE returned = 0 AND return_datetime < %s", (now,))
        r3 = c.fetchone()
        
        result = {
            "total_items": r['count'] if r else 0,
            "active_bookings": r2['count'] if r2 else 0,
            "total_revenue": float(r2['rev'] if r2 else 0),
            "available_items": int(r['avail'] if r else 0),
            "overdue_bookings": r3['count'] if r3 else 0
        }
        
        return Response(to_json(result), mimetype='application/json')
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/bookings')
def get_bookings():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("""
            SELECT b.*, i.name as item_name 
            FROM bookings b 
            LEFT JOIN inventory i ON b.item_id = i.id 
            ORDER BY b.id DESC
        """)
        rows = c.fetchall()
        # Конвертируем в обычные dict
        result = []
        for row in rows:
            item = dict(row)
            # Конвертируем все datetime в строки
            for key, value in item.items():
                if isinstance(value, (datetime, date)):
                    item[key] = value.isoformat()
            result.append(item)
        
        return Response(to_json(result), mimetype='application/json')
    except Exception as e:
        logger.error(f"Bookings error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/inventory')
def get_inventory():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT * FROM inventory ORDER BY id")
        rows = c.fetchall()
        
        # Конвертируем в обычные dict
        result = []
        for row in rows:
            item = dict(row)
            # Конвертируем все datetime в строки
            for key, value in item.items():
                if isinstance(value, (datetime, date)):
                    item[key] = value.isoformat()
            result.append(item)
        
        logger.info(f"Inventory: {len(result)} items")
        return Response(to_json(result), mimetype='application/json')
    except Exception as e:
        logger.error(f"Inventory error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/bookings/<int:booking_id>/return', methods=['POST'])
def return_booking(booking_id):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        
        c.execute("SELECT item_id, quantity FROM bookings WHERE id = %s AND returned = 0", (booking_id,))
        r = c.fetchone()
        if not r:
            return Response(to_json({"error": "Not found"}), status=404, mimetype='application/json')
        
        c.execute("UPDATE inventory SET available_quantity = available_quantity + %s WHERE id = %s", (r['quantity'], r['item_id']))
        c.execute("UPDATE bookings SET returned = 1 WHERE id = %s", (booking_id,))
        conn.commit()
        
        return Response(to_json({"ok": True}), mimetype='application/json')
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Return error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
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
        return Response(to_json({"status": "ok", "database": "connected"}), mimetype='application/json')
    except Exception as e:
        return Response(to_json({"status": "error", "database": str(e)}), status=500, mimetype='application/json')

@app.route('/api/init', methods=['POST'])
def force_init():
    success = init_db()
    return Response(to_json({"success": success}), mimetype='application/json')
