# api/index.py
from flask import Flask, request, jsonify
import sqlite3
import json
from datetime import datetime

app = Flask(__name__)

DB_PATH = "/tmp/rent_bot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
        </div>

        <div class="glass rounded-xl p-1 mb-4 flex">
            <button @click="tab = 'bookings'" :class="tab === 'bookings' ? 'bg-purple-600 text-white' : 'text-gray-400'" class="flex-1 py-2 rounded-lg text-sm font-medium">Брони</button>
            <button @click="tab = 'inventory'" :class="tab === 'inventory' ? 'bg-purple-600 text-white' : 'text-gray-400'" class="flex-1 py-2 rounded-lg text-sm font-medium">Склад</button>
        </div>

        <div x-show="tab === 'bookings'" class="space-y-3">
            <template x-for="b in bookings" :key="b.id">
                <div class="glass rounded-xl p-4">
                    <div class="flex justify-between mb-2">
                        <div class="font-semibold" x-text="b.item_name"></div>
                        <div class="text-green-400 font-bold"><span x-text="b.total_price.toLocaleString()"></span> ₸</div>
                    </div>
                    <div class="flex justify-between items-center">
                        <div class="text-xs text-gray-400">ID: <span x-text="b.user_id"></span></div>
                        <button @click="returnBooking(b.id)" x-show="!b.returned" class="px-3 py-1 bg-blue-600 text-white rounded text-xs">Вернуть</button>
                        <span x-show="b.returned" class="text-xs text-gray-500">Возвращено</span>
                    </div>
                </div>
            </template>
        </div>

        <div x-show="tab === 'inventory'" class="space-y-3">
            <template x-for="item in inventory" :key="item.id">
                <div class="glass rounded-xl p-4">
                    <div class="flex justify-between mb-2">
                        <div class="font-semibold" x-text="item.name"></div>
                        <div :class="item.available_quantity > 0 ? 'text-green-400' : 'text-red-400'">
                            <span x-text="item.available_quantity"></span>/<span x-text="item.total_quantity"></span>
                        </div>
                    </div>
                    <div class="text-xs text-gray-400">
                        Час: <span x-text="item.price_per_hour"></span> ₸ | 
                        День: <span x-text="item.price_per_day"></span> ₸
                    </div>
                </div>
            </template>
        </div>
    </div>

    <script>
        function app() {
            return {
                tab: 'bookings',
                stats: { total_revenue: 0, active_bookings: 0 },
                bookings: [],
                inventory: [],
                
                init() {
                    this.loadData();
                    setInterval(() => this.loadData(), 10000);
                },
                
                async loadData() {
                    const [s, b, i] = await Promise.all([
                        fetch('/api/stats').then(r => r.json()),
                        fetch('/api/bookings').then(r => r.json()),
                        fetch('/api/inventory').then(r => r.json())
                    ]);
                    this.stats = s;
                    this.bookings = b;
                    this.inventory = i;
                },
                
                async returnBooking(id) {
                    if (!confirm('Вернуть?')) return;
                    await fetch(`/api/bookings/${id}/return`, { method: 'POST' });
                    this.loadData();
                }
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    init_db()
    return HTML_PAGE

@app.route('/api/stats')
def get_stats():
    init_db()
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
    return jsonify({
        "total_items": total_items or 0,
        "active_bookings": active or 0,
        "total_revenue": revenue or 0,
        "available_items": available or 0,
        "overdue_bookings": overdue or 0
    })

@app.route('/api/bookings')
def get_bookings():
    init_db()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT b.*, i.name as item_name FROM bookings b JOIN inventory i ON b.item_id = i.id ORDER BY b.booked_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/bookings/<int:booking_id>/return', methods=['POST'])
def return_booking(booking_id):
    init_db()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT item_id, quantity FROM bookings WHERE id = ? AND returned = 0", (booking_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    c.execute("UPDATE inventory SET available_quantity = available_quantity + ? WHERE id = ?", (r["quantity"], r["item_id"]))
    c.execute("UPDATE bookings SET returned = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route('/api/inventory')
def get_inventory():
    init_db()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM inventory ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)
