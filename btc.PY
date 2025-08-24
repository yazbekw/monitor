from flask import Flask, jsonify
import threading
import time
import yfinance as yf
import numpy as np
from datetime import datetime
import requests
import pytz
import os

app = Flask(__name__)

# ========== إعدادات Telegram ==========
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# ========== إعدادات التداول ==========
ASSETS = ["BTC-USD", "ETH-USD", "BNB-USD", "ADA-USD", "XRP-USD"]
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

# ========== أوقات التشغيل ==========
TRADING_SCHEDULE = [
    # أوقات الشراء
    {"type": "buy", "days": ["tuesday", "wednesday", "thursday"], "time": "01:00"},
    {"type": "buy", "days": ["tuesday", "wednesday", "thursday"], "time": "15:00"},
    {"type": "buy", "days": ["monday", "friday"], "time": "13:00"},
    {"type": "buy", "days": ["sunday", "saturday"], "time": "01:00"},
    {"type": "buy", "days": ["saturday"], "time": "16:00"},
    
    # أوقات البيع
    {"type": "sell", "days": ["sunday", "monday"], "time": "17:00"},
    {"type": "sell", "days": ["monday"], "time": "00:00"},
    {"type": "sell", "days": ["monday"], "time": "07:00"},
    {"type": "sell", "days": ["friday"], "time": "00:00"},
    {"type": "sell", "days": ["friday"], "time": "05:00"},
    {"type": "sell", "days": ["saturday"], "time": "21:00"},
    {"type": "sell", "days": ["tuesday", "wednesday", "thursday"], "time": "08:00"}
]

def send_telegram_message(message):
    """إرسال رسالة عبر Telegram"""
    if len(message) > 4000:
        message = message[:4000] + "..."
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except:
        return False

def calculate_rsi(prices, period=14):
    """حساب مؤشر RSI"""
    if len(prices) < period + 1:
        return np.array([50] * len(prices))
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gains = np.zeros_like(prices)
    avg_losses = np.zeros_like(prices)
    
    avg_gains[period] = np.mean(gains[:period])
    avg_losses[period] = np.mean(losses[:period])
    
    if avg_losses[period] == 0:
        avg_losses[period] = 0.0001
    
    for i in range(period + 1, len(prices)):
        avg_gains[i] = (avg_gains[i-1] * (period-1) + gains[i-1]) / period
        avg_losses[i] = (avg_losses[i-1] * (period-1) + losses[i-1]) / period
        
        if avg_losses[i] == 0:
            avg_losses[i] = 0.0001
    
    rs = avg_gains / avg_losses
    rsi = 100 - (100 / (1 + rs))
    rsi[:period] = 50
    
    return rsi

def get_market_data(symbol):
    """جلب بيانات السوق"""
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="1mo", interval="1d")
        
        if len(hist) < 15:
            return None, None, None
            
        current_price = hist['Close'].iloc[-1]
        rsi_values = calculate_rsi(hist['Close'].values)
        current_rsi = rsi_values[-1]
        
        prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        price_change = ((current_price - prev_price) / prev_price) * 100
        
        return current_price, current_rsi, price_change
        
    except:
        return None, None, None

def get_rsi_recommendation(rsi, is_buy_time):
    """الحصول على توصية بناءً على RSI"""
    if is_buy_time:
        if rsi < 30: return "شراء قوي جداً", "🎯", "🟢"
        elif rsi < 35: return "شراء قوي", "👍", "🟢"
        elif rsi < 40: return "شراء جيد", "📈", "🟡"
        else: return "تجنب الشراء", "⚠️", "🔴"
    else:
        if rsi > 70: return "بيع قوي جداً", "🎯", "🟢"
        elif rsi > 65: return "بيع قوي", "👍", "🟢"
        elif rsi > 60: return "بيع جيد", "📈", "🟡"
        else: return "تجنب البيع", "⚠️", "🔴"

def check_trading_time():
    """التحقق إذا كان الوقت مناسب للتداول"""
    now = datetime.now(DAMASCUS_TZ)
    current_time = now.strftime("%H:%M")
    current_day = now.strftime("%A").lower()
    
    for slot in TRADING_SCHEDULE:
        if current_day in slot["days"] and current_time == slot["time"]:
            return True, slot["type"]
    
    return False, None

def run_trading_bot():
    """تشغيل بوت التداول في الخلفية"""
    while True:
        try:
            should_trade, trade_type = check_trading_time()
            
            if should_trade:
                now = datetime.now(DAMASCUS_TZ)
                current_time = now.strftime("%Y-%m-%d %H:%M")
                
                action = "شراء" if trade_type == "buy" else "بيع"
                action_emoji = "🟢" if trade_type == "buy" else "🔴"
                
                message = f"{action_emoji} <b>إشعار تداول - وقت {action}</b>\n"
                message += f"⏰ <i>{current_time}</i>\n"
                message += "─" * 30 + "\n\n"
                
                assets_analyzed = 0
                
                for symbol in ASSETS:
                    data = get_market_data(symbol)
                    if all(x is not None for x in data):
                        price, rsi, change = data
                        assets_analyzed += 1
                        
                        rec_text, rec_emoji, color_emoji = get_rsi_recommendation(rsi, trade_type == "buy")
                        change_emoji = "📈" if change >= 0 else "📉"
                        change_sign = "+" if change >= 0 else ""
                        
                        message += f"{color_emoji} <b>{symbol}</b>\n"
                        message += f"💰 السعر: ${price:,.2f} {change_emoji} {change_sign}{change:.2f}%\n"
                        message += f"📊 RSI: {rsi:.1f} - {rec_emoji} {rec_text}\n"
                        message += "─" * 20 + "\n"
                
                if assets_analyzed > 0:
                    message += f"\n📋 <i>تم تحليل {assets_analyzed} أصل</i>"
                    send_telegram_message(message)
                    print(f"✅ تم إرسال تحليل {assets_analyzed} أصل - {current_time}")
            
            time.sleep(60)  # التحقق كل دقيقة
            
        except Exception as e:
            print(f"❌ خطأ في البوت: {e}")
            time.sleep(300)  # انتظار 5 دقائق عند الخطأ

@app.route('/')
def home():
    """الصفحة الرئيسية للتحقق من حالة الخدمة"""
    return jsonify({
        "status": "active",
        "service": "Trading Bot",
        "assets": ASSETS,
        "last_checked": datetime.now(DAMASCUS_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/health')
def health_check():
    """ endpoint للتحقق من الصحة لـ UptimeRobot"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/status')
def status():
    """عرض حالة البوت"""
    now = datetime.now(DAMASCUS_TZ)
    should_trade, trade_type = check_trading_time()
    
    return jsonify({
        "status": "running",
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "should_trade": should_trade,
        "trade_type": trade_type,
        "next_check": "every_minute"
    })

@app.route('/test-notification')
def test_notification():
    """اختبار إرسال إشعار"""
    success = send_telegram_message("🔧 <b>اختبار الإشعار</b>\n✅ الخدمة تعمل بشكل صحيح")
    return jsonify({"success": success, "message": "Test notification sent"})

def start_bot():
    """بدء تشغيل البوت في thread منفصل"""
    bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    bot_thread.start()
    print("✅ بدأ تشغيل بوت التداول في الخلفية")

if __name__ == '__main__':
    # بدء البوت عند التشغيل
    start_bot()
    
    # إرسال رسالة بدء التشغيل
    send_telegram_message("🚀 <b>تم تشغيل بوت التداول</b>\n⏰ جاري المراقبة التلقائية")
    
    # تشغيل Flask
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
