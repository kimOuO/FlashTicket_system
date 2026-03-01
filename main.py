import asyncio
import json
import logging
from datetime import datetime
from playwright.async_api import async_playwright
import ddddocr
from utils import NTPSynchronizer

# 配置 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FlashTicket-Main")

# 初始化 ddddocr
try:
    ocr = ddddocr.DdddOcr(show_ad=False)
except Exception as e:
    logger.error(f"初始化 ddddocr 失敗: {e}")
    ocr = None

# 載入配置
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    logger.error("找不到 config.json！")
    exit(1)

# 初始化 NTP
ntp_sync = NTPSynchronizer()
ntp_sync.sync()

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

async def solve_captcha_with_ocr(page, selector):
    """使用 ddddocr 自動辨識驗證碼 (超輕量、無須額外安裝軟體)"""
    if not ocr:
        return None
    try:
        element = await page.wait_for_selector(selector, timeout=3000)
        if not element:
            return None

        image_bytes = await element.screenshot()
        result = ocr.classification(image_bytes)
        
        logger.info(f" OCR 辨識結果: '{result}'")
        return result
    except Exception as e:
        logger.error(f"OCR 辨識失敗: {e}")
        return None

async def block_resources(route):
    """攔截不必要的資源請求，極大化速度"""
    url = route.request.url.lower()
    if route.request.resource_type in ["media", "font", "stylesheet"]:
        await route.abort()
    elif route.request.resource_type == "image":
        # 阻擋絕大部分圖片，但如果是驗證碼圖片必須放行！
        if "captcha" in url:
            await route.continue_()
        else:
            await route.abort()
    else:
        await route.continue_()

async def automatic_attack(context, account):
    """作法 A：手動登入 (延遲 30 秒) + 後續自動搶票流程"""
    page = await context.new_page()
    
    # 處理驗證碼錯誤跳出的彈窗 (Alert框)，避免程式卡死
    page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    
    try:
        # ======= 新增：作法 A 手動登入機制 ======= 
        logger.info(f"[{account['username']}] 0. 開啟售票網站首頁，準備進行手動登入...")
        
        # 解析目標網址的首頁以利登入
        from urllib.parse import urlparse
        parsed_uri = urlparse(CONFIG['target_url'])
        base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}/"
        
        # 導向首頁
        await page.goto(base_url)
        
        logger.info("==================================================")
        logger.info("【手動登入時間】: 程式已為您暫停 30 秒。")
        logger.info("請在此時於彈出的瀏覽器中「手動輸入帳號密碼」完成登入！")
        logger.info("30 秒後將自動跳轉至目標購票頁面，並繼續搶票流程。")
        logger.info("==================================================")
        
        # 顯示倒數計時
        for i in range(30, 0, -1):
            if i % 10 == 0 or i <= 5:
                logger.info(f"手動登入倒數 {i} 秒...")
            await asyncio.sleep(1)
            
        logger.info("30 秒暫停結束！即將進入全自動搶票流程...")
        # ==========================================

        # 加入自動阻擋功能以極大化速度
        await page.route("**/*", block_resources)

        logger.info(f"[{account['username']}] 1. 進入目標選區頁...")
        await page.goto(CONFIG['target_url'])
        
        # 選區
        try:
            await page.wait_for_selector(CONFIG['selectors']['area_item'], timeout=5000)
            areas = await page.locator(CONFIG['selectors']['area_item']).all()
            if areas:
                target_area = areas[0]
                await target_area.click()
            else:
                return
        except Exception as e:
            logger.error(f"選區失敗: {e}")
            return

        # 等待表單頁面
        await page.wait_for_url("**/checking*")
        logger.info(f"[{account['username']}] 2. 成功進入填單頁面，等待時間倒數...")

        target_dt = datetime.fromisoformat(CONFIG['target_time_iso'])
        target_ts = target_dt.timestamp() if target_dt.tzinfo is None else target_dt.timestamp()

        # 等待到設定的時間點
        await wait_for_trigger(target_ts - CONFIG['lead_time_seconds'])

        logger.info(f"[{account['username']}] 3. 時間到！開始光速填寫與提交！")
        
        # 驗證碼辨識與提交無窮迴圈 (包含失敗重整後的防呆機制)
        while True:
            try:
                # 確保每次執行迴圈時，畫面上的選項都有被正確填寫 
                # (防範驗證碼錯誤導致網頁自動重新整理，選項被清空卡死的情況)
                await page.wait_for_selector(CONFIG['selectors']['quantity_select'], timeout=5000)
                await page.select_option(CONFIG['selectors']['quantity_select'], "1")
                await page.check(CONFIG['selectors']['terms_checkbox'])
            except Exception as e:
                logger.warning("尋找下拉選單或勾選框失敗，可能網頁未備妥，將繼續重試...")
            
            captcha_selector = CONFIG['selectors'].get('captcha_img')
            if captcha_selector:
                logger.info("嘗試自動辨識驗證碼...")
                answer = await solve_captcha_with_ocr(page, captcha_selector)
                if answer:
                    try:
                        await page.fill(CONFIG['selectors']['captcha_input'], "")
                        await page.fill(CONFIG['selectors']['captcha_input'], answer)
                    except:
                        pass
                else:
                    logger.warning("OCR 無法辨識，或無驗證碼。")
            
            # 點擊送出
            try:
                submit_btn = page.locator(CONFIG['selectors']['submit_btn'])
                await submit_btn.click()
                logger.info("提交按鈕已點擊！等待伺服器回應...")
            except:
                pass

            # 觀察結果
            try:
                # 若能成功跳轉到 loading，代表驗證碼正確且送出成功
                await page.wait_for_url("**/loading*", timeout=2500)
                logger.info(f"[{account['username']}] 🎉 成功跳轉至 loading，極大機率搶票成功！")
                break
            except Exception as e:
                logger.warning(f"[{account['username']}] 提交失敗、驗證碼錯誤或網頁重整中，程式準備下一輪嘗試...")
                # 給予網頁一點緩衝或重新載入的時間
                await asyncio.sleep(0.5)
                
        # 搶票成功，掛起瀏覽器讓使用者檢查
        logger.info("腳本執行完畢，保留瀏覽器視窗方便您檢查或結帳。")
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"[{account['username']}] 流程發生未預期異常: {e}")
    finally:
        await page.close()

async def main_flow():
    async with async_playwright() as p:
        # 開啟瀏覽器為可見模式 (headless=False)，加入防反扒參數
        browser = await p.chromium.launch(
            headless=False, 
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800}
        )
        
        # 提取第一個帳號作測試 (目前帳號只是識別用，登入採 30 秒手動)
        account = CONFIG['accounts'][0]
        logger.info(f"載入目標帳號：{account['username']}")
        
        await automatic_attack(context, account)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main_flow())
