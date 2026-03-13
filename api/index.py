# api/index.py — ИСПРАВЛЕННАЯ ВЕРСИЯ
from flask import Flask, request, Response
import os
import json
import logging
from datetime import datetime, date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Берём из переменных окружения (должны быть настроены в Vercel!)
DATABASE_URL = os.getenv('DATABASE_URL', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Убираем channel_binding если есть
if 'channel_binding' in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split('&channel_binding')[0]

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:
    logger.error(f"psycopg2 error: {e}")
    psycopg2 = None

class DateTimeEncoder(json.JSONEncoder):
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
    return json.dumps(data, cls=DateTimeEncoder, ensure_ascii=False)

def init_db():
    if not psycopg2 or not DATABASE_URL:
        logger.error("DB not initialized: psycopg2 or DATABASE_URL missing")
        return False
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Таблица inventory
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
        
        # Начальные данные
        items = [
            (1, "Футбольный мяч", "футбол", 10, 10, 500, 2500),
            (2, "Теннисная ракетка", "теннис", 8, 8, 750, 4000),
            (3, "Баскетбольный мяч", "баскетбол", 6, 6, 500, 2500),
            (4, "Горный велосипед", "вело", 4, 4, 1500, 7500),
            (5, "Хоккейные коньки", "хоккей", 12, 12, 1000, 5000),
            (6, "Скейтборд", "скейт", 5, 5, 750, 3500),
            (7, "Роликовые коньки", "ролики", 15, 15, 750, 3500),
            (8, "Гантели 10 кг", "фитнес", 20, 20, 250, 1500),
        ]
        
        for item in items:
            c.execute('''
                INSERT INTO inventory (id, name, sport, total_quantity, available_quantity, price_per_hour, price_per_day)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    sport = EXCLUDED.sport,
                    total_quantity = EXCLUDED.total_quantity,
                    available_quantity = EXCLUDED.available_quantity,
                    price_per_hour = EXCLUDED.price_per_hour,
                    price_per_day = EXCLUDED.price_per_day
            ''', item)
        
        conn.commit()
        logger.info("DB initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Init error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# Инициализация при старте
init_db()

# ============ HTML ============
HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Мои брони</title>
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); 
            color: #e2e8f0; 
            margin: 0; 
            padding: 16px; 
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }
        .card { 
            background: rgba(30, 41, 59, 0.8); 
            backdrop-filter: blur(10px);
            border-radius: 16px; 
            padding: 20px; 
            margin-bottom: 16px; 
            border: 1px solid rgba(148, 163, 184, 0.1);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2); }
        .btn { 
            background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%); 
            color: white; 
            border: none; 
            padding: 12px 24px; 
            border-radius: 12px; 
            cursor: pointer; 
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s;
            box-shadow: 0 4px 6px -1px rgba(124, 58, 237, 0.3);
        }
        .btn:hover { 
            background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
            transform: translateY(-1px);
            box-shadow: 0 6px 8px -1px rgba(124, 58, 237, 0.4);
        }
        .btn:active { transform: translateY(0); }
        .btn-secondary { 
            background: rgba(51, 65, 85, 0.8); 
            box-shadow: none;
        }
        .btn-secondary:hover { background: rgba(71, 85, 105, 0.9); }
        .item-name { font-weight: 700; color: white; font-size: 17px; letter-spacing: -0.01em; }
        .price { 
            color: #34d399; 
            font-weight: 800; 
            font-size: 18px;
            text-shadow: 0 2px 4px rgba(52, 211, 153, 0.2);
        }
        .overdue { 
            border-color: #ef4444 !important; 
            background: rgba(239, 68, 68, 0.15) !important;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
            50% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
        }
        .tabs { 
            display: flex; 
            gap: 8px; 
            margin-bottom: 20px; 
            background: rgba(30, 41, 59, 0.6); 
            padding: 6px; 
            border-radius: 12px;
            backdrop-filter: blur(10px);
        }
        .tab { 
            flex: 1; 
            padding: 12px; 
            text-align: center; 
            border-radius: 10px; 
            cursor: pointer; 
            color: #94a3b8;
            font-weight: 500;
            transition: all 0.2s;
        }
        .tab:hover { color: #e2e8f0; }
        .tab.active { 
            background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%); 
            color: white;
            box-shadow: 0 4px 6px -1px rgba(124, 58, 237, 0.3);
        }
        .empty { 
            text-align: center; 
            padding: 60px 20px; 
            color: #64748b;
            font-size: 16px;
        }
        .empty-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.5; }
        .error { 
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); 
            color: white; 
            padding: 16px; 
            border-radius: 12px; 
            margin-bottom: 20px;
            box-shadow: 0 4px 6px -1px rgba(239, 68, 68, 0.3);
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .user-info { 
            background: rgba(30, 41, 59, 0.6); 
            padding: 14px 18px; 
            border-radius: 12px; 
            margin-bottom: 20px; 
            font-size: 14px; 
            color: #94a3b8;
            display: flex;
            align-items: center;
            gap: 10px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(148, 163, 184, 0.1);
        }
        .catalog-btn { 
            background: linear-gradient(135deg, #334155 0%, #1e293b 100%); 
            color: white; 
            padding: 18px; 
            border-radius: 16px; 
            text-align: center; 
            margin-bottom: 20px; 
            cursor: pointer; 
            font-weight: 600;
            font-size: 16px;
            border: 1px solid rgba(148, 163, 184, 0.2);
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .catalog-btn:hover { 
            background: linear-gradient(135deg, #475569 0%, #334155 100%);
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
        }
        #catalog-modal { 
            display: none; 
            position: fixed; 
            top: 0; 
            left: 0; 
            right: 0; 
            bottom: 0; 
            background: rgba(15, 23, 42, 0.98); 
            z-index: 1000; 
            overflow-y: auto; 
            padding: 20px;
            backdrop-filter: blur(20px);
        }
        .modal-header { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 24px; 
            position: sticky; 
            top: 0; 
            background: rgba(15, 23, 42, 0.95); 
            padding: 16px 0;
            backdrop-filter: blur(10px);
            z-index: 10;
        }
        .close-btn { 
            background: rgba(51, 65, 85, 0.8); 
            color: white; 
            border: none; 
            padding: 12px 20px; 
            border-radius: 12px; 
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }
        .close-btn:hover { background: rgba(71, 85, 105, 0.9); }
        .inventory-item { margin-bottom: 16px; }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .badge-sport { background: rgba(167, 139, 250, 0.2); color: #a78bfa; }
        .badge-available { background: rgba(52, 211, 153, 0.2); color: #34d399; }
        .badge-unavailable { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .skeleton {
            background: linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
            border-radius: 12px;
            height: 100px;
            margin-bottom: 16px;
        }
        @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        .toast {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: rgba(30, 41, 59, 0.95);
            color: white;
            padding: 16px 24px;
            border-radius: 12px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
            z-index: 2000;
            opacity: 0;
            transition: all 0.3s;
            border: 1px solid rgba(148, 163, 184, 0.2);
            backdrop-filter: blur(10px);
        }
        .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
        .toast.success { border-left: 4px solid #34d399; }
        .toast.error { border-left: 4px solid #ef4444; }
        .loading-spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        h1 { color: #a78bfa; margin: 0 0 24px 0; font-size: 28px; font-weight: 800; letter-spacing: -0.02em; }
        h2 { color: #a78bfa; margin: 0; font-size: 24px; font-weight: 700; }
        .status-text { font-size: 13px; font-weight: 500; }
        .return-btn { font-size: 13px; padding: 8px 16px; }
        .date-text { font-size: 13px; color: #64748b; margin-top: 4px; }
        .quantity-badge {
            background: rgba(51, 65, 85, 0.6);
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 12px;
            color: #94a3b8;
        }
    </style>
</head>
<body>
    <div id="error" class="error" style="display: none;">
        <span>⚠️</span>
        <span id="error-text"></span>
    </div>
    
    <div class="user-info">
        <span>👤</span>
        <span>ID: <span id="user-id" style="color: #e2e8f0; font-weight: 600;">-</span></span>
    </div>
    
    <h1>Мои брони</h1>

    <div class="catalog-btn" onclick="openCatalog()">
        <span>📦</span>
        <span>Каталог товаров</span>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="switchTab('active')">Активные</div>
        <div class="tab" onclick="switchTab('history')">История</div>
    </div>

    <div id="content">
        <div class="skeleton"></div>
        <div class="skeleton"></div>
    </div>

    <div id="catalog-modal">
        <div class="modal-header">
            <h2>Каталог</h2>
            <button class="close-btn" onclick="closeCatalog()">✕ Закрыть</button>
        </div>
        <div id="catalog-list">
            <div class="skeleton"></div>
            <div class="skeleton"></div>
            <div class="skeleton"></div>
        </div>
    </div>

    <div id="toast" class="toast"></div>

    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const userId = urlParams.get('user_id');
        document.getElementById('user-id').textContent = userId || 'не указан';
        
        if (!userId) {
            showError('Ошибка: откройте через бота (не передан user_id)');
        }

        let currentTab = 'active';
        let myBookings = [];
        let isLoading = false;

        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast ' + type;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }

        function showError(msg) {
            const el = document.getElementById('error');
            document.getElementById('error-text').textContent = msg;
            el.style.display = 'flex';
            setTimeout(() => el.style.display = 'none', 5000);
        }

        async function loadBookings() {
            if (!userId || isLoading) return;
            isLoading = true;
            
            try {
                const res = await fetch('/api/my-bookings?user_id=' + userId);
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.error || 'Ошибка загрузки');
                }
                const data = await res.json();
                myBookings = Array.isArray(data) ? data : [];
                renderBookings();
            } catch (e) {
                showError('Ошибка: ' + e.message);
                document.getElementById('content').innerHTML = '<div class="empty"><div class="empty-icon">😕</div>Не удалось загрузить брони</div>';
            } finally {
                isLoading = false;
            }
        }

        function renderBookings() {
            const container = document.getElementById('content');
            const filtered = myBookings.filter(b => currentTab === 'active' ? !b.returned : b.returned);

            if (filtered.length === 0) {
                container.innerHTML = '<div class="empty"><div class="empty-icon">' + 
                    (currentTab === 'active' ? '📭' : '📋') + 
                    '</div>Нет ' + (currentTab === 'active' ? 'активных броней' : 'завершенных броней') + '</div>';
                return;
            }

            container.innerHTML = filtered.map(b => {
                const isOverdue = !b.returned && new Date(b.return_datetime) < new Date();
                const returnDate = new Date(b.return_datetime);
                const isToday = new Date().toDateString() === returnDate.toDateString();
                
                return '<div class="card ' + (isOverdue ? 'overdue' : '') + '">' +
                    '<div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">' +
                        '<div style="flex: 1;">' +
                            '<div class="item-name">' + escapeHtml(b.item_name) + '</div>' +
                            '<div style="margin-top: 6px;">' +
                                '<span class="quantity-badge">' + b.quantity + ' шт.</span>' +
                                '<span class="quantity-badge" style="margin-left: 6px;">' + b.duration + ' ' + (b.rent_type === 'hour' ? 'час' : 'дн.') + '</span>' +
                            '</div>' +
                        '</div>' +
                        '<div class="price">' + Math.round(b.total_price).toLocaleString() + ' ₸</div>' +
                    '</div>' +
                    '<div class="date-text">📅 ' + formatDate(b.booking_date) + ' в ' + b.booking_time + '</div>' +
                    '<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(148, 163, 184, 0.1);">' +
                        '<div class="status-text" style="' + (isOverdue ? 'color: #ef4444;' : b.returned ? 'color: #34d399;' : 'color: #94a3b8;') + '">' +
                            (isOverdue ? '⚠️ Просрочено! Верните срочно' : 
                             b.returned ? '✅ Возвращено' : 
                             isToday ? '🕐 Вернуть сегодня' : 
                             '📦 Вернуть: ' + formatDateTime(b.return_datetime)) +
                        '</div>' +
                        (!b.returned ? '<button class="btn return-btn" onclick="returnItem(' + b.id + ', this)">Вернуть</button>' : '') +
                    '</div>' +
                '</div>';
            }).join('');
        }

        async function openCatalog() {
            const modal = document.getElementById('catalog-modal');
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
            
            try {
                const res = await fetch('/api/inventory');
                if (!res.ok) throw new Error('Ошибка загрузки');
                const items = await res.json();
                const container = document.getElementById('catalog-list');
                
                if (items.length === 0) {
                    container.innerHTML = '<div class="empty"><div class="empty-icon">📭</div>Каталог пуст</div>';
                    return;
                }
                
                container.innerHTML = items.map(item => {
                    const isAvailable = item.available_quantity > 0;
                    return '<div class="card inventory-item">' +
                        '<div style="display: flex; justify-content: space-between; align-items: start;">' +
                            '<div style="flex: 1;">' +
                                '<div class="item-name">' + escapeHtml(item.name) + '</div>' +
                                '<div style="margin: 8px 0;">' +
                                    '<span class="badge badge-sport">' + item.sport + '</span>' +
                                '</div>' +
                                '<div style="font-size: 15px; color: #34d399; font-weight: 600;">' + 
                                    Math.round(item.price_per_hour).toLocaleString() + ' ₸/час • ' + 
                                    Math.round(item.price_per_day).toLocaleString() + ' ₸/день' +
                                '</div>' +
                            '</div>' +
                            '<div style="text-align: right;">' +
                                '<div style="font-size: 28px; font-weight: 800; color: ' + (isAvailable ? '#34d399' : '#ef4444') + ';">' + item.available_quantity + '</div>' +
                                '<div style="font-size: 12px; color: #64748b; margin-top: 4px;">из ' + item.total_quantity + '</div>' +
                                '<span class="badge ' + (isAvailable ? 'badge-available' : 'badge-unavailable') + '" style="margin-top: 8px;">' + 
                                    (isAvailable ? 'В наличии' : 'Нет в наличии') + 
                                '</span>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');
            } catch (e) {
                document.getElementById('catalog-list').innerHTML = '<div class="error">Ошибка загрузки каталога</div>';
            }
        }

        function closeCatalog() {
            document.getElementById('catalog-modal').style.display = 'none';
            document.body.style.overflow = 'auto';
        }

        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            renderBookings();
        }

        async function returnItem(bookingId, btn) {
            if (!confirm('Подтвердите возврат товара')) return;
            
            const originalText = btn.textContent;
            btn.innerHTML = '<span class="loading-spinner"></span>';
            btn.disabled = true;
            
            try {
                const res = await fetch('/api/my-bookings/' + bookingId + '/return?user_id=' + userId, { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.error || 'Ошибка возврата');
                }
                
                showToast('✅ Товар успешно возвращен!');
                await loadBookings();
            } catch (e) {
                showToast('❌ ' + e.message, 'error');
                btn.textContent = originalText;
                btn.disabled = false;
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
                return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
            } catch(e) { return dt; }
        }

        function formatDateTime(dt) {
            if (!dt) return '-';
            try {
                const d = new Date(dt);
                return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
            } catch(e) { return dt; }
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeCatalog();
        });

        let touchStartY = 0;
        document.addEventListener('touchstart', e => touchStartY = e.touches[0].clientY);
        document.addEventListener('touchend', e => {
            const touchEndY = e.changedTouches[0].clientY;
            if (touchEndY - touchStartY > 100 && window.scrollY === 0) {
                loadBookings();
                showToast('🔄 Обновлено');
            }
        });

        loadBookings();
        setInterval(loadBookings, 30000);
    </script>
</body>
</html>"""

# ============ ROUTES ============

@app.route('/')
def index():
    return HTML_PAGE

@app.route('/api/my-bookings')
def get_my_bookings():
    user_id = request.args.get('user_id', type=int)
    # ИСПРАВЛЕНО: было if not userId (опечатка)
    if not user_id:
        return Response(to_json({"error": "user_id required"}), status=401, mimetype='application/json')
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        # ИСПРАВЛЕНО: убран i.image_url
        c.execute("""
            SELECT b.*, i.name as item_name 
            FROM bookings b 
            LEFT JOIN inventory i ON b.item_id = i.id 
            WHERE b.user_id = %s
            ORDER BY b.id DESC
        """, (user_id,))
        rows = c.fetchall()
        
        result = []
        for row in rows:
            item = dict(row)
            for key, value in item.items():
                if isinstance(value, (datetime, date)):
                    item[key] = value.isoformat()
            result.append(item)
        
        return Response(to_json(result), mimetype='application/json')
    except Exception as e:
        logger.error(f"My bookings error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/my-bookings/<int:booking_id>/return', methods=['POST'])
def return_my_booking(booking_id):
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return Response(to_json({"error": "user_id required"}), status=401, mimetype='application/json')
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT item_id, quantity, returned FROM bookings WHERE id = %s AND user_id = %s", 
                 (booking_id, user_id))
        booking = c.fetchone()
        
        if not booking:
            return Response(to_json({"error": "Бронь не найдена"}), status=404, mimetype='application/json')
        
        if booking[2]:
            return Response(to_json({"error": "Уже возвращена"}), status=400, mimetype='application/json')
        
        c.execute("UPDATE inventory SET available_quantity = available_quantity + %s WHERE id = %s",
                 (booking[1], booking[0]))
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

@app.route('/api/inventory')
def get_inventory():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT * FROM inventory ORDER BY id")
        rows = c.fetchall()
        
        result = []
        for row in rows:
            item = dict(row)
            for key, value in item.items():
                if isinstance(value, (datetime, date)):
                    item[key] = value.isoformat()
            result.append(item)
        
        return Response(to_json(result), mimetype='application/json')
    except Exception as e:
        logger.error(f"Inventory error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

# ============ ADMIN API ============

@app.route('/api/admin/bookings')
def get_admin_bookings():
    admin_id = request.args.get('admin_id', type=int)
    if admin_id != ADMIN_ID:
        return Response(to_json({"error": "Forbidden"}), status=403, mimetype='application/json')
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        # ИСПРАВЛЕНО: убран i.image_url
        c.execute("""
            SELECT b.*, i.name as item_name 
            FROM bookings b 
            LEFT JOIN inventory i ON b.item_id = i.id 
            ORDER BY b.id DESC
        """)
        rows = c.fetchall()
        
        result = []
        for row in rows:
            item = dict(row)
            for key, value in item.items():
                if isinstance(value, (datetime, date)):
                    item[key] = value.isoformat()
            result.append(item)
        
        return Response(to_json(result), mimetype='application/json')
    except Exception as e:
        logger.error(f"Admin bookings error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/admin/stats')
def get_admin_stats():
    admin_id = request.args.get('admin_id', type=int)
    if admin_id != ADMIN_ID:
        return Response(to_json({"error": "Forbidden"}), status=403, mimetype='application/json')
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM bookings WHERE returned = 0")
        active = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM bookings WHERE returned = 1")
        returned = c.fetchone()[0]
        
        c.execute("SELECT COALESCE(SUM(total_price), 0) FROM bookings")
        revenue = c.fetchone()[0]
        
        return Response(to_json({
            "active_bookings": active,
            "returned_bookings": returned,
            "total_revenue": revenue
        }), mimetype='application/json')
        
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/health')
def health():
    return Response(to_json({"status": "ok", "database": "connected" if DATABASE_URL else "not configured"}), mimetype='application/json')
