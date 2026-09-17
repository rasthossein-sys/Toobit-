import asyncio
import logging
import os
from typing import Dict, Any, Optional
import aiohttp
import ccxt.async_support as ccxt  # استفاده از نسخه ناهمگام ccxt برای سرعت بالا در سرور

# --- تنظیمات سیستم لاگینگ برای سرور ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("ToobitCCXTHunter")

# --- موتور تحلیلگر پیشرفته با پشتیبانی CCXT ---
class CCXTHunterEngine:
    def __init__(self):
        # راه‌اندازی صرافی تووبیت از طریق کتابخانه استاندارد CCXT
        self.exchange = ccxt.toobit({
            'enableRateLimit': True,
        })

    async def close(self):
        await self.exchange.close()

    async def analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        formatted_symbol = f"{symbol.upper()}/USDT"
        btc_symbol = "BTC/USDT"
        
        try:
            # دریافت اطلاعات تیکر بیت‌کوین برای بررسی همبستگی کلان بازار
            btc_ticker = await self.exchange.fetch_ticker(btc_symbol)
            btc_change = float(btc_ticker.get('percentage', 0.0) or 0.0)

            # دریافت اطلاعات تیکر ارز مورد نظر
            ticker = await self.exchange.fetch_ticker(formatted_symbol)
            
            current_price = float(ticker.get('last', 0.0))
            high_price = float(ticker.get('high', current_price))
            low_price = float(ticker.get('low', current_price))
            price_change = float(ticker.get('percentage', 0.0) or 0.0)

            if current_price == 0:
                return {"status": "ERROR", "message": "قیمت نامعتبر است."}

            # محاسبات فیبوناچی اصلاحی
            diff = high_price - low_price
            fib_0382 = round(high_price - (diff * 0.382), 2)
            fib_0618 = round(high_price - (diff * 0.618), 2)

            # تشخیص وضعیت پامپ/دامپ و استاپ‌هانت
            market_condition = "نرمال و با ثبات"
            if btc_change <= -2.5:
                market_condition = "⚠️ دامپ شدید بازار (ریزش سنگین بیت‌کوین)"
            elif btc_change >= 2.5:
                market_condition = "🚀 پامپ و رشد پرقدرت بازار (پیشروی بیت‌کوین)"

            high_threshold = high_price * 0.995
            low_threshold = low_price * 1.005
            trap_type = "معمولی (بدون تله سنگین نهنگ)"
            
            if current_price <= low_threshold:
                trap_type = "🛑 تله نزولی / استاپ‌هانت لانگ‌ (Bear Trap / Long Liquidity Sweep)"
            elif current_price >= high_threshold:
                trap_type = "🚨 تله صعودی / استاپ‌هانت شورت‌ (Bull Trap / Short Liquidity Sweep)"

            return {
                "status": "SUCCESS",
                "symbol": formatted_symbol,
                "price": current_price,
                "change_24h": price_change,
                "market_condition": market_condition,
                "trap_description": trap_type,
                "fib_0382": fib_0382,
                "fib_0618": fib_0618,
                "entry": fib_0618,
                "sl": round(low_price * 0.985, 2),
                "tp": round(high_price * 1.02, 2)
            }

        except Exception as e:
            logger.error(f"خطا در تحلیل CCXT برای {symbol}: {e}")
            return {"status": "ERROR", "message": f"خطا: نماد `{symbol}` در صرافی تووبیت یافت نشد یا در دسترس نیست."}

# --- مدیریت ارتباط با تلگرام ---
class TelegramBotHandler:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.engine = CCXTHunterEngine()

    async def send_message(self, session: aiohttp.ClientSession, chat_id: int, text: str):
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            async with session.post(url, json=payload, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"خطا در ارسال پیام تلگرام: {await response.text()}")
        except Exception as e:
            logger.error(f"خطای ارتباط با تلگرام: {e}")

    async def get_updates(self, session: aiohttp.ClientSession, offset: Optional[int] = None) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/getUpdates"
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset
        try:
            async with session.get(url, params=params, timeout=35) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result", [])
        except Exception as e:
            logger.error(f"خطا در دریافت آپدیت‌های تلگرام: {e}")
        return []

    async def run(self):
        logger.info("ربات شکارچی حرفه‌ای مجهز به CCXT آماده به‌کار است...")
        offset = None
        
        async with aiohttp.ClientSession() as session:
            while True:
                updates = await self.get_updates(session, offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    message = update.get("message")
                    if not message or "text" not in message:
                        continue
                        
                    chat_id = message["chat"]["id"]
                    text = message["text"].strip().upper()

                    if text.startswith("/START"):
                        welcome_msg = (
                            "🎯 **ربات شکارچی حرفه‌ای بازار (Toobit CCXT Pro Edition)**\n\n"
                            "نام هر ارز را بفرستید (مثلا `BTC`، `ETH` یا `SOL`) تا تحلیل دقیق صرافی با کتابخانه CCXT شامل:\n"
                            "🔹 **استاپ‌هانت و تله نهنگ**\n"
                            "🔹 **بررسی پامپ و دامپ بیت‌کوین**\n"
                            "🔹 **سطوح فیبوناچی استاندارد (0.618)**\n"
                            "به صورت آنی برایتان ارسال شود."
                        )
                        await self.send_message(session, chat_id, welcome_msg)
                        continue

                    coin = text.replace("USDT", "").strip()
                    await self.send_message(session, chat_id, f"🔍 در حال اسکن حرفه‌ای بازار با موتور CCXT برای `{coin}/USDT`...")
                    
                    analysis = await self.engine.analyze_symbol(coin)
                    
                    if analysis["status"] == "ERROR":
                        await self.send_message(session, chat_id, analysis["message"])
                        continue

                    report = (
                        f"📊 **گزارش تخصصی CCXT برای `{analysis['symbol']}`**\n\n"
                        f"💰 قیمت لحظه‌ای: `{analysis['price']}` (تغییر 24h: `{analysis['change_24h']}%`)\n"
                        f"🌐 وضعیت کلان بازار: `{analysis['market_condition']}`\n\n"
                        f"🚨 **وضعیت تله و استاپ‌هانت:**\n`{analysis['trap_description']}`\n\n"
                        f"📐 **سطوح فیبوناچی اصلاحی:**\n"
                        f"  • سطح 0.382: `{analysis['fib_0382']}`\n"
                        f"  • **سطح طلایی ورود (0.618):** `{analysis['fib_0618']}`\n\n"
                        f"📍 **نقطه ورود پیشنهادی:** `{analysis['entry']}`\n"
                        f"🛑 **حد ضرر (SL):** `{analysis['sl']}`\n"
                        f"✅ **تیک پروفیت (TP):** `{analysis['tp']}`\n\n"
                        f"⚠️ *پردازش‌شده به صورت ابری با موتور استاندارد صرافی.*"
                    )
                    
                    await self.send_message(session, chat_id, report)
                
                await asyncio.sleep(1)

async def main():
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        logger.critical("متغیر محیطی TELEGRAM_TOKEN تنظیم نشده است!")
        return

    bot_handler = TelegramBotHandler(TELEGRAM_TOKEN)
    try:
        await bot_handler.run()
    finally:
        await bot_handler.engine.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("ربات متوقف شد.")
      
