#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import html
import time
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai

# 🔑 讀取 GitHub Secrets 金鑰 (Success Mode)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 🆕 Telegram 金鑰（沒設定就會自動跳過 Telegram 發送，不影響 LINE）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

RSS_URL = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

def fetch_google_news():
    """抓取新聞並過濾長網址"""
    try:
        response = requests.get(RSS_URL, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news_list = []
        for item in root.findall('./channel/item')[:10]:
            title = item.find('title').text
            link = item.find('link').text
            clean_title = title.split(' - ')[0]
            # URL 安全閥：防止網址過長導致 LINE 報錯
            if len(link) > 990: link = "https://news.google.com/"
            news_list.append({'title': clean_title, 'link': link})
        return news_list
    except Exception as e:
        print(f"Fetch Error: {e}"); return []

def get_gemini_summary(news_list):
    """AI 摘要生成 (旗艦成功版 + 分類提示詞)"""
    if not GEMINI_API_KEY: return "❌ 缺少 API Key"
    
    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    # 強制台灣時間
    try:
        tw_time = datetime.now(timezone(timedelta(hours=8)))
        h = tw_time.hour
    except: h = datetime.now().hour

    # 🕒 優化問候語邏輯 (配合主播口吻)
    if 5 <= h < 12: greeting, period = "早安", "今日上午"
    elif 12 <= h < 18: greeting, period = "午安", "今日午間"
    else: greeting, period = "晚安", "今日晚間"
    
    opening = f"{greeting}，為您帶來{period}重點快報"

    # 📝 核心修改：植入你指定的分類提示詞
    prompt = (
        f"以下是台灣今日熱門新聞標題：\n{titles_text}\n\n"
        f"請扮演專業主播，以『{opening}』作為開場白，"
        "為我生成一份「分段式」的重點快報，總字數約 250-300 字。"
        "⚠️ 分類建議：請根據新聞內容自然分類（如【政治焦點】、【國際情勢】、【財經動態】、【社會民生】等）。"
        "⚠️ 格式要求：\n"
        "1. 每個【分類標題】獨佔一行。\n"
        "2. 分類與內容之間請換行，不同分類之間請空一行。\n"
        "3. 語氣簡潔有力，嚴禁使用 Markdown 星號 (**) 或粗體語法。"
    )

    client = genai.Client(api_key=GEMINI_API_KEY)

    # 🎯 黃金備援清單（2026-06 更新：2.0 系列免費額度已被歸零，改用 2.5 系列）
    models_to_try = [
        "gemini-2.5-flash",       # 主力：最新強效型（免費額度仍可用）
        "gemini-2.5-flash-lite",  # 備援1：2.5 輕量版
        "gemini-2.0-flash",       # 備援2：墊底（免費額度可能為 0，純保險）
    ]

    # 暫時性錯誤（塞車/限流）才值得「同模型重試」；其他錯誤直接換下一個模型
    TRANSIENT = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded")
    MAX_RETRY = 3  # 每個模型最多重試次數

    for model_name in models_to_try:
        for attempt in range(1, MAX_RETRY + 1):
            try:
                print(f"🤖 嘗試使用模型: {model_name} (第 {attempt} 次) ...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                print(f"✅ 成功！由 [{model_name}] 完成摘要。")
                return response.text.replace("**", "")  # 二次保險淨化 Markdown
            except Exception as e:
                msg = str(e)
                is_transient = any(k in msg for k in TRANSIENT)
                # 暫時性錯誤且還有重試額度 -> 等幾秒再打同一個模型
                if is_transient and attempt < MAX_RETRY:
                    wait = 10 * attempt
                    print(f"⏳ {model_name} 暫時忙碌，{wait} 秒後重試...")
                    time.sleep(wait)
                    continue
                # 非暫時性錯誤，或重試用盡 -> 換下一個模型
                print(f"⚠️ {model_name} 無法使用 ({msg[:120]})，切換備援...")
                break

    return "❌ AI 暫時無法回應 (所有模型皆忙碌)"

def send_flex_message(news_list, summary):
    """發送滿版舒服版訊息 (Giga Size)"""
    if not LINE_CHANNEL_ACCESS_TOKEN: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    flex = [{"type": "text", "text": f"📅 {tw_time} 新聞快報", "weight": "bold", "size": "md", "color": "#888888"}]
    
    if summary:
        flex.append({
            "type": "box", "layout": "vertical", "backgroundColor": "#f0f8ff", "cornerRadius": "md", "paddingAll": "md", "margin": "md",
            "contents": [
                {"type": "text", "text": "🤖 AI 重點摘要", "weight": "bold", "size": "md", "color": "#1DB446"},
                {"type": "text", "text": summary, "wrap": True, "size": "md", "margin": "md", "color": "#555555", "lineSpacing": "6px"}
            ]
        })
        
    flex.append({"type": "separator", "margin": "xl"})
    flex.append({"type": "text", "text": "🔥 熱門頭條", "weight": "bold", "size": "xl", "margin": "xl"})

    for i, item in enumerate(news_list, 1):
        flex.append({
            "type": "box", "layout": "horizontal", "margin": "lg",
            "contents": [
                {"type": "text", "text": f"{i}.", "flex": 0, "color": "#aaaaaa", "size": "lg"},
                {"type": "text", "text": item['title'], "wrap": True, "size": "lg", "color": "#111111", "flex": 1, "margin": "md", "action": {"type": "uri", "uri": item['link']}}
            ]
        })
        
    # ✨ 關鍵：Giga 尺寸確保手機滿版閱讀舒服
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": f"🔔 {tw_time} 新聞", "contents": {"type": "bubble", "size": "giga", "body": {"type": "box", "layout": "vertical", "contents": flex}}}]}
    requests.post(url, headers=headers, data=json.dumps(payload))

def send_telegram_message(news_list, summary):
    """🆕 發送 Telegram 訊息 (HTML 格式)。沒設金鑰就直接跳過，不影響 LINE。"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(" ⏭️  未設定 Telegram 金鑰，跳過 Telegram 發送。")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    # 把標題轉成 HTML 超連結；標題與摘要都做 HTML 跳脫，避免特殊字元破壞版面
    news_content = ""
    for i, item in enumerate(news_list, 1):
        safe_title = html.escape(item['title'])
        news_content += f"{i}. <a href=\"{item['link']}\">{safe_title}</a>\n\n"

    safe_summary = html.escape(summary) if summary else "（本日暫無摘要）"

    final_text = (
        f"<b>📅 {tw_time} 新聞快報</b>\n\n"
        f"<b>🤖 AI 重點摘要：</b>\n"
        f"{safe_summary}\n\n"
        f"------------------\n"
        f"<b>🔥 熱門頭條：</b>\n"
        f"{news_content}"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": final_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200 and response.json().get("ok"):
            print(" ✅  Telegram 訊息發送成功！")
        else:
            print(f" ❌  Telegram 發送失敗: {response.status_code} {response.text}")
    except Exception as e:
        print(f" ❌  Telegram 連線錯誤: {e}")

def update_pwa_data(news_list, summary):
    """同步更新 PWA 資料"""
    try:
        tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        data = {"updated_at": tw_time, "summary": summary, "news": news_list}
        with open('latest_news.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

if __name__ == "__main__":
    news = fetch_google_news()
    if news:
        summary = get_gemini_summary(news)
        send_flex_message(news, summary)
        send_telegram_message(news, summary)
        update_pwa_data(news, summary)
