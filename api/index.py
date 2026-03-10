# api/index.py — Vercel + Neon Database (исправленная версия)
from flask import Flask, request, jsonify
import os
import sys
import traceback
from datetime import datetime
import logging
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

logger.info("=" * 50)
logger.info("Starting RentBot API with Neon...")

# ИСПРАВЛЕННЫЙ DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL')

# Убираем channel_binding если есть (вызывает ошибки)
if DATABASE_URL and 'channel_binding' in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace('&channel_binding=require', '').replace('?channel_binding=require&', '?').replace('?channel_binding=require', '')

logger.info(f"DB URL (masked): {DATABASE_URL[:50]}..." if DATABASE_URL else "No DATABASE_URL!")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    logger.info(f"psycopg2 version: {psycopg2.__version__}")
except ImportError as e:
    logger.error(f"psycopg2 import failed: {e}")
    psycopg2 = None

def get_db():
    """Получить соединение с Neon"""
    if psycopg2 is None:
        raise Exception("psycopg2 not installed")
    
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")
    
    try:
        # ИСПРАВЛЕНИЕ: Простое соединение без pool для начала
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode='require',
            connect_timeout=10
        )
        conn.autocommit = False
        return conn
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        raise

def init_db():
    """Инициализация базы"""
    if psycopg2 is None:
        logger.error("psycopg2 not available")
        return False
    
    conn = None
    try:
        logger.info("Initializing database...")
        conn = get_db()
        c = conn.cursor()
        
        # Таблица inventory
        c.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                sport TEXT NOT NULL,
                total_quantity INTEGER NOT NULL DEFAULT 0,
                available_quantity INTEGER NOT NULL DEFAULT 0,
                price_per_hour REAL DEFAULT 0,
                price_per_day REAL DEFAULT 0
            )
        ''')
        
        # Таблица bookings
        c.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                item_id INTEGER REFERENCES inventory(id),
                quantity INTEGER NOT NULL DEFAULT 1,
                rent_type TEXT CHECK (rent_type IN ('hour', 'day')),
                booking_date TEXT NOT NULL,
                booking_time TEXT DEFAULT '00:00',
                duration INTEGER NOT NULL DEFAULT 1,
                return_datetime TEXT NOT NULL,
                total_price REAL NOT NULL DEFAULT 0,
                booked_at TEXT NOT NULL,
                reminder_sent INTEGER DEFAULT 0,
                returned INTEGER DEFAULT 0
            )
        ''')
        
        # Индексы
        c.execute('CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_bookings_returned ON bookings(returned)')
        
        # Проверяем данные
        c.execute("SELECT COUNT(*) FROM inventory")
        count = c.fetchone()[0]
        logger.info(f"Inventory count: {count}")
        
        if count == 0:
            logger.info("Seeding data...")
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
                "INSERT INTO inventory (name, sport, total_quantity, available_quantity, price_per_hour, price_per_day) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
                items
            )
            conn.commit()
            logger.info("Data seeded")
        
        conn.commit()
        logger.info("Database initialized OK")
        return True
        
    except Exception as e:
        logger.error(f"Init failed: {e}")
        logger.error(traceback.format_exc())
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# Инициализация при старте
init_db()

# HTML админка (та же что была)
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
    </style>
</head>
<body x-data="app()" x-init="init()" x-cloak class="p-4">
    <div class="max-w-lg mx-auto">
        <div class="flex items-center justify-between mb-6">
            <h1 class="text-2xl font-bold text-purple-400">RentBot Admin</h1>
            <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full" :class="connected ? 'bg-green-500' : 'bg-red-500'"></div>
                <span class="text-xs text-gray-400" x-text="connected ? 'Онлайн' : 'Оффлайн'"></span>
            </div>
        </div>
        
        <div class="grid grid-cols-2 gap-3 mb-4">
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs">Выручка</div>
                <div class="text-xl font-bold text-purple-400"><span x-text="stats.total_revenue.toLocaleString()"></span> ₸</div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs">Активные</div>
                <div class="text-xl font-bold text-blue-400" x-text="stats.active_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs">Просрочено</div>
                <div class="text-xl font-bold" :class="stats.overdue_bookings > 0 ? 'text-red-400' : 'text-green-400'" x-text="stats.overdue_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs">Доступно</div>
                <div class="text-xl font-bold text-green-400" x-text="stats.available_items"></div>
            </div>
        </div>

        <div class="glass rounded-xl p-1 mb-4 flex">
            <button @click="tab = 'bookings'" :class="tab === 'bookings' ? 'bg-purple-600 text-white' : 'text-gray-400'" class="flex-1 py-2 rounded-lg text-sm font-medium">Брони</button>
            <button @click="tab = 'inventory'" :class="tab === 'inventory' ? 'bg-purple-600 text-white' : 'text-gray-400'" class="flex-1 py-2 rounded-lg text-sm font-medium">Склад</button>
        </div>

        <div x-show="tab === 'bookings'" class="space-y-3">
            <div class="flex gap-2 overflow-x-auto pb-2">
                <button @click="filter = 'all'" :class="filter === 'all' ? 'bg-purple-600' : 'bg-slate-700'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap">Все</button>
                <button @click="filter = 'active'" :class="filter === 'active' ? 'bg-green-600' : 'bg-slate-700'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap">Активные</button>
                <button @click="filter = 'overdue'" :class="filter === 'overdue' ? 'bg-red-600' : 'bg-slate-700'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap">Просроченные</button>
            </div>

            <template x-for="b in filteredBookings" :key="b.id">
                <div class="glass rounded-xl p-4" :class="isOverdue(b) && !b.returned ? 'border-red-500/50 border' : ''">
                    <div class="flex justify-between mb-2">
                        <div>
                            <div class="font-semibold text-sm" x-text="b.item_name"></div>
                            <div class="text-xs text-gray-400">ID: <span x-text="b.user_id"></span></div>
                        </div>
                        <div class="text-right">
                            <div class="text-green-400 font-bold"><span x-text="b.total_price.toLocaleString()"></span> ₸</div>
                            <div class="text-xs text-gray-400"><span x-text="b.quantity"></span> шт.</div>
                        </div>
                    </div>
                    <div class="text-xs text-gray-400 mb-2">
                        <span x-text="b.booking_date"></span> <span x-text="b.booking_time"></span>
                        (<span x-text="b.rent_type === 'hour' ? 'час' : 'день'"></span>: <span x-text="b.duration"></span>)
                    </div>
                    <div class="flex justify-between items-center">
                        <div class="text-xs" :class="isOverdue(b) && !b.returned ? 'text-red-400 font-medium' : 'text-gray-500'">
                            Возврат: <span x-text="formatDate(b.return_datetime)"></span>
                        </div>
                        <button @click="returnBooking(b.id)" x-show="!b.returned" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium">Вернуть</button>
                        <span x-show="b.returned" class="text-xs text-gray-500">✓ Возвращено</span>
                    </div>
                </div>
            </template>
            
            <div x-show="filteredBookings.length === 0" class="text-center py-8 text-gray-500 text-sm">
                Нет бронирований
            </div>
        </div>

        <div x-show="tab === 'inventory'" class="space-y-3">
            <template x-for="item in inventory" :key="item.id">
                <div class="glass rounded-xl p-4">
                    <div class="flex justify-between items-start mb-3">
                        <div>
                            <div class="font-semibold text-sm" x-text="item.name"></div>
                            <div class="text-xs text-gray-400 capitalize" x-text="item.sport"></div>
                        </div>
                        <div class="text-right">
                            <div class="text-lg font-bold" :class="item.available_quantity > 0 ? 'text-green-400' : 'text-red-400'">
                                <span x-text="item.available_quantity"></span><span class="text-gray-500 text-sm">/<span x-text="item.total_quantity"></span></span>
                            </div>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-xs mb-3">
                        <div class="bg-slate-800/50 rounded-lg p-2 text-center">
                            <div class="text-gray-400">Час</div>
                            <div class="font-medium"><span x-text="item.price_per_hour.toLocaleString()"></span> ₸</div>
                        </div>
                        <div class="bg-slate-800/50 rounded-lg p-2 text-center">
                            <div class="text-gray-400">День</div>
                            <div class="font-medium"><span x-text="item.price_per_day.toLocaleString()"></span> ₸</div>
                        </div>
                    </div>
                </div>
            </template>
        </div>
        
        <div x-show="error" class="fixed bottom-4 left-4 right-4 max-w-lg mx-auto bg-red-500 text-white px-4 py-3 rounded-xl text-sm" @click="error = ''">
            <span x-text="error"></span>
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
                connected: false,
                error: '',
                
                init() {
                    this.loadData();
                    setInterval(() => this.loadData(), 10000);
                },
                
                async loadData() {
                    try {
                        const [s, b, i] = await Promise.all([
                            fetch('/api/stats').then(r => r.json()),
                            fetch('/api/bookings').then(r => r.json()),
                            fetch('/api/inventory').then(r => r.json())
                        ]);
                        this.stats = s;
                        this.bookings = b;
                        this.inventory = i;
                        this.connected = true;
                        this.error = '';
                    } catch (e) {
                        console.error('Error:', e);
                        this.connected = false;
                        this.error = 'Ошибка соединения с сервером';
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
                    if (!confirm('Вернуть товар?')) return;
                    try {
                        const res = await fetch(`/api/bookings/${id}/return`, { method: 'POST' });
                        if (res.ok) this.loadData();
                    } catch (e) {
                        this.error = 'Ошибка возврата';
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
        
        conn.close()
        
        return jsonify({
            "total_items": total_items or 0,
            "active_bookings": active or 0,
            "total_revenue": float(revenue) if revenue else 0,
            "available_items": int(available) if available else 0,
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
            ORDER BY b.booked_at DESC
        """)
        rows = c.fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
        
    except Exception as e:
        logger.error(f"Bookings error: {e}")
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
        
        c.execute("BEGIN")
        c.execute("SELECT item_id, quantity FROM bookings WHERE id = %s AND returned = 0 FOR UPDATE", (booking_id,))
        r = c.fetchone()
        if not r:
            c.execute("ROLLBACK")
            return jsonify({"error": "Not found"}), 404
        
        c.execute("UPDATE inventory SET available_quantity = available_quantity + %s WHERE id = %s", (r['quantity'], r['item_id']))
        c.execute("UPDATE bookings SET returned = 1 WHERE id = %s", (booking_id,))
        c.execute("COMMIT")
        conn.close()
        
        return jsonify({"ok": True})
        
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        logger.error(f"Return error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/inventory')
def get_inventory():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM inventory ORDER BY id")
        rows = c.fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
        
    except Exception as e:
        logger.error(f"Inventory error: {e}")
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
        c.fetchone()
        conn.close()
        status = "connected"
    except Exception as e:
        status = f"error: {str(e)}"
    
    return jsonify({
        "status": "ok",
        "database": status,
        "url_configured": DATABASE_URL is not None
    })

@app.route('/api/debug')
def debug():
    return jsonify({
        'database_url_exists': 'DATABASE_URL' in os.environ,
        'url_length': len(DATABASE_URL) if DATABASE_URL else 0,
        'psycopg2': psycopg2 is not None
    })
