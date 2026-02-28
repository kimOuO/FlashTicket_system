import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from utils import NTPSynchronizer, BezierMouse, CaptchaProcessor

# 配置 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FlashTicket-Visual")

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
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5] 
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-TW', 'zh', 'en-US', 'en']
        });
    """)

async def wait_for_trigger(target_ts):
    """精準計時等待"""
    while True:
        now = ntp_sync.get_precise_time()
        remaining = target_ts - now
        
        if remaining <= 0:
            break
        
        if remaining > 1.0:
            await asyncio.sleep(remaining - 0.5)
        elif remaining > 0.01:
            await asyncio.sleep(remaining * 0.8)
        else:
            pass

async def visual_attack(context, account):
    """全自動瀏覽器操作模式 (可視化)"""
    page = await context.new_page()
    await stealth_setup(page)
    
    # 這裡不攔截資源，方便觀察 (若要加速可開啟)
    # await page.route("**/*", block_resources)
    
    try:
        logger.info(f"[{account['username']}] 1. 進入區域選擇頁...")
        await page.goto(CONFIG['target_url']) # 預設為 /progress
        
        # 等待並點擊第一個區域
        try:
            await page.wait_for_selector(CONFIG['selectors']['area_item'], timeout=5000)
            areas = await page.locator(CONFIG['selectors']['area_item']).all()
            if areas:
                target_area = areas[0]
                logger.info(f"點擊區域: {await target_area.inner_text()}")
                await target_area.click()
            else:
                logger.error("沒找到區域按鈕！")
                return
        except Exception as e:
            logger.error(f"選區失敗: {e}")
            return

        # 等待表單頁面載入
        await page.wait_for_url("**/checking*")
        logger.info(f"[{account['username']}] 2. 成功進入表單頁，等待倒數...")

        # 計算目標時間
        target_dt = datetime.fromisoformat(CONFIG['target_time_iso'])
        if target_dt.tzinfo is None:
             target_ts = target_dt.timestamp()
        else:
             target_ts = target_dt.timestamp()

        # 等待直到目標時間
        logger.info(f"目標時間: {target_dt} (剩餘 {target_ts - ntp_sync.get_precise_time():.2f} 秒)")
        await wait_for_trigger(target_ts - CONFIG['lead_time_seconds'])

        logger.info(f"[{account['username']}] 3. 時間到！開始填寫與提交！")
        
        # 極速填寫邏輯
        # 1. 選擇張數
        await page.select_option(CONFIG['selectors']['quantity_select'], "1")
        
        # 2. 勾選條款
        await page.check(CONFIG['selectors']['terms_checkbox'])
        
        # 3. 處理驗證碼 (改為手動輸入或簡單提示)
        try:
            # 嘗試等待驗證碼圖片出現
            captcha_elem = await page.wait_for_selector(CONFIG['selectors']['captcha_img'], timeout=2000)
            if captcha_elem:
                # 聚焦到驗證碼輸入框，方便使用者直接輸入
                await page.focus(CONFIG['selectors']['captcha_input'])
                
                # 播放提示音 (Windows) 或打印巨大的提示
                logger.warning("!!! 請輸入驗證碼 !!!")
                logger.warning("!!! 請輸入驗證碼 !!!")
                logger.warning("!!! 請輸入驗證碼 !!!")
                import winsound
                winsound.Beep(1000, 500) # 頻率 1000Hz，持續 0.5 秒

                # 在這裡我們可以選擇等待使用者輸入，或者用一個無限迴圈檢查輸入框是否有值
                # 為了搶票速度，這裡建議由使用者手動輸入後，手動按 Enter (或者我們偵測輸入長度)
                
                # 方案 A: 等待使用者在 input 框輸入至少 4 碼 (假設驗證碼長度)
                # await page.wait_for_function(f"document.querySelector('{CONFIG['selectors']['captcha_input']}').value.length >= 4")
                
                # 方案 B: 使用者自行輸入並按下提交，程式不干涉驗證碼部分，只負責前面的勾選
                logger.info("已聚焦輸入框，請手動輸入驗證碼並提交 (程式會繼續監視結果)...")
                
                # 修改邏輯：等待使用者輸入滿 4 碼 (假設驗證碼長度) 後自動提交，或者讓使用者自己按 Enter
                # 這裡改成：偵測到使用者按下 Enter 鍵，或點擊了提交按鈕後，程式才繼續後續的截圖/紀錄
                
                # 等待導航發生 (代表使用者送出了表單)
                await page.wait_for_url("**/loading*", timeout=60000) # 給使用者 60 秒輸入
                logger.info("檢測到頁面跳轉，使用者已提交驗證碼！")
                
                # 跳過原本的自動點擊，直接進入結果判斷
                # (因為使用者手動提交了)
                pass 

        except Exception as e:
             logger.info(f"驗證碼處理或等待提交時發生狀況 (或無驗證碼): {e}")
             # 如果沒有驗證碼，或者等待超時，嘗試自動點擊提交
             submit_btn = page.locator(CONFIG['selectors']['submit_btn'])
             await submit_btn.click()
             logger.info(f"[{account['username']}] 4. 嘗試自動點擊提交按鈕！")

        # 等待結果頁面 (觀察用)
        try:
            await page.wait_for_url("**/loading*", timeout=5000)
            logger.info("成功跳轉至 loading 頁面，搶票成功！")
            await asyncio.sleep(10) 
            # 截取成功畫面證據
            filename = f"success_{account['username']}_{int(datetime.now().timestamp())}.png"
            await page.screenshot(path=filename)
            logger.info(f"已保存成功截圖：{filename}")

            # 保持瀏覽器開啟一段時間以供觀察
            # await asyncio.sleep(10)  # 因為外層有等待，這裡可以不用暫停太久
        except:
            logger.warning("未檢測到跳轉，可能失敗或網路延遲。請手動檢查頁面。")
            await page.screenshot(path="failed_evidence.png")
            # await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"流程異常: {e}")
    # finally:
        # await page.close()  # 不自動關閉頁面，讓使用者可以繼續操作

async def main():
    async with async_playwright() as p:
        # headless=False 讓瀏覽器視窗跳出來，方便手動輸入付款資訊
        browser = await p.chromium.launch(
            headless=False, 
            args=["--start-maximized"] # 最大化視窗
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            no_viewport=True
        )

        # 這裡帳號結構不同，需要提取第一個帳號物件
        task = visual_attack(context, CONFIG['accounts'][0])
        await task

        logger.info("自動化流程結束，保留視窗以供操作...")
        try:
            # 等待使用者按 Enter 結束
            # 使用 run_in_executor 避免阻塞事件迴圈
            await asyncio.get_event_loop().run_in_executor(None, input, "請在完成付款後，按 Enter 鍵關閉瀏覽器...")
        except:
            pass
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
