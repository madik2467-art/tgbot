# api/index.py — Vercel + Neon (финальная рабочая версия)
from flask import Flask, request, jsonify
import os
import sys
import traceback
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

logger.info("=" * 50)
logger.info("RentBot API starting...")

# DATABASE_URL с очисткой от channel_binding
DATABASE_URL = os.getenv('DATABASE_URL', '')
if 'channel_binding' in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split('&channel_binding')[0].split('?channel_binding')[0]

logger.info(f"DATABASE_URL configured: {bool(DATABASE_URL)}")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    logger.info(f"psycopg2: {psycopg2.__version__}")
except ImportError as e:
    logger.error(f"psycopg2 error: {e}")
    psycopg2 = None

def get_db():
    """Получить соединение с Neon"""
    if not psycopg2:
        raise Exception("psycopg2 not installed")
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")
    
    conn = psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=10)
    conn.autocommit = False
    return conn

def seed_data(conn):
    """Заполнить начальные данные"""
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
    """Инициализация БД"""
    if not psycopg2:
        return False
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Создаём таблицы
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
        
        # ВСЕГДА сидируем данные (или обновляем)
        seed_data(conn)
        
        # Проверяем
        c.execute("SELECT COUNT(*) FROM inventory")
        count = c.fetchone()[0]
        logger.info(f"Total inventory items: {count}")
        
        return True
    except Exception as e:
        logger.error(f"Init error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# Инициализация
init_db()

# HTML админка (улучшенная с обработкой ошибок)
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RentBot Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; }
        .glass { background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255,255,255,0.1); }
        [x-cloak] { display: none !important; }
        .loading { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    </style>
</head>
<body x-data="app()" x-init="init()" x-cloak class="p-4">
    <div class="max-w-lg mx-auto">
        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
            <h1 class="text-2xl font-bold text-purple-400">RentBot Admin</h1>
            <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full" :class="connected ? 'bg-green-500' : 'bg-red-500'"></div>
                <span class="text-xs text-gray-400" x-text="connected ? 'Онлайн' : 'Оффлайн'"></span>
            </div>
        </div>
        
        <!-- Error Alert -->
        <div x-show="error" class="mb-4 bg-red-500/20 border border-red-500/50 text-red-300 px-4 py-3 rounded-xl text-sm" x-text="error"></div>
        
        <!-- Stats -->
        <div class="grid grid-cols-2 gap-3 mb-4">
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Выручка</div>
                <div class="text-xl font-bold text-purple-400" x-text="stats.total_revenue.toLocaleString() + ' ₸'"></div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Активные брони</div>
                <div class="text-xl font-bold text-blue-400" x-text="stats.active_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4" :class="stats.overdue_bookings > 0 ? 'border-red-500/50' : ''">
                <div class="text-gray-400 text-xs mb-1">Просрочено</div>
                <div class="text-xl font-bold" :class="stats.overdue_bookings > 0 ? 'text-red-400' : 'text-green-400'" x-text="stats.overdue_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Товаров доступно</div>
                <div class="text-xl font-bold text-green-400" x-text="stats.available_items"></div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="glass rounded-xl p-1 mb-4 flex">
            <button @click="tab = 'bookings'" :class="tab === 'bookings' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'" class="flex-1 py-2 rounded-lg text-sm font-medium transition">Бронирования</button>
            <button @click="tab = 'inventory'" :class="tab === 'inventory' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'" class="flex-1 py-2 rounded-lg text-sm font-medium transition">Склад</button>
        </div>

        <!-- Bookings -->
        <div x-show="tab === 'bookings'" class="space-y-3">
            <div class="flex gap-2 overflow-x-auto pb-2">
                <button @click="filter = 'all'" :class="filter === 'all' ? 'bg-purple-600 text-white' : 'bg-slate-700 text-gray-300'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition">Все</button>
                <button @click="filter = 'active'" :class="filter === 'active' ? 'bg-green-600 text-white' : 'bg-slate-700 text-gray-300'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition">Активные</button>
                <button @click="filter = 'overdue'" :class="filter === 'overdue' ? 'bg-red-600 text-white' : 'bg-slate-700 text-gray-300'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition">Просроченные</button>
            </div>

            <div x-show="loading" class="text-center py-8">
                <div class="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full loading mx-auto"></div>
            </div>

            <template x-for="b in filteredBookings" :key="b.id">
                <div class="glass rounded-xl p-4 transition hover:border-purple-500/30" :class="isOverdue(b) && !b.returned ? 'border-red-500/50 bg-red-500/5' : ''">
                    <div class="flex justify-between items-start mb-2">
                        <div>
                            <div class="font-semibold text-white" x-text="b.item_name"></div>
                            <div class="text-xs text-gray-400">Пользователь: <span x-text="b.user_id"></span></div>
                        </div>
                        <div class="text-right">
                            <div class="text-green-400 font-bold" x-text="b.total_price.toLocaleString() + ' ₸'"></div>
                            <div class="text-xs text-gray-400" x-text="b.quantity + ' шт.'"></div>
                        </div>
                    </div>
                    <div class="text-xs text-gray-400 mb-3 bg-slate-800/50 rounded p-2">
                        <div class="flex justify-between">
                            <span>Начало:</span>
                            <span x-text="b.booking_date + ' ' + b.booking_time"></span>
                        </div>
                        <div class="flex justify-between mt-1">
                            <span>Длительность:</span>
                            <span x-text="b.duration + (b.rent_type === 'hour' ? ' ч.' : ' дн.')"></span>
                        </div>
                    </div>
                    <div class="flex justify-between items-center">
                        <div class="text-xs" :class="isOverdue(b) && !b.returned ? 'text-red-400 font-bold' : 'text-gray-500'">
                            <span x-show="isOverdue(b) && !b.returned">⚠️ </span>
                            Возврат: <span x-text="formatDate(b.return_datetime)"></span>
                        </div>
                        <button @click="returnBooking(b.id)" x-show="!b.returned" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition">Вернуть</button>
                        <span x-show="b.returned" class="text-xs text-green-400">✓ Возвращено</span>
                    </div>
                </div>
            </template>
            
            <div x-show="!loading && filteredBookings.length === 0" class="text-center py-8 text-gray-500">
                Нет бронирований
            </div>
        </div>

        <!-- Inventory -->
        <div x-show="tab === 'inventory'" class="space-y-3">
            <div x-show="loading" class="text-center py-8">
                <div class="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full loading mx-auto"></div>
            </div>

            <template x-for="item in inventory" :key="item.id">
                <div class="glass rounded-xl p-4 hover:border-purple-500/30 transition">
                    <div class="flex justify-between items-start mb-3">
                        <div>
                            <div class="font-semibold text-white" x-text="item.name"></div>
                            <div class="text-xs text-purple-400 capitalize" x-text="item.sport"></div>
                        </div>
                        <div class="text-right">
                            <div class="text-lg font-bold" :class="item.available_quantity > 0 ? 'text-green-400' : 'text-red-400'">
                                <span x-text="item.available_quantity"></span><span class="text-gray-500 text-sm">/<span x-text="item.total_quantity"></span></span>
                            </div>
                            <div class="text-xs text-gray-400">доступно</div>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-xs">
                        <div class="bg-slate-800/50 rounded-lg p-2 text-center">
                            <div class="text-gray-400 mb-1">Почасовая</div>
                            <div class="font-medium text-white" x-text="item.price_per_hour.toLocaleString() + ' ₸'"></div>
                        </div>
                        <div class="bg-slate-800/50 rounded-lg p-2 text-center">
                            <div class="text-gray-400 mb-1">Посуточная</div>
                            <div class="font-medium text-white" x-text="item.price_per_day.toLocaleString() + ' ₸'"></div>
                        </div>
                    </div>
                </div>
            </template>
        </div>
    </div>

    <script>
        function app() {
            return {
                tab: 'bookings',
                filter: 'all',
                stats: { total_revenue: 0, active_bookings: 0, overdue_bookings: 0, available_items: 0 },
                bookings: [],
                inventory: [],
                loading: true,
                connected: false,
                error: '',
                
                init() {
                    this.loadData();
                    setInterval(() => this.loadData(), 10000);
                },
                
                async loadData() {
                    this.loading = true;
                    this.error = '';
                    try {
                        const [sRes, bRes, iRes] = await Promise.all([
                            fetch('/api/stats'),
                            fetch('/api/bookings'),
                            fetch('/api/inventory')
                        ]);
                        
                        if (!sRes.ok || !bRes.ok || !iRes.ok) {
                            throw new Error('API error: ' + (await sRes.text()).slice(0, 100));
                        }
                        
                        const [s, b, i] = await Promise.all([sRes.json(), bRes.json(), iRes.json()]);
                        
                        this.stats = s;
                        this.bookings = b;
                        this.inventory = i;
                        this.connected = true;
                    } catch (e) {
                        console.error('Load error:', e);
                        this.connected = false;
                        this.error = 'Ошибка загрузки: ' + e.message;
                    } finally {
                        this.loading = false;
                    }
                },

                get filteredBookings() {
                    if (this.filter === 'all') return this.bookings;
                    if (this.filter === 'active') return this.bookings.filter(b => !b.returned && !this.isOverdue(b));
                    if (this.filter === 'overdue') return this.bookings.filter(b => !b.returned && this.isOverdue(b));
                    return this.bookings;
                },
                
                isOverdue(b) {
                    return new Date(b.return_datetime) < new Date() && !b.returned;
                },

                formatDate(dt) {
                    const d = new Date(dt);
                    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
                },
                
                async returnBooking(id) {
                    if (!confirm('Подтвердить возврат?')) return;
                    try {
                        const res = await fetch(`/api/bookings/${id}/return`, { method: 'POST' });
                        if (!res.ok) throw new Error('Return failed');
                        await this.loadData();
                    } catch (e) {
                        this.error = 'Ошибка возврата: ' + e.message;
                    }
                }
            }
        }
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
        
        return jsonify({
            "total_items": total_items or 0,
            "active_bookings": active or 0,
            "total_revenue": float(revenue or 0),
            "available_items": int(available or 0),
            "overdue_bookings": overdue or 0
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500
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
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        logger.error(f"Bookings error: {e}")
        return jsonify({"error": str(e)}), 500
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
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        logger.error(f"Inventory error: {e}")
        return jsonify({"error": str(e)}), 500
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
            return jsonify({"error": "Booking not found"}), 404
        
        c.execute("UPDATE inventory SET available_quantity = available_quantity + %s WHERE id = %s", (r['quantity'], r['item_id']))
        c.execute("UPDATE bookings SET returned = 1 WHERE id = %s", (booking_id,))
        conn.commit()
        
        return jsonify({"ok": True})
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Return error: {e}")
        return jsonify({"error": str(e)}), 500
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
        return jsonify({"status": "ok", "database": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "database": str(e)}), 500

@app.route('/api/seed', methods=['POST'])
def force_seed():
    """Ручное сидирование данных"""
    try:
        conn = get_db()
        seed_data(conn)
        conn.close()
        return jsonify({"ok": True, "message": "Data seeded"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
