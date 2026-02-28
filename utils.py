import time
import math
import random
import asyncio
import cv2
import ntplib
import numpy as np
from datetime import datetime, timezone
from curl_cffi import requests as cffi_requests  # 用於模擬 TLS 指紋

class NTPSynchronizer:
    def __init__(self, server='pool.ntp.org'):
        self.server = server
        self.offset = 0.0
        self.client = ntplib.NTPClient()

    def sync(self):
        """計算本地時間與 NTP 伺服器的時間偏差"""
        try:
            response = self.client.request(self.server, version=3)
            # offset = 伺服器時間 - 本地時間
            self.offset = response.offset
            print(f"[NTP] 時間同步完成。偏差值: {self.offset:.6f} 秒")
        except Exception as e:
            print(f"[NTP] 同步失敗，使用本地時間: {e}")
            self.offset = 0.0

    def get_precise_time(self):
        """獲取校準後的精確 Unix Timestamp"""
        return time.time() + self.offset

class BezierMouse:
    """生成貝茲曲線路徑以模擬人類滑鼠移動"""
    @staticmethod
    def get_path(start, end, steps=20):
        path = []
        x1, y1 = start
        x2, y2 = end
        
        # 隨機控制點
        ctrl1_x = x1 + random.randint(0, abs(x2 - x1)) * 0.5
        ctrl1_y = y1 + random.randint(-100, 100)
        ctrl2_x = x2 - random.randint(0, abs(x2 - x1)) * 0.5
        ctrl2_y = y2 + random.randint(-100, 100)

        for t in np.linspace(0, 1, num=steps):
            # 三階貝茲曲線公式
            x = (1-t)**3 * x1 + 3*(1-t)**2 * t * ctrl1_x + 3*(1-t) * t**2 * ctrl2_x + t**3 * x2
            y = (1-t)**3 * y1 + 3*(1-t)**2 * t * ctrl1_y + 3*(1-t) * t**2 * ctrl2_y + t**3 * y2
            path.append((x, y))
        return path

class CaptchaProcessor:
    """簡單的圖形驗證碼預處理"""
    @staticmethod
    def preprocess(image_bytes):
        # 將 bytes 轉換為 numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 灰階化
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 二值化 (Otsu's method)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 去噪 (簡單的中值濾波)
        denoised = cv2.medianBlur(binary, 3)
        
        # 這裡通常會接續 OCR 模型 (如 Tesseract 或深層學習模型)
        # 為演示目的，返回處理後的圖片數據
        return denoised

class NetworkUtils:
    @staticmethod
    async def submit_with_ja3(url, headers=None, cookies=None, data=None, method="POST", proxy=None):
        """
        使用 curl_cffi 模擬真實瀏覽器 TLS 指紋 (JA3 Fingerprinting)
        這能繞過許多針對 Python requests/httpx 的防火牆阻擋
        """
        try:
            # 模擬 Chrome 120 的 TLS 指紋
            response = cffi_requests.request(
                method=method,
                url=url,
                headers=headers,
                cookies=cookies,
                json=data if method == "POST" else None,
                params=data if method == "GET" else None,
                impersonate="chrome120",
                proxies={"http": proxy, "https": proxy} if proxy else None,
                timeout=5
            )
            return response.status_code, response.text
        except Exception as e:
            return 999, str(e)

    @staticmethod
    async def exponential_backoff(attempt, base_delay=0.1, max_delay=2.0):
        """指數退避策略"""
        delay = min(base_delay * (2 ** attempt), max_delay)
        jitter = random.uniform(0, 0.05) # 加入隨機抖動
        await asyncio.sleep(delay + jitter)
