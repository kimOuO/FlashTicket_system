import asyncio
import json
import logging
from datetime import datetime
from playwright.async_api import async_playwright
import ddddocr
from utils import NTPSynchronizer

# 配置 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FlashTicket-AutoOCR")

import argparse
import sys
import os

# 初始化 ddddocr (帶帶弟弟 OCR, 專門用來辨識驗證碼的超輕量模型)
ocr = ddddocr.DdddOcr(show_ad=False)

# 載入配置
try:
    with open('config.json', 'r') as f:
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
    try:
        # 1. 找到圖片元素
        element = await page.wait_for_selector(selector, timeout=3000)
        if not element:
            return None

        # 2. 截取圖片元素的 bytes (Playwright 原生支援截圖成二進位)
        image_bytes = await element.screenshot()
        
        # 3. 直接丟給 ddddocr 辨識 (它內建預處理模型，連 cv2 的降噪都不用自己寫！)
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
    """全自動流程 (包含 OCR 辨識驗證碼)"""
    page = await context.new_page()
    
    # 攔截加速：不載入不必要的圖片、CSS 或字體
    await page.route("**/*", block_resources)

    # 處理驗證碼錯誤跳出的彈窗 (Alert框)，避免程式卡死
    page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    
    try:
        logger.info(f"[{account['username']}] 1. 進入區域選擇頁...")
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
        logger.info(f"[{account['username']}] 2. 等待倒數...")

        target_dt = datetime.fromisoformat(CONFIG['target_time_iso'])
        target_ts = target_dt.timestamp() if target_dt.tzinfo is None else target_dt.timestamp()

        await wait_for_trigger(target_ts - CONFIG['lead_time_seconds'])

        logger.info(f"[{account['username']}] 3. 開始填寫與提交！")
        
        # 驗證碼辨識與提交迴圈 (直到成功為止)
        while True:
            try:
                # 把「填寫」放進迴圈，防止驗證碼錯誤導致網頁重整後，選項被清空
                await page.wait_for_selector(CONFIG['selectors']['quantity_select'], timeout=5000)
                await page.select_option(CONFIG['selectors']['quantity_select'], "1")
                await page.check(CONFIG['selectors']['terms_checkbox'])
            except Exception as e:
                logger.warning("尋找下拉選單或勾選框失敗，可能網頁未備妥，繼續重試...")

            # 自動辨識驗證碼 (如果有)
            captcha_selector = CONFIG['selectors'].get('captcha_img')
            if captcha_selector:
                logger.info("嘗試自動辨識驗證碼...")
                
                # 如果網站支援點擊驗證碼圖片刷新，可在這裡嘗試點擊
                # try: await page.click(captcha_selector, timeout=1000); await asyncio.sleep(0.5)
                # except: pass
                
                answer = await solve_captcha_with_ocr(page, captcha_selector)
                if answer:
                    try:
                        await page.fill(CONFIG['selectors']['captcha_input'], "")
                        await page.fill(CONFIG['selectors']['captcha_input'], answer)
                    except:
                        pass
                else:
                    logger.warning("OCR 無法辨識，或無驗證碼。")
            
            # 提交
            try:
                submit_btn = page.locator(CONFIG['selectors']['submit_btn'])
                await submit_btn.click()
                logger.info("提交按鈕已點擊！等待結果...")
            except:
                pass

            # 觀察結果
            try:
                # 若能在 2.5 秒內跳轉到 loading，代表驗證碼正確且送出成功
                await page.wait_for_url("**/loading*", timeout=2500)
                logger.info(f"[{account['username']}] 成功跳轉，可能搶票成功！")
                break # 成功！跳出無窮迴圈
            except:
                logger.warning("未檢測到跳轉，可能是驗證碼錯誤。準備下一輪重新填寫...")
                # 清空驗證碼輸入框，準備下一輪辨識
                if captcha_selector:
                    try:
                        await page.fill(CONFIG['selectors']['captcha_input'], "")
                    except:
                        pass
                
                # 短暫等待，避免網頁還沒反應過來 (給予重整緩衝)
                await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"流程異常: {e}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) 
        context = await browser.new_context()

        task = automatic_attack(context, CONFIG['accounts'][0])
        await task

        logger.info("流程結束，保留視窗...")
        try:
            await asyncio.get_event_loop().run_in_executor(None, input, "按 Enter 鍵關閉瀏覽器...")
        except:
            pass
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())