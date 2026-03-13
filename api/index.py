# api/index.py — Исправленная версия для Vercel
from flask import Flask, request, Response
import os
import json
import logging
from datetime import datetime, date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Получаем URL из Environment Variables (без channel_binding!)
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
    if not psycopg2:
        return False
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Создаём таблицу inventory (если нет)
        c.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                sport TEXT NOT NULL,
                total_quantity INTEGER DEFAULT 0,
                available_quantity INTEGER DEFAULT 0,
                price_per_hour REAL DEFAULT 0,
                price_per_day REAL DEFAULT 0,
                image_url TEXT DEFAULT ''
            )
        ''')
        
        # ДОБАВЛЯЕМ: проверяем и добавляем колонку image_url если её нет
        try:
            c.execute("SELECT image_url FROM inventory LIMIT 1")
        except:
            c.execute("ALTER TABLE inventory ADD COLUMN image_url TEXT DEFAULT ''")
            logger.info("Added image_url column")
        
        # Создаём таблицу bookings
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
        
        # Заполняем данные с фото
        items = [
            (1, "Футбольный мяч", "футбол", 10, 10, 500, 2500, "https://images.unsplash.com/photo-1614632537190-23e4146777db?w=400"),
            (2, "Теннисная ракетка", "теннис", 8, 8, 750, 4000, "https://images.unsplash.com/photo-1622279457486-62dcc4a431d6?w=400"),
            (3, "Баскетбольный мяч", "баскетбол", 6, 6, 500, 2500, "https://images.unsplash.com/photo-1519861531473-9200262188bf?w=400"),
            (4, "Горный велосипед", "вело", 4, 4, 1500, 7500, "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=400"),
            (5, "Хоккейные коньки", "хоккей", 12, 12, 1000, 5000, "https://images.unsplash.com/photo-1565992441121-4367c2967103?w=400"),
            (6, "Скейтборд", "скейт", 5, 5, 750, 3500, "https://images.unsplash.com/photo-1520045892732-304bc3ac5d8e?w=400"),
            (7, "Роликовые коньки", "ролики", 15, 15, 750, 3500, "https://images.unsplash.com/photo-1566796195789-d5a59f97235b?w=400"),
            (8, "Гантели 10 кг", "фитнес", 20, 20, 250, 1500, "https://images.unsplash.com/photo-1583454110551-21f2fa2afe61?w=400"),
        ]
        
        for item in items:
            c.execute('''
                INSERT INTO inventory (id, name, sport, total_quantity, available_quantity, price_per_hour, price_per_day, image_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    sport = EXCLUDED.sport,
                    total_quantity = EXCLUDED.total_quantity,
                    available_quantity = EXCLUDED.available_quantity,
                    price_per_hour = EXCLUDED.price_per_hour,
                    price_per_day = EXCLUDED.price_per_day,
                    image_url = EXCLUDED.image_url
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

# ============ HTML СТРАНИЦЫ ============

USER_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Мои брони</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 16px; min-height: 100vh; }
        .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; border: 1px solid #334155; }
        .btn { background: #7c3aed; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .btn:hover { background: #6d28d9; }
        .btn-secondary { background: #334155; }
        .btn-secondary:hover { background: #475569; }
        .item-name { font-weight: 600; color: white; font-size: 16px; }
        .price { color: #34d399; font-weight: bold; }
        .overdue { border-color: #ef4444 !important; background: rgba(239, 68, 68, 0.1) !important; }
        .tabs { display: flex; gap: 8px; margin-bottom: 16px; background: #1e293b; padding: 4px; border-radius: 8px; }
        .tab { flex: 1; padding: 10px; text-align: center; border-radius: 6px; cursor: pointer; color: #94a3b8; font-size: 14px; }
        .tab.active { background: #7c3aed; color: white; }
        .empty { text-align: center; padding: 40px; color: #64748b; }
        .error { background: #ef4444; color: white; padding: 12px; border-radius: 8px; margin-bottom: 16px; }
        .user-info { background: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; color: #94a3b8; }
        .catalog-btn { background: #334155; color: white; padding: 14px; border-radius: 8px; text-align: center; margin-bottom: 16px; cursor: pointer; font-weight: 500; }
        .catalog-btn:hover { background: #475569; }
        #catalog-modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: #0f172a; z-index: 1000; overflow-y: auto; padding: 16px; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; position: sticky; top: 0; background: #0f172a; padding: 10px 0; }
        .close-btn { background: #334155; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .inventory-item { display: flex; gap: 16px; align-items: center; margin-bottom: 12px; }
        .inventory-img { width: 80px; height: 80px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
        .returned { opacity: 0.6; }
    </style>
</head>
<body>
    <div id="error" class="error" style="display: none;"></div>
    
    <div class="user-info">
        👤 ID: <span id="user-id">-</span>
    </div>

    <h1 style="color: #a78bfa; margin: 0 0 20px 0; font-size: 24px;">Мои брони</h1>

    <div class="catalog-btn" onclick="openCatalog()">
        📦 Каталог товаров
    </div>

    <div class="tabs">
        <div class="tab active" onclick="switchTab('active')">Активные</div>
        <div class="tab" onclick="switchTab('history')">История</div>
    </div>

    <div id="content">
        <div style="text-align: center; padding: 40px; color: #64748b;">Загрузка...</div>
    </div>

    <div id="catalog-modal">
        <div class="modal-header">
            <h2 style="color: #a78bfa; margin: 0;">Каталог</h2>
            <button class="close-btn" onclick="closeCatalog()">✕ Закрыть</button>
        </div>
        <div id="catalog-list"></div>
    </div>

    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const userId = urlParams.get('user_id');
        document.getElementById('user-id').textContent = userId || 'не указан';
        
        if (!userId) {
            document.getElementById('error').style.display = 'block';
            document.getElementById('error').textContent = 'Ошибка: откройте через бота';
        }

        let currentTab = 'active';
        let myBookings = [];

        function showError(msg) {
            const el = document.getElementById('error');
            el.textContent = msg;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }

        async function loadBookings() {
            if (!userId) return;
            try {
                const res = await fetch('/api/my-bookings?user_id=' + userId);
                if (!res.ok) throw new Error(await res.text());
                const data = await res.json();
                myBookings = Array.isArray(data) ? data : [];
                renderBookings();
            } catch (e) {
                showError('Ошибка: ' + e.message);
            }
        }

        function renderBookings() {
            const container = document.getElementById('content');
            const filtered = myBookings.filter(b => currentTab === 'active' ? !b.returned : b.returned);

            if (filtered.length === 0) {
                container.innerHTML = '<div class="empty">Нет ' + (currentTab === 'active' ? 'активных' : 'завершенных') + ' броней</div>';
                return;
            }

            container.innerHTML = filtered.map(b => {
                const isOverdue = !b.returned && new Date(b.return_datetime) < new Date();
                return '<div class="card ' + (isOverdue ? 'overdue' : '') + ' ' + (b.returned ? 'returned' : '') + '">' +
                    '<div style="display: flex; justify-content: space-between; margin-bottom: 8px;">' +
                        '<div>' +
                            '<div class="item-name">' + escapeHtml(b.item_name) + '</div>' +
                            '<div style="font-size: 12px; color: #64748b;">' + b.quantity + ' шт. • ' + b.duration + ' ' + (b.rent_type === 'hour' ? 'ч.' : 'дн.') + '</div>' +
                        '</div>' +
                        '<div class="price">' + b.total_price.toLocaleString() + ' ₸</div>' +
                    '</div>' +
                    '<div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">' + b.booking_date + ' ' + (b.booking_time || '') + '</div>' +
                    '<div style="display: flex; justify-content: space-between; align-items: center;">' +
                        '<div style="font-size: 12px; ' + (isOverdue ? 'color: #ef4444; font-weight: bold;' : 'color: #64748b;') + '">' +
                            (isOverdue ? '⚠️ Просрочено! ' : '') +
                            (b.returned ? '✅ Возвращено' : 'Возврат: ' + formatDate(b.return_datetime)) +
                        '</div>' +
                        (!b.returned ? '<button class="btn" onclick="returnItem(' + b.id + ')" style="font-size: 12px; padding: 6px 12px;">Вернуть</button>' : '') +
                    '</div>' +
                '</div>';
            }).join('');
        }

        async function openCatalog() {
            try {
                const res = await fetch('/api/inventory');
                if (!res.ok) throw new Error('Failed to load');
                const items = await res.json();
                const container = document.getElementById('catalog-list');
                
                if (!items || items.length === 0) {
                    container.innerHTML = '<div class="empty">Каталог пуст</div>';
                } else {
                    container.innerHTML = items.map(item => 
                        '<div class="card inventory-item">' +
                            '<img src="' + (item.image_url || 'https://via.placeholder.com/80') + '" class="inventory-img" onerror="this.src=\'https://via.placeholder.com/80\'">' +
                            '<div style="flex: 1;">' +
                                '<div class="item-name">' + escapeHtml(item.name) + '</div>' +
                                '<div style="font-size: 12px; color: #a78bfa; text-transform: uppercase; margin: 4px 0;">' + item.sport + '</div>' +
                                '<div style="font-size: 14px; color: #34d399; margin-bottom: 4px;">' + item.price_per_hour + '₸/час • ' + item.price_per_day + '₸/день</div>' +
                                '<div style="font-size: 12px; color: ' + (item.available_quantity > 0 ? '#64748b' : '#ef4444') + ';">Доступно: ' + item.available_quantity + '/' + item.total_quantity + '</div>' +
                            '</div>' +
                        '</div>'
                    ).join('');
                }
                
                document.getElementById('catalog-modal').style.display = 'block';
                document.body.style.overflow = 'hidden';
            } catch (e) {
                showError('Ошибка каталога: ' + e.message);
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

        async function returnItem(bookingId) {
            if (!confirm('Вернуть товар?')) return;
            try {
                const res = await fetch('/api/my-bookings/' + bookingId + '/return?user_id=' + userId, { method: 'POST' });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.error || 'Ошибка');
                }
                await loadBookings();
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
                return new Date(dt).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
            } catch(e) { return dt; }
        }

        loadBookings();
        setInterval(loadBookings, 10000);
    </script>
</body>
</html>"""

ADMIN_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Админ панель</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 16px; }
        .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; border: 1px solid #334155; }
        .btn { background: #7c3aed; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .btn:hover { background: #6d28d9; }
        .btn-danger { background: #dc2626; }
        .btn-danger:hover { background: #b91c1c; }
        .tabs { display: flex; gap: 8px; margin-bottom: 16px; background: #1e293b; padding: 4px; border-radius: 8px; overflow-x: auto; }
        .tab { flex: 1; padding: 10px; text-align: center; border-radius: 6px; cursor: pointer; color: #94a3b8; font-size: 14px; white-space: nowrap; }
        .tab.active { background: #dc2626; color: white; }
        .stat-card { background: #1e293b; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid #334155; }
        .stat-value { font-size: 28px; font-weight: bold; color: #a78bfa; }
        .stat-label { font-size: 12px; color: #64748b; margin-top: 4px; }
        .user-card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; border: 1px solid #334155; cursor: pointer; }
        .user-card:hover { border-color: #7c3aed; }
        .overdue { border-color: #ef4444 !important; background: rgba(239, 68, 68, 0.1) !important; }
        .back-btn { background: #334155; color: white; padding: 10px 20px; border-radius: 8px; cursor: pointer; margin-bottom: 16px; display: inline-block; border: none; }
        .hidden { display: none !important; }
        .inventory-img { width: 60px; height: 60px; object-fit: cover; border-radius: 8px; }
    </style>
</head>
<body>
    <h1 style="color: #dc2626; margin: 0 0 20px 0;">🔴 Админ панель</h1>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px;">
        <div class="stat-card">
            <div class="stat-value" id="stat-revenue">0</div>
            <div class="stat-label">Выручка</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="stat-active">0</div>
            <div class="stat-label">Активные</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="stat-overdue" style="color: #ef4444;">0</div>
            <div class="stat-label">Просрочено</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="stat-users">0</div>
            <div class="stat-label">Пользователи</div>
        </div>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="switchTab('users')">Пользователи</div>
        <div class="tab" onclick="switchTab('bookings')">Все брони</div>
        <div class="tab" onclick="switchTab('inventory')">Склад</div>
    </div>

    <div id="main-content"></div>
    
    <div id="user-detail" class="hidden">
        <button class="back-btn" onclick="backToList()">← Назад</button>
        <h2 id="detail-title" style="color: #a78bfa; margin: 0 0 16px 0;"></h2>
        <div id="detail-content"></div>
    </div>

    <script>
        let currentTab = 'users';
        let allBookings = [];
        let usersList = [];
        let currentUserId = null;

        async function loadData() {
            try {
                const [statsRes, bookingsRes] = await Promise.all([
                    fetch('/api/admin/stats'),
                    fetch('/api/admin/bookings')
                ]);
                
                const stats = await statsRes.json();
                const bookingsData = await bookingsRes.json();
                allBookings = Array.isArray(bookingsData) ? bookingsData : [];
                
                // Группируем по пользователям
                const userMap = {};
                allBookings.forEach(b => {
                    if (!userMap[b.user_id]) {
                        userMap[b.user_id] = { user_id: b.user_id, bookings: [], total: 0, active: 0 };
                    }
                    userMap[b.user_id].bookings.push(b);
                    userMap[b.user_id].total += b.total_price;
                    if (!b.returned) userMap[b.user_id].active++;
                });
                usersList = Object.values(userMap);
                
                document.getElementById('stat-revenue').textContent = (stats.total_revenue || 0).toLocaleString() + ' ₸';
                document.getElementById('stat-active').textContent = stats.active_bookings || 0;
                document.getElementById('stat-overdue').textContent = stats.overdue_bookings || 0;
                document.getElementById('stat-users').textContent = usersList.length;
                
                if (currentUserId) {
                    showUserDetail(currentUserId);
                } else {
                    renderMain();
                }
            } catch (e) {
                document.getElementById('main-content').innerHTML = '<div style="color: #ef4444;">Ошибка загрузки</div>';
            }
        }

        function renderMain() {
            if (currentTab === 'users') renderUsers();
            else if (currentTab === 'bookings') renderAllBookings();
            else if (currentTab === 'inventory') renderInventory();
        }

        function renderUsers() {
            const container = document.getElementById('main-content');
            if (usersList.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #64748b;">Нет данных</div>';
                return;
            }
            
            container.innerHTML = usersList.map(u => {
                const hasOverdue = u.bookings.some(b => !b.returned && new Date(b.return_datetime) < new Date());
                return '<div class="user-card ' + (hasOverdue ? 'overdue' : '') + '" onclick="showUserDetail(' + u.user_id + ')">' +
                    '<div style="display: flex; justify-content: space-between; align-items: center;">' +
                        '<div>' +
                            '<div style="font-weight: 600; color: white;">Пользователь #' + u.user_id + '</div>' +
                            '<div style="font-size: 12px; color: #64748b; margin-top: 4px;">Броней: ' + u.bookings.length + ' | Активных: ' + u.active + '</div>' +
                        '</div>' +
                        '<div style="text-align: right;">' +
                            '<div style="color: #34d399; font-weight: bold;">' + u.total.toLocaleString() + ' ₸</div>' +
                            (hasOverdue ? '<div style="color: #ef4444; font-size: 12px;">⚠️ Просрочка</div>' : '') +
                        '</div>' +
                    '</div>' +
                '</div>';
            }).join('');
        }

        function showUserDetail(userId) {
            currentUserId = userId;
            const user = usersList.find(u => u.user_id === userId);
            if (!user) return;
            
            document.getElementById('main-content').classList.add('hidden');
            document.getElementById('user-detail').classList.remove('hidden');
            document.getElementById('detail-title').textContent = 'Пользователь #' + userId;
            
            const container = document.getElementById('detail-content');
            if (user.bookings.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #64748b;">Нет броней</div>';
                return;
            }
            
            container.innerHTML = user.bookings.map(b => {
                const isOverdue = !b.returned && new Date(b.return_datetime) < new Date();
                return '<div class="card ' + (isOverdue ? 'overdue' : '') + '">' +
                    '<div style="display: flex; justify-content: space-between; margin-bottom: 8px;">' +
                        '<div>' +
                            '<div style="font-weight: 600;">' + escapeHtml(b.item_name) + '</div>' +
                            '<div style="font-size: 12px; color: #64748b;">' + b.quantity + ' шт. • ' + b.duration + ' ' + (b.rent_type === 'hour' ? 'ч.' : 'дн.') + '</div>' +
                        '</div>' +
                        '<div style="color: #34d399; font-weight: bold;">' + b.total_price.toLocaleString() + ' ₸</div>' +
                    '</div>' +
                    '<div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">' + b.booking_date + '</div>' +
                    '<div style="display: flex; justify-content: space-between; align-items: center;">' +
                        '<div style="font-size: 12px; ' + (isOverdue ? 'color: #ef4444; font-weight: bold;' : 'color: #64748b;') + '">' +
                            (isOverdue ? '⚠️ Просрочено! ' : '') +
                            (b.returned ? '✅ Возвращено' : 'Возврат: ' + formatDate(b.return_datetime)) +
                        '</div>' +
                        (!b.returned ? '<button class="btn btn-danger" onclick="adminReturn(' + b.id + ')">Вернуть</button>' : '') +
                    '</div>' +
                '</div>';
            }).join('');
        }

        function backToList() {
            currentUserId = null;
            document.getElementById('user-detail').classList.add('hidden');
            document.getElementById('main-content').classList.remove('hidden');
            renderMain();
        }

        function renderAllBookings() {
            const container = document.getElementById('main-content');
            const active = allBookings.filter(b => !b.returned);
            
            if (active.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #64748b;">Нет активных броней</div>';
                return;
            }
            
            container.innerHTML = active.map(b => {
                const isOverdue = new Date(b.return_datetime) < new Date();
                return '<div class="card ' + (isOverdue ? 'overdue' : '') + '">' +
                    '<div style="display: flex; justify-content: space-between; margin-bottom: 8px;">' +
                        '<div>' +
                            '<div style="font-weight: 600;">' + escapeHtml(b.item_name) + '</div>' +
                            '<div style="font-size: 12px; color: #64748b;">Пользователь #' + b.user_id + '</div>' +
                        '</div>' +
                        '<div style="color: #34d399; font-weight: bold;">' + b.total_price.toLocaleString() + ' ₸</div>' +
                    '</div>' +
                    '<div style="display: flex; justify-content: space-between; align-items: center;">' +
                        '<div style="font-size: 12px; ' + (isOverdue ? 'color: #ef4444;' : 'color: #64748b;') + '">' +
                            (isOverdue ? '⚠️ ' : '') + 'Возврат: ' + formatDate(b.return_datetime) +
                        '</div>' +
                        '<button class="btn btn-danger" onclick="adminReturn(' + b.id + ')">Вернуть</button>' +
                    '</div>' +
                '</div>';
            }).join('');
        }

        async function renderInventory() {
            const container = document.getElementById('main-content');
            try {
                const res = await fetch('/api/inventory');
                const items = await res.json();
                
                container.innerHTML = items.map(item => 
                    '<div class="card" style="display: flex; gap: 16px; align-items: center;">' +
                        '<img src="' + (item.image_url || 'https://via.placeholder.com/60') + '" class="inventory-img" onerror="this.src=\'https://via.placeholder.com/60\'">' +
                        '<div style="flex: 1;">' +
                            '<div style="font-weight: 600;">' + escapeHtml(item.name) + '</div>' +
                            '<div style="font-size: 12px; color: #a78bfa;">' + item.sport + '</div>' +
                            '<div style="font-size: 14px; color: #34d399;">' + item.price_per_hour + '₸/ч | ' + item.price_per_day + '₸/день</div>' +
                            '<div style="font-size: 12px; color: ' + (item.available_quantity > 0 ? '#64748b' : '#ef4444') + ';">' +
                                'Доступно: ' + item.available_quantity + '/' + item.total_quantity +
                            '</div>' +
                        '</div>' +
                    '</div>'
                ).join('');
            } catch (e) {
                container.innerHTML = '<div style="color: #ef4444;">Ошибка загрузки склада</div>';
            }
        }

        async function adminReturn(bookingId) {
            if (!confirm('Подтвердить возврат?')) return;
            try {
                const res = await fetch('/api/admin/bookings/' + bookingId + '/return', { method: 'POST' });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.error);
                }
                await loadData();
            } catch (e) {
                alert('Ошибка: ' + e.message);
            }
        }

        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            backToList();
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
                return new Date(dt).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
            } catch(e) { return dt; }
        }

        loadData();
        setInterval(loadData, 10000);
    </script>
</body>
</html>"""

# ============ ROUTES ============

@app.route('/')
def index():
    user_id = request.args.get('user_id', type=int)
    if user_id and user_id == ADMIN_ID:
        return ADMIN_PAGE
    return USER_PAGE

@app.route('/admin')
def admin_direct():
    return ADMIN_PAGE

# ============ USER API ============

@app.route('/api/my-bookings')
def get_my_bookings():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return Response(to_json({"error": "user_id required"}), status=401, mimetype='application/json')
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("""
            SELECT b.*, i.name as item_name, i.image_url 
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
        
        if booking[2]:  # returned
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

# ============ ADMIN API ============

@app.route('/api/admin/stats')
def admin_stats():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT COALESCE(SUM(total_price), 0) FROM bookings WHERE returned = 0")
        revenue = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM bookings WHERE returned = 0")
        active = c.fetchone()[0]
        
        now = datetime.now().isoformat()
        c.execute("SELECT COUNT(*) FROM bookings WHERE returned = 0 AND return_datetime < %s", (now,))
        overdue = c.fetchone()[0]
        
        c.execute("SELECT COUNT(DISTINCT user_id) FROM bookings")
        users = c.fetchone()[0]
        
        return Response(to_json({
            "total_revenue": float(revenue or 0),
            "active_bookings": active,
            "overdue_bookings": overdue,
            "total_users": users
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        return Response(to_json({"error": str(e)}), status=500, mimetype='application/json')
    finally:
        if conn:
            conn.close()

@app.route('/api/admin/bookings')
def admin_bookings():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("""
            SELECT b.*, i.name as item_name, i.image_url 
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

@app.route('/api/admin/bookings/<int:booking_id>/return', methods=['POST'])
def admin_return(booking_id):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT item_id, quantity, returned FROM bookings WHERE id = %s", (booking_id,))
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
        logger.error(f"Admin return error: {e}")
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

@app.route('/api/health')
def health():
    return Response(to_json({"status": "ok"}), mimetype='application/json')

