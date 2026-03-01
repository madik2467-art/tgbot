# api/index.py — Vercel Serverless API + WebApp
import sqlite3
import json
from datetime import datetime
from typing import Optional

# Vercel использует serverless, поэтому база должна быть в /tmp
DB_PATH = "/tmp/rent_bot.db"

def get_db():
    """Подключение к БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация (вызывать при первом запуске)"""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            sport TEXT,
            total_quantity INTEGER,
            available_quantity INTEGER,
            price_per_hour REAL DEFAULT 0,
            price_per_day REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
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
        );
    ''')
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM inventory")
    if cursor.fetchone()[0] == 0:
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
        conn.executemany("INSERT INTO inventory VALUES (NULL, ?, ?, ?, ?, ?, ?)", items)
        conn.commit()
    conn.close()

# HTML страница (inline)
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>RentBot Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <meta name="theme-color" content="#0f172a">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; touch-action: manipulation; }
        .glass { background: rgba(30, 41, 59, 0.9); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); }
        .gradient-text { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        [x-cloak] { display: none !important; }
        .telegram-button { background: #3390ec; color: white; }
        .telegram-button:active { background: #2a7bc8; }
        /* Скрыть скроллбар но оставить скролл */
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body x-data="app()" x-init="init()" x-cloak class="min-h-screen pb-20">
    
    <!-- Telegram Header -->
    <div class="fixed top-0 w-full z-50 glass border-b border-slate-700">
        <div class="max-w-lg mx-auto px-4 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 bg-gradient-to-br from-purple-500 to-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-sm">R</div>
                <div>
                    <div class="font-semibold text-sm">RentBot Admin</div>
                    <div class="text-xs text-gray-400" x-text="stats.active_bookings + ' активных'"></div>
                </div>
            </div>
            <button @click="refreshData()" class="p-2 rounded-lg hover:bg-slate-700 transition-colors" :class="loading ? 'animate-spin' : ''">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
            </button>
        </div>
    </div>

    <!-- Main Content -->
    <main class="pt-16 max-w-lg mx-auto px-4">
        
        <!-- Stats Cards -->
        <div class="grid grid-cols-2 gap-3 my-4">
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Выручка</div>
                <div class="text-xl font-bold text-purple-400"><span x-text="stats.total_revenue.toLocaleString()"></span> ₸</div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Просрочено</div>
                <div class="text-xl font-bold" :class="stats.overdue_bookings > 0 ? 'text-red-400' : 'text-green-400'" x-text="stats.overdue_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Активные</div>
                <div class="text-xl font-bold text-blue-400" x-text="stats.active_bookings"></div>
            </div>
            <div class="glass rounded-xl p-4">
                <div class="text-gray-400 text-xs mb-1">Доступно</div>
                <div class="text-xl font-bold text-green-400" x-text="stats.available_items"></div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="glass rounded-xl p-1 mb-4 flex">
            <button @click="tab = 'bookings'" 
                    :class="tab === 'bookings' ? 'bg-purple-600 text-white' : 'text-gray-400'"
                    class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all">
                Брони
            </button>
            <button @click="tab = 'inventory'" 
                    :class="tab === 'inventory' ? 'bg-purple-600 text-white' : 'text-gray-400'"
                    class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all">
                Склад
            </button>
        </div>

        <!-- Bookings Tab -->
        <div x-show="tab === 'bookings'" class="space-y-3">
            <div class="flex gap-2 overflow-x-auto no-scrollbar pb-2">
                <button @click="filter = 'all'" :class="filter === 'all' ? 'bg-purple-600' : 'bg-slate-700'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors">Все</button>
                <button @click="filter = 'active'" :class="filter === 'active' ? 'bg-green-600' : 'bg-slate-700'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors">Активные</button>
                <button @click="filter = 'overdue'" :class="filter === 'overdue' ? 'bg-red-600' : 'bg-slate-700'" class="px-4 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors">Просроченные</button>
            </div>

            <template x-for="b in filteredBookings" :key="b.id">
                <div class="glass rounded-xl p-4" :class="isOverdue(b) && !b.returned ? 'border-red-500/50' : ''">
                    <div class="flex justify-between items-start mb-2">
                        <div>
                            <div class="font-semibold text-sm" x-text="b.item_name"></div>
                            <div class="text-xs text-gray-400">ID клиента: <span x-text="b.user_id"></span></div>
                        </div>
                        <div class="text-right">
                            <div class="text-sm font-bold text-green-400"><span x-text="b.total_price.toLocaleString()"></span> ₸</div>
                            <div class="text-xs text-gray-400"><span x-text="b.quantity"></span> шт.</div>
                        </div>
                    </div>
                    
                    <div class="flex items-center gap-2 mb-3 text-xs">
                        <span class="px-2 py-0.5 rounded bg-slate-700" x-text="b.rent_type === 'hour' ? '⏰ Час' : '📅 День'"></span>
                        <span class="text-gray-400" x-text="b.booking_date + ' ' + b.booking_time"></span>
                    </div>

                    <div class="flex items-center justify-between">
                        <div class="text-xs" :class="isOverdue(b) && !b.returned ? 'text-red-400 font-medium' : 'text-gray-400'">
                            Возврат: <span x-text="formatDate(b.return_datetime)"></span>
                        </div>
                        <button @click="returnBooking(b.id)" 
                                x-show="!b.returned"
                                class="telegram-button px-4 py-1.5 rounded-lg text-xs font-medium active:scale-95 transition-transform">
                            Вернуть
                        </button>
                        <span x-show="b.returned" class="text-xs text-gray-500">✓ Возвращено</span>
                    </div>
                </div>
            </template>
            
            <div x-show="filteredBookings.length === 0" class="text-center py-8 text-gray-500 text-sm">
                Нет бронирований
            </div>
        </div>

        <!-- Inventory Tab -->
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

                    <div class="flex gap-2">
                        <button @click="editItem(item)" class="flex-1 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-xs font-medium transition-colors">
                            Изменить
                        </button>
                        <button @click="deleteItem(item.id)" class="px-3 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg text-xs transition-colors">
                            ✕
                        </button>
                    </div>
                </div>
            </template>
        </div>
    </main>

    <!-- Bottom Actions -->
    <div class="fixed bottom-0 w-full glass border-t border-slate-700 pb-safe">
        <div class="max-w-lg mx-auto px-4 py-3 flex gap-3">
            <button @click="showAddItem = true" class="flex-1 telegram-button py-3 rounded-xl text-sm font-semibold active:scale-95 transition-transform">
                + Добавить товар
            </button>
        </div>
    </div>

    <!-- Add Item Modal -->
    <div x-show="showAddItem" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4" x-cloak @click.away="showAddItem = false">
        <div class="glass rounded-2xl p-6 w-full max-w-sm" @click.stop>
            <h3 class="text-lg font-bold mb-4">Новый товар</h3>
            <div class="space-y-3">
                <input x-model="newItem.name" placeholder="Название" class="w-full px-4 py-3 bg-slate-800 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500">
                <select x-model="newItem.sport" class="w-full px-4 py-3 bg-slate-800 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500">
                    <option value="футбол">⚽ Футбол</option>
                    <option value="теннис">🎾 Теннис</option>
                    <option value="баскетбол">🏀 Баскетбол</option>
                    <option value="вело">🚲 Велосипеды</option>
                    <option value="хоккей">🏒 Хоккей</option>
                    <option value="скейт">🛹 Скейтборды</option>
                    <option value="ролики">🛼 Ролики</option>
                    <option value="фитнес">🏋️ Фитнес</option>
                </select>
                <input x-model.number="newItem.total_quantity" type="number" placeholder="Количество" class="w-full px-4 py-3 bg-slate-800 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500">
                <div class="grid grid-cols-2 gap-3">
                    <input x-model.number="newItem.price_per_hour" type="number" placeholder="Цена/час" class="w-full px-4 py-3 bg-slate-800 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500">
                    <input x-model.number="newItem.price_per_day" type="number" placeholder="Цена/день" class="w-full px-4 py-3 bg-slate-800 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500">
                </div>
                <div class="flex gap-3 mt-4">
                    <button @click="showAddItem = false" class="flex-1 py-3 bg-slate-700 text-white rounded-xl text-sm font-medium">Отмена</button>
                    <button @click="addItem()" class="flex-1 telegram-button py-3 rounded-xl text-sm font-semibold">Сохранить</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div x-show="toast.show" x-transition class="fixed top-20 left-1/2 transform -translate-x-1/2 z-50">
        <div class="glass px-6 py-3 rounded-full text-sm font-medium" :class="toast.type === 'error' ? 'bg-red-600/90 text-white' : 'bg-green-600/90 text-white'" x-text="toast.message"></div>
    </div>

    <script>
        function app() {
            return {
                tab: 'bookings',
                filter: 'all',
                stats: { total_items: 0, active_bookings: 0, total_revenue: 0, available_items: 0, overdue_bookings: 0 },
                bookings: [],
                inventory: [],
                loading: false,
                showAddItem: false,
                newItem: { name: '', sport: 'футбол', total_quantity: 1, price_per_hour: 0, price_per_day: 0 },
                toast: { show: false, message: '', type: 'success' },
                refreshInterval: null,

                init() {
                    this.refreshData();
                    // Автообновление каждые 10 секунд
                    this.refreshInterval = setInterval(() => this.refreshData(), 10000);
                },

                showToast(message, type = 'success') {
                    this.toast = { show: true, message, type };
                    setTimeout(() => this.toast.show = false, 3000);
                },

                async refreshData() {
                    this.loading = true;
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
                    this.loading = false;
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
                            this.showToast('Товар возвращен');
                            this.refreshData();
                        } else {
                            this.showToast('Ошибка', 'error');
                        }
                    } catch (e) {
                        this.showToast('Ошибка сети', 'error');
                    }
                },

                async addItem() {
                    if (!this.newItem.name) {
                        this.showToast('Введите название', 'error');
                        return;
                    }
                    try {
                        const res = await fetch('/api/inventory', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(this.newItem)
                        });
                        if (res.ok) {
                            this.showToast('Товар добавлен');
                            this.showAddItem = false;
                            this.newItem = { name: '', sport: 'футбол', total_quantity: 1, price_per_hour: 0, price_per_day: 0 };
                            this.refreshData();
                        }
                    } catch (e) {
                        this.showToast('Ошибка', 'error');
                    }
                },

                async deleteItem(id) {
                    if (!confirm('Удалить товар?')) return;
                    try {
                        const res = await fetch(`/api/inventory/${id}`, { method: 'DELETE' });
                        if (res.ok) {
                            this.showToast('Товар удален');
                            this.refreshData();
                        } else {
                            this.showToast('Нельзя удалить (есть брони)', 'error');
                        }
                    } catch (e) {
                        this.showToast('Ошибка', 'error');
                    }
                },

                editItem(item) {
                    // Для Telegram WebApp можно открыть нативный prompt
                    const newPrice = prompt('Новая цена за час:', item.price_per_hour);
                    if (newPrice && !isNaN(newPrice)) {
                        fetch(`/api/inventory/${item.id}`, {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ price_per_hour: parseFloat(newPrice) })
                        }).then(() => {
                            this.showToast('Цена обновлена');
                            this.refreshData();
                        });
                    }
                }
            }
        }
    </script>
</body>
</html>
"""

# ===================== API HANDLERS =====================

def handler(request):
    """Основной handler для Vercel"""
    path = request.get('path', '/')
    method = request.get('method', 'GET')
    
    # Инициализация БД при первом запуске
    init_db()
    
    # HTML страница
    if path == '/' and method == 'GET':
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/html; charset=utf-8'},
            'body': HTML_PAGE
        }
    
    # API endpoints
    if path == '/api/stats' and method == 'GET':
        return get_stats()
    
    if path == '/api/bookings' and method == 'GET':
        return get_bookings()
    
    if path.startswith('/api/bookings/') and path.endswith('/return') and method == 'POST':
        booking_id = int(path.split('/')[3])
        return return_booking(booking_id)
    
    if path == '/api/inventory' and method == 'GET':
        return get_inventory()
    
    if path == '/api/inventory' and method == 'POST':
        return add_inventory(json.loads(request.get('body', '{}')))
    
    if path.startswith('/api/inventory/') and method == 'DELETE':
        item_id = int(path.split('/')[3])
        return delete_inventory(item_id)
    
    if path.startswith('/api/inventory/') and method == 'PATCH':
        item_id = int(path.split('/')[3])
        return update_inventory(item_id, json.loads(request.get('body', '{}')))
    
    return {'statusCode': 404, 'body': 'Not Found'}

# ===================== API FUNCTIONS =====================

def get_stats():
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*), SUM(available_quantity) FROM inventory")
    total_items, available = c.fetchone()
    
    c.execute("SELECT COUNT(*), SUM(total_price) FROM bookings WHERE returned = 0")
    active, revenue = c.fetchone()
    
    now = datetime.now().isoformat()
    c.execute("SELECT COUNT(*) FROM bookings WHERE returned = 0 AND return_datetime < ?", (now,))
    overdue = c.fetchone()[0]
    
    conn.close()
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            "total_items": total_items or 0,
            "active_bookings": active or 0,
            "total_revenue": revenue or 0,
            "available_items": available or 0,
            "overdue_bookings": overdue or 0
        })
    }

def get_bookings():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT b.*, i.name as item_name 
        FROM bookings b 
        JOIN inventory i ON b.item_id = i.id 
        ORDER BY b.booked_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(rows)
    }

def return_booking(booking_id):
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT item_id, quantity FROM bookings WHERE id = ? AND returned = 0", (booking_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        return {'statusCode': 404, 'body': 'Not found'}
    
    c.execute("UPDATE inventory SET available_quantity = available_quantity + ? WHERE id = ?", 
              (r["quantity"], r["item_id"]))
    c.execute("UPDATE bookings SET returned = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    
    return {'statusCode': 200, 'body': json.dumps({'ok': True})}

def get_inventory():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM inventory ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(rows)
    }

def add_inventory(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO inventory (name, sport, total_quantity, available_quantity, price_per_hour, price_per_day)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data["name"], data["sport"], data["total_quantity"], data["total_quantity"], 
          data["price_per_hour"], data["price_per_day"]))
    conn.commit()
    conn.close()
    
    return {'statusCode': 200, 'body': json.dumps({'ok': True, 'id': c.lastrowid})}

def delete_inventory(item_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM bookings WHERE item_id = ? AND returned = 0", (item_id,))
    if c.fetchone()[0] > 0:
        conn.close()
        return {'statusCode': 400, 'body': 'Has active bookings'}
    
    c.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    
    return {'statusCode': 200, 'body': json.dumps({'ok': True})}

def update_inventory(item_id, data):
    conn = get_db()
    c = conn.cursor()
    
    if 'price_per_hour' in data:
        c.execute("UPDATE inventory SET price_per_hour = ? WHERE id = ?", (data['price_per_hour'], item_id))
    if 'price_per_day' in data:
        c.execute("UPDATE inventory SET price_per_day = ? WHERE id = ?", (data['price_per_day'], item_id))
    
    conn.commit()
    conn.close()
    return {'statusCode': 200, 'body': json.dumps({'ok': True})}

# Для локального тестирования
if __name__ == "__main__":
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            response = handler({'path': self.path, 'method': 'GET'})
            self.send_response(response['statusCode'])
            for k, v in response.get('headers', {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(response['body'].encode())
        
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()
            response = handler({'path': self.path, 'method': 'POST', 'body': body})
            self.send_response(response['statusCode'])
            self.end_headers()
            self.wfile.write(response['body'].encode())
    
    print("Local server: http://localhost:8000")
    HTTPServer(('localhost', 8000), Handler).serve_forever()