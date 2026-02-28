import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from utils import NTPSynchronizer, BezierMouse, CaptchaProcessor, NetworkUtils

# 配置 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FlashTicket")

# 載入配置
with open('config.json', 'r') as f:
    CONFIG = json.load(f)

# 初始化 NTP
ntp_sync = NTPSynchronizer()
ntp_sync.sync()

async def block_resources(route):
    """攔截不必要的資源請求，極大化速度"""
    if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
        await route.abort()
    elif "google-analytics" in route.request.url or "facebook" in route.request.url:
        await route.abort() # 阻擋追蹤器
    else:
        await route.continue_()

async def stealth_setup(page):
    """進階 Stealth 設置：覆蓋 navigator.webdriver 等特徵"""
    # 使用 CDP (Chrome DevTools Protocol) 移除 webdriver 標記
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        // 偽造 plugin 列表
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5] 
        });
        // 偽造語言
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-TW', 'zh', 'en-US', 'en']
        });
    """)

async def human_like_fill(page, selector, text):
    """擬人化輸入：隨機間隔輸入"""
    box = await page.locator(selector).bounding_box()
    if box:
        # 使用貝茲曲線移動滑鼠
        start_x, start_y = random.randint(0, 100), random.randint(0, 100)
        path = BezierMouse.get_path((start_x, start_y), (box['x'] + 10, box['y'] + 10))
        for point in path:
            await page.mouse.move(point[0], point[1])
            await asyncio.sleep(0.001) # 極短暫延遲

    await page.click(selector)
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.005, 0.03)) # 快速但隨機的打字延遲

async def process_account(context, account):
    """處理搶票流程初始化：進入區域選擇並準備表單"""
    page = await context.new_page()
    await stealth_setup(page)
    
    # 開啟請求攔截
    await page.route("**/*", block_resources)
    
    try:
        logger.info(f"[{account['username']}] 開始初始化流程...")
        # 1. 進入區域選擇頁面 (Target URL 應為 /progress)
        await page.goto(CONFIG['target_url'], wait_until='domcontentloaded')
        
        # 針對 Ticket Training 網站的特殊邏輯：選擇區域
        try:
            logger.info("正在尋找區域按鈕...")
            # 等待任一 .seat-item 出現
            await page.wait_for_selector(CONFIG['selectors']['area_item'], timeout=5000)
            areas = await page.locator(CONFIG['selectors']['area_item']).all()
            
            if areas:
                target_area = areas[0]
                logger.info(f"點擊區域: {await target_area.inner_text()}")
                await target_area.click()
                
                # 等待進入 /checking 頁面
                await page.wait_for_url("**/checking*", timeout=5000)
                logger.info(f"成功進入訂單頁面: {page.url}")
            else:
                logger.warning("未找到任何可選區域(area_item)。")

        except Exception as e:
            logger.warning(f"區域選擇步驟異常: {e}")

        # 獲取 Cookies 與 Session 用於後續 API 併發
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        ua = await page.evaluate("navigator.userAgent")
        
        logger.info(f"[{account['username']}] Session 提取成功，準備進行 API 攻擊。")
        return {
            "username": account['username'],
            "cookies": cookie_dict,
            "user_agent": ua
        }

    except Exception as e:
        logger.error(f"[{account['username']}] 初始化失敗: {e}")
        return None
    finally:
        await page.close()

async def wait_for_trigger(target_ts):
    """精準計時等待"""
    while True:
        now = ntp_sync.get_precise_time()
        remaining = target_ts - now
        
        if remaining <= 0:
            break
        
        # 如果剩餘時間很多，sleep 較長時間，否則進入 busy loop
        if remaining > 1.0:
            await asyncio.sleep(remaining - 0.5)
        elif remaining > 0.01:
            await asyncio.sleep(remaining * 0.8)
        else:
            # 最後 10ms 內使用 busy wait 以達到微秒級準度
            pass

async def api_attack(session_data):
    """API 層級的高併發請求 (模擬搶購/提交)"""
    if not session_data:
        return

    # 計算目標時間
    target_dt = datetime.fromisoformat(CONFIG['target_time_iso'])
    
    # 修正：直接將輸入視為本地時間，取得 timestamp
    # 如果沒有 tzinfo，視為本地時間
    if target_dt.tzinfo is None:
        target_ts = target_dt.timestamp()
    else:
        target_ts = target_dt.timestamp()
    
    # 提前量 (Lead Time) 補償網路延遲
    trigger_ts = target_ts - CONFIG['lead_time_seconds']

    logger.info(f"[{session_data['username']}] 等待觸發時間: {target_dt} (Unix: {trigger_ts})")
    await wait_for_trigger(trigger_ts)
    
    # 構建請求 Payload
    # 針對 Ticket Training: GET /loading?quantity=1&terms=on
    payload = {
        "quantity": "1",
        "terms": "on"
    }
    
    method = CONFIG.get("method", "POST") # 支援配置 method

    for attempt in range(CONFIG['max_retries'] + 1):
        status, resp_text = await NetworkUtils.submit_with_ja3(
            CONFIG['api_endpoint'],
            headers={"User-Agent": session_data['user_agent']},
            cookies=session_data['cookies'],
            data=payload,
            method=method
        )
        
        if status == 200:
            logger.info(f"[{session_data['username']}] 請求成功! 回應: {resp_text[:50]}...")
            break
        elif status in [429, 503]:
            logger.warning(f"[{session_data['username']}] 伺服器忙碌 ({status})。第 {attempt} 次重試...")
            await NetworkUtils.exponential_backoff(attempt)
        else:
            logger.error(f"[{session_data['username']}] 請求失敗 ({status})。")
            break

async def main():
    async with async_playwright() as p:
        # 使用 Firefox 或 Chrome
        browser = await p.chromium.launch(
            headless=True,  # 設為 False 可觀察行為
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        
        context = await browser.new_context(
            user_agent=CONFIG['headers']['User-Agent'],
            viewport={'width': 1920, 'height': 1080}
        )

        # 1. 準備階段：並行處理所有帳號登入/初始化
        logger.info("開始平行初始化...")
        login_tasks = [process_account(context, acc) for acc in CONFIG['accounts']]
        sessions = await asyncio.gather(*login_tasks)
        
        valid_sessions = [s for s in sessions if s]
        logger.info(f"成功獲取 {len(valid_sessions)} 個有效 Session。")

        # 2. 攻擊階段：並行等待並發射
        if valid_sessions:
            logger.info("系統準備就緒，進入發射倒數...")
            attack_tasks = [api_attack(s) for s in valid_sessions]
            await asyncio.gather(*attack_tasks)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
