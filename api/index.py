# api/index.py — Vercel + Supabase (Flask) с детальным логированием
from flask import Flask, request, jsonify
import os
import sys
import traceback
from datetime import datetime

app = Flask(__name__)

# Детальное логирование
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("=" * 50)
logger.info("Starting RentBot API...")
logger.info(f"Python version: {sys.version}")
logger.info(f"Current directory: {os.getcwd()}")
logger.info(f"Files in directory: {os.listdir('.')}")

# Supabase PostgreSQL URL
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    # Временно захардкожено (потом убрать!)
    DATABASE_URL = 'postgresql://postgres:train-luck-stun-apple@db.wgxgpjpfjhigqronecss.supabase.co:5432/postgres?sslmode=require'

# Для проверки — выводим в логи (пароль замаскирован)
print(f"DATABASE_URL loaded: {DATABASE_URL[:30]}...")

# Импортируем psycopg2
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    logger.info("Successfully imported psycopg2")
except ImportError as e:
    logger.error(f"Failed to import psycopg2: {e}")
    psycopg2 = None

def get_db():
    """Получить соединение с БД"""
    if psycopg2 is None:
        raise Exception("psycopg2 not installed")
    
    try:
        logger.info("Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = RealDictCursor
        logger.info("Database connection successful")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def init_db():
    """Инициализация базы данных"""
    if psycopg2 is None:
        logger.error("Cannot init DB - psycopg2 not available")
        return False
    
    try:
        logger.info("Initializing database...")
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        
        # Создаём таблицы
        c.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                sport TEXT,
                total_quantity INTEGER,
                available_quantity INTEGER,
                price_per_hour REAL DEFAULT 0,
                price_per_day REAL DEFAULT 0
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                item_id INTEGER,
                quantity INTEGER,
                rent_type TEXT,
                booking_date TEXT,
                booking_time TEXT,
                duration INTEGER,
                return_datetime TEXT,
                total_price REAL,
                booked_at TEXT,
                reminder_sent INTEGER DEFAULT 0,
                returned INTEGER DEFAULT 0
            )
        ''')
        
        # Проверяем, есть ли данные
        c.execute("SELECT COUNT(*) FROM inventory")
        count = c.fetchone()[0]
        logger.info(f"Inventory count: {count}")
        
        if count == 0:
            logger.info("Seeding initial data...")
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
                "INSERT INTO inventory (name, sport, total_quantity, available_quantity, price_per_hour, price_per_day) VALUES (%s, %s, %s, %s, %s, %s)",
                items
            )
            conn.commit()
            logger.info("Data seeded successfully")
        
        conn.close()
        logger.info("Database initialization completed")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.error(traceback.format_exc())
        return False

# Инициализация при импорте
init_db()

# HTML страница (сокращённая для теста)
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
        <h1 class="text-2xl font-bold mb-4 text-purple-400">RentBot Admin</h1>
        
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
                        <button @click="returnBooking(b.id)" x-show="!b.returned" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition-colors">Вернуть</button>
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
    </div>

    <script>
        function app() {
            return {
                tab: 'bookings',
                filter: 'all',
                stats: { total_revenue: 0, active_bookings: 0, overdue_bookings: 0, available_items: 0 },
                bookings: [],
                inventory: [],
                
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
                    } catch (e) {
                        console.error('Error:', e);
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
                        if (res.ok) {
                            this.loadData();
                        }
                    } catch (e) {
                        console.error('Error:', e);
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
    try:
        logger.info("API: /api/stats called")
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
        
        result = {
            "total_items": total_items or 0,
            "active_bookings": active or 0,
            "total_revenue": float(revenue) if revenue else 0,
            "available_items": int(available) if available else 0,
            "overdue_bookings": overdue or 0
        }
        logger.info(f"API: /api/stats returning: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API Error in /api/stats: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/bookings')
def get_bookings():
    try:
        logger.info("API: /api/bookings called")
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
        result = [dict(r) for r in rows]
        logger.info(f"API: /api/bookings returning {len(result)} rows")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API Error in /api/bookings: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/bookings/<int:booking_id>/return', methods=['POST'])
def return_booking(booking_id):
    try:
        logger.info(f"API: /api/bookings/{booking_id}/return called")
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT item_id, quantity FROM bookings WHERE id = %s AND returned = 0", (booking_id,))
        r = c.fetchone()
        if not r:
            conn.close()
            return jsonify({"error": "Not found"}), 404
        
        c.execute("UPDATE inventory SET available_quantity = available_quantity + %s WHERE id = %s", (r['quantity'], r['item_id']))
        c.execute("UPDATE bookings SET returned = 1 WHERE id = %s", (booking_id,))
        conn.commit()
        conn.close()
        
        logger.info(f"API: Booking {booking_id} returned successfully")
        return jsonify({"ok": True})
        
    except Exception as e:
        logger.error(f"API Error in return_booking: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/inventory')
def get_inventory():
    try:
        logger.info("API: /api/inventory called")
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM inventory ORDER BY id")
        rows = c.fetchall()
        conn.close()
        result = [dict(r) for r in rows]
        logger.info(f"API: /api/inventory returning {len(result)} rows")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API Error in /api/inventory: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# Для теста - простой endpoint
@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "psycopg2": psycopg2 is not None,
        "database_url_set": os.getenv('DATABASE_URL') is not None  # ← Исправлено!
    })

logger.info("Flask app initialized successfully")

@app.route('/api/debug')
def debug():
    import os
    env_vars = {k: v[:30] + '...' if v and len(v) > 30 else v 
                for k, v in os.environ.items() 
                if not k.lower().startswith('secret') and not k.lower().startswith('token')}
    
    return jsonify({
        'total_env_vars': len(os.environ),
        'database_url_raw': os.getenv('DATABASE_URL'),
        'database_url_exists': 'DATABASE_URL' in os.environ,
        'env_keys': list(os.environ.keys()),
        'sample_vars': env_vars
    })


