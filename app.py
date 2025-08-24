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

# إعدادات الأساسية
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ASSETS = ["BTC-USD", "ETH-USD", "AAPL", "MSFT", "TSLA"]
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

def send_telegram_message(message):
    """إرسال رسالة عبر Telegram"""
    try:
        if len(message) > 4000:
            message = message[:4000] + "..."
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except:
        return False

def calculate_rsi_simple(prices, period=14):
    """حساب RSI مبسط"""
    if len(prices) < period + 1:
        return 50
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return 100 if avg_gain > 0 else 50
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_market_data(symbol):
    """جلب بيانات السوق"""
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="15d", interval="1d")
        
        if len(hist) < 2:
            return None, None, None
            
        current_price = hist['Close'].iloc[-1]
        rsi = calculate_rsi_simple(hist['Close'].values)
        
        prev_price = hist['Close'].iloc[-2]
        price_change = ((current_price - prev_price) / prev_price) * 100
        
        return current_price, rsi, price_change
        
    except Exception as e:
        print(f"Error with {symbol}: {e}")
        return None, None, None

def get_rsi_recommendation(rsi, is_buy_time):
    """توصيات RSI"""
    if is_buy_time:
        if rsi < 30: return "شراء قوي جداً", "🎯"
        elif rsi < 35: return "شراء قوي", "👍"
        elif rsi < 40: return "شراء جيد", "📈"
        else: return "تجنب الشراء", "⚠️"
    else:
        if rsi > 70: return "بيع قوي جداً", "🎯"
        elif rsi > 65: return "بيع قوي", "👍"
        elif rsi > 60: return "بيع جيد", "📈"
        else: return "تجنب البيع", "⚠️"

def should_trade_now():
    """التحقق من وقت التداول"""
    now = datetime.now(DAMASCUS_TZ)
    current_time = now.strftime("%H:%M")
    current_day = now.strftime("%A").lower()
    
    # أوقات الشراء
    buy_times = [
        {"days": ["tuesday", "wednesday", "thursday"], "time": "01:00"},
        {"days": ["tuesday", "wednesday", "thursday"], "time": "15:00"},
        {"days": ["monday", "friday"], "time": "13:00"},
        {"days": ["sunday", "saturday"], "time": "01:00"},
        {"days": ["saturday"], "time": "16:00"}
    ]
    
    # أوقات البيع
    sell_times = [
        {"days": ["sunday", "monday"], "time": "17:00"},
        {"days": ["monday"], "time": "00:00"},
        {"days": ["monday"], "time": "07:00"},
        {"days": ["friday"], "time": "00:00"},
        {"days": ["friday"], "time": "05:00"},
        {"days": ["saturday"], "time": "21:00"},
        {"days": ["tuesday", "wednesday", "thursday"], "time": "08:00"}
    ]
    
    for slot in buy_times:
        if current_day in slot["days"] and current_time == slot["time"]:
            return True, "buy"
    
    for slot in sell_times:
        if current_day in slot["days"] and current_time == slot["time"]:
            return True, "sell"
    
    return False, None

def trading_bot_loop():
    """حلقة البوت الرئيسية"""
    while True:
        try:
            trade_now, trade_type = should_trade_now()
            
            if trade_now:
                now = datetime.now(DAMASCUS_TZ)
                current_time = now.strftime("%Y-%m-%d %H:%M")
                
                action = "شراء" if trade_type == "buy" else "بيع"
                message = f"🕒 <b>وقت {action}</b>\n⏰ {current_time}\n\n"
                
                for symbol in ASSETS:
                    data = get_market_data(symbol)
                    if all(x is not None for x in data):
                        price, rsi, change = data
                        rec_text, rec_emoji = get_rsi_recommendation(rsi, trade_type == "buy")
                        change_emoji = "📈" if change >= 0 else "📉"
                        
                        message += f"• <b>{symbol}</b>\n"
                        message += f"  💰 ${price:,.2f} {change_emoji} {change:+.2f}%\n"
                        message += f"  📊 RSI: {rsi:.1f} - {rec_emoji} {rec_text}\n\n"
                
                if len(message) > 100:  # إذا كان هناك بيانات
                    send_telegram_message(message)
                    print(f"✅ تم إرسال إشعار: {current_time}")
            
            time.sleep(60)  # التحقق كل دقيقة
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            time.sleep(300)

@app.route('/')
def home():
    return jsonify({
        "status": "active", 
        "service": "Trading Bot",
        "time": datetime.now(DAMASCUS_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/test')
def test():
    success = send_telegram_message("✅ <b>اختبار ناجح</b>\nالخدمة تعمل بشكل صحيح")
    return jsonify({"success": success})

if __name__ == '__main__':
    # بدء البوت في thread منفصل
    bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
    bot_thread.start()
    
    # إرسال رسالة بدء التشغيل
    send_telegram_message("🚀 <b>تم تشغيل البوت</b>\nجاري المراقبة التلقائية")
    
    # تشغيل الخادم
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
