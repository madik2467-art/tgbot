# api/index.py — Vercel + Supabase (исправленная версия)
from flask import Flask, request, jsonify
import os
import sys
import traceback
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

logger.info("=" * 50)
logger.info("Starting RentBot API...")
logger.info(f"Python version: {sys.version}")

# ИСПРАВЛЕННЫЙ DATABASE_URL с SSL
DATABASE_URL = os.getenv('DATABASE_URL')

# Импорт psycopg2 с обработкой ошибок
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool
    logger.info("psycopg2 imported successfully")
except ImportError as e:
    logger.error(f"Failed to import psycopg2: {e}")
    psycopg2 = None
    RealDictCursor = None
    pool = None

# Глобальный пул соединений (критично для serverless!)
_connection_pool = None

def get_connection_pool():
    """Создать пул соединений (thread-safe)"""
    global _connection_pool
    
    if _connection_pool is None and psycopg2:
        try:
            # ИСПРАВЛЕНИЕ: Добавляем sslmode=require и увеличиваем таймауты
            db_url = DATABASE_URL
            if 'sslmode=' not in db_url:
                db_url += '?sslmode=require'
            
            _connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,  # minconn
                3,  # maxconn (не больше 3 для Vercel!)
                db_url,
                connect_timeout=10,
                options='-c statement_timeout=30000'  # 30 сек макс на запрос
            )
            logger.info("Connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    
    return _connection_pool

def get_db():
    """Получить соединение из пула"""
    if psycopg2 is None:
        raise Exception("psycopg2 not installed")
    
    pool = get_connection_pool()
    if pool is None:
        raise Exception("Connection pool not initialized")
    
    try:
        conn = pool.getconn()
        if conn.closed:
            pool.putconn(conn, close=True)
            conn = pool.getconn()
        return conn
    except Exception as e:
        logger.error(f"Failed to get connection from pool: {e}")
        # Fallback: создаём новое соединение
        return psycopg2.connect(DATABASE_URL, sslmode='require')

def release_db(conn):
    """Вернуть соединение в пул"""
    if _connection_pool and conn:
        try:
            _connection_pool.putconn(conn)
        except:
            pass

def init_db():
    """Инициализация базы данных"""
    if psycopg2 is None:
        logger.error("Cannot init DB - psycopg2 not available")
        return False
    
    conn = None
    try:
        logger.info("Initializing database...")
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        conn.autocommit = False
        c = conn.cursor()
        
        # Создаём таблицы с правильными типами
        c.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                sport TEXT NOT NULL,
                total_quantity INTEGER NOT NULL DEFAULT 0,
                available_quantity INTEGER NOT NULL DEFAULT 0,
                price_per_hour REAL DEFAULT 0,
                price_per_day REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                item_id INTEGER REFERENCES inventory(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1,
                rent_type TEXT CHECK (rent_type IN ('hour', 'day')),
                booking_date TEXT NOT NULL,
                booking_time TEXT DEFAULT '00:00',
                duration INTEGER NOT NULL DEFAULT 1,
                return_datetime TEXT NOT NULL,
                total_price REAL NOT NULL DEFAULT 0,
                booked_at TEXT NOT NULL,
                reminder_sent INTEGER DEFAULT 0,
                returned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индексы для скорости
        c.execute('CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_bookings_returned ON bookings(returned)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_bookings_return_datetime ON bookings(return_datetime)')
        
        # Проверяем данные
        c.execute("SELECT COUNT(*) FROM inventory")
        count = c.fetchone()[0]
        logger.info(f"Inventory items: {count}")
        
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
                "INSERT INTO inventory (name, sport, total_quantity, available_quantity, price_per_hour, price_per_day) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
                items
            )
            conn.commit()
            logger.info("Data seeded successfully")
        else:
            conn.commit()
        
        logger.info("Database initialization completed")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.error(traceback.format_exc())
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# Инициализация при импорте
init_db()

# HTML страница админки (улучшенная)
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
        .glass:hover { border-color: rgba(147, 51, 234, 0.5); }
        [x-cloak] { display: none !important; }
        .pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: .5; }
        }
    </style>
</head>
<body x-data="app()" x-init="init()" x-cloak class="p-4 min-h-screen">
    <div class="max-w-lg mx-auto">
        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
            <h1 class="text-2xl font-bold text-purple-400">RentBot Admin</h1>
            <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full" :class="connected ? 'bg-green-500' : 'bg-red-500 pulse'"></div>
                <span class="text-xs text-gray-400" x-text="connected ? 'Онлайн' : 'Оффлайн'"></span>
            </div>
        </div>
        
        <!-- Stats -->
        <div class="grid grid-cols-2 gap-3 mb-4">
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Выручка</div>
                <div class="text-xl font-bold text-purple-400"><span x-text="stats.total_revenue.toLocaleString()"></span> ₸</div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Активные</div>
                <div class="text-xl font-bold text-blue-400" x-text="stats.active_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4" :class="stats.overdue_bookings > 0 ? 'border-red-500/50 border' : ''">
                <div class="text-gray-400 text-xs mb-1">Просрочено</div>
                <div class="text-xl font-bold" :class="stats.overdue_bookings > 0 ? 'text-red-400' : 'text-green-400'" x-text="stats.overdue_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Доступно</div>
                <div class="text-xl font-bold text-green-400" x-text="stats.available_items"></div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="glass rounded-xl p-1 mb-4 flex">
            <button @click="tab = 'bookings'" :class="tab === 'bookings' ? 'bg-purple-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'" class="flex-1 py-2 rounded-lg text-sm font-medium transition-all">Брони</button>
            <button @click="tab = 'inventory'" :class="tab === 'inventory' ? 'bg-purple-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'" class="flex-1 py-2 rounded-lg text-sm font-medium transition-all">Склад</button>
        </div>

        <!-- Bookings Tab -->
        <div x-show="tab === 'bookings'" class="space-y-3">
            <!-- Filters -->
            <div class="flex gap-2 overflow-x-auto pb-2">
                <button @click="filter = 'all'" :class="filter === 'all' ? 'bg-purple-600 text-white' : 'bg-slate-700 text-gray-300'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors">Все</button>
                <button @click="filter = 'active'" :class="filter === 'active' ? 'bg-green-600 text-white' : 'bg-slate-700 text-gray-300'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors">Активные</button>
                <button @click="filter = 'overdue'" :class="filter === 'overdue' ? 'bg-red-600 text-white' : 'bg-slate-700 text-gray-300'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors">Просроченные</button>
                <button @click="filter = 'returned'" :class="filter === 'returned' ? 'bg-gray-600 text-white' : 'bg-slate-700 text-gray-300'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors">Возвращённые</button>
            </div>

            <!-- Loading -->
            <div x-show="loading" class="text-center py-8">
                <div class="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                <div class="text-gray-400 text-sm">Загрузка...</div>
            </div>

            <!-- Bookings List -->
            <template x-for="b in filteredBookings" :key="b.id">
                <div class="glass rounded-xl p-4 transition-all" :class="isOverdue(b) && !b.returned ? 'border-red-500/50 border bg-red-500/5' : (b.returned ? 'opacity-60' : '')">
                    <div class="flex justify-between items-start mb-2">
                        <div>
                            <div class="font-semibold text-sm text-white" x-text="b.item_name"></div>
                            <div class="text-xs text-gray-400">ID: <span x-text="b.user_id"></span></div>
                        </div>
                        <div class="text-right">
                            <div class="text-green-400 font-bold"><span x-text="b.total_price.toLocaleString()"></span> ₸</div>
                            <div class="text-xs text-gray-400"><span x-text="b.quantity"></span> шт.</div>
                        </div>
                    </div>
                    
                    <div class="text-xs text-gray-400 mb-2 bg-slate-800/50 rounded-lg p-2">
                        <div class="flex justify-between mb-1">
                            <span>Начало:</span>
                            <span x-text="b.booking_date + ' ' + b.booking_time"></span>
                        </div>
                        <div class="flex justify-between">
                            <span>Длительность:</span>
                            <span x-text="b.duration + (b.rent_type === 'hour' ? ' ч.' : ' дн.')"></span>
                        </div>
                    </div>
                    
                    <div class="flex justify-between items-center">
                        <div class="text-xs" :class="isOverdue(b) && !b.returned ? 'text-red-400 font-bold' : 'text-gray-500'">
                            <span x-show="isOverdue(b) && !b.returned">⚠️ </span>
                            Возврат: <span x-text="formatDate(b.return_datetime)"></span>
                        </div>
                        <button @click="returnBooking(b.id)" x-show="!b.returned" :disabled="processing" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white rounded-lg text-xs font-medium transition-colors">
                            <span x-show="!processing">Вернуть</span>
                            <span x-show="processing">...</span>
                        </button>
                        <span x-show="b.returned" class="text-xs text-green-400">✓ Возвращено</span>
                    </div>
                </div>
            </template>
            
            <div x-show="!loading && filteredBookings.length === 0" class="text-center py-8 text-gray-500 text-sm">
                Нет бронирований
            </div>
        </div>

        <!-- Inventory Tab -->
        <div x-show="tab === 'inventory'" class="space-y-3">
            <div x-show="loading" class="text-center py-8">
                <div class="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            </div>
            
            <template x-for="item in inventory" :key="item.id">
                <div class="glass rounded-xl p-4 hover:border-purple-500/30 transition-all">
                    <div class="flex justify-between items-start mb-3">
                        <div>
                            <div class="font-semibold text-sm text-white" x-text="item.name"></div>
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
                            <div class="text-gray-400 mb-1">Час</div>
                            <div class="font-medium text-white"><span x-text="item.price_per_hour.toLocaleString()"></span> ₸</div>
                        </div>
                        <div class="bg-slate-800/50 rounded-lg p-2 text-center">
                            <div class="text-gray-400 mb-1">День</div>
                            <div class="font-medium text-white"><span x-text="item.price_per_day.toLocaleString()"></span> ₸</div>
                        </div>
                    </div>
                </div>
            </template>
        </div>
        
        <!-- Error Toast -->
        <div x-show="error" x-transition class="fixed bottom-4 left-4 right-4 max-w-lg mx-auto bg-red-500 text-white px-4 py-3 rounded-xl text-sm shadow-lg" @click="error = ''">
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
                loading: true,
                processing: false,
                connected: false,
                error: '',
                
                init() {
                    this.loadData();
                    setInterval(() => this.loadData(), 10000);
                },
                
                async loadData() {
                    this.loading = true;
                    try {
                        const [s, b, i] = await Promise.all([
                            fetch('/api/stats').then(r => r.ok ? r.json() : Promise.reject('stats failed')),
                            fetch('/api/bookings').then(r => r.ok ? r.json() : Promise.reject('bookings failed')),
                            fetch('/api/inventory').then(r => r.ok ? r.json() : Promise.reject('inventory failed'))
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
                    } finally {
                        this.loading = false;
                    }
                },

                get filteredBookings() {
                    if (this.filter === 'all') return this.bookings;
                    if (this.filter === 'active') return this.bookings.filter(b => !b.returned && !this.isOverdue(b));
                    if (this.filter === 'overdue') return this.bookings.filter(b => !b.returned && this.isOverdue(b));
                    if (this.filter === 'returned') return this.bookings.filter(b => b.returned);
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
                    if (!confirm('Подтвердить возврат товара?')) return;
                    this.processing = true;
                    try {
                        const res = await fetch(`/api/bookings/${id}/return`, { method: 'POST' });
                        if (res.ok) {
                            await this.loadData();
                        } else {
                            const err = await res.json();
                            this.error = err.error || 'Ошибка возврата';
                        }
                    } catch (e) {
                        this.error = 'Ошибка соединения';
                    } finally {
                        this.processing = false;
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
        
        result = {
            "total_items": total_items or 0,
            "active_bookings": active or 0,
            "total_revenue": float(revenue) if revenue else 0,
            "available_items": int(available) if available else 0,
            "overdue_bookings": overdue or 0
        }
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API Error /api/stats: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db(conn)

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
        result = [dict(r) for r in rows]
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API Error /api/bookings: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db(conn)

@app.route('/api/bookings/<int:booking_id>/return', methods=['POST'])
def return_booking(booking_id):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Начинаем транзакцию
        c.execute("BEGIN")
        
        c.execute("SELECT item_id, quantity FROM bookings WHERE id = %s AND returned = 0 FOR UPDATE", (booking_id,))
        r = c.fetchone()
        if not r:
            c.execute("ROLLBACK")
            return jsonify({"error": "Booking not found or already returned"}), 404
        
        # Возвращаем товар на склад
        c.execute("UPDATE inventory SET available_quantity = available_quantity + %s WHERE id = %s", (r['quantity'], r['item_id']))
        # Помечаем бронь как возвращённую
        c.execute("UPDATE bookings SET returned = 1 WHERE id = %s", (booking_id,))
        
        c.execute("COMMIT")
        return jsonify({"ok": True, "message": "Booking returned successfully"})
        
    except Exception as e:
        if conn:
            c.execute("ROLLBACK")
        logger.error(f"API Error return_booking: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db(conn)

@app.route('/api/inventory')
def get_inventory():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM inventory ORDER BY id")
        rows = c.fetchall()
        result = [dict(r) for r in rows]
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API Error /api/inventory: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db(conn)

@app.route('/api/health')
def health():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=5)
        conn.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return jsonify({
        "status": "ok",
        "psycopg2": psycopg2 is not None,
        "database_url_set": DATABASE_URL is not None,
        "database_connection": db_status,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/debug')
def debug():
    safe_env = {k: v[:20] + '...' if v and len(str(v)) > 20 else v 
                for k, v in os.environ.items() 
                if not any(s in k.lower() for s in ['secret', 'token', 'key', 'password', 'auth'])}
    
    return jsonify({
        'database_url_exists': 'DATABASE_URL' in os.environ,
        'database_url_length': len(os.getenv('DATABASE_URL', '')),
        'env_keys': list(os.environ.keys()),
        'sample_vars': safe_env,
        'psycopg2_version': psycopg2.__version__ if psycopg2 else None
    })
