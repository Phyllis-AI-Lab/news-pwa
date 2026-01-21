#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案名稱：Google News AI 智能新聞秘書 (2026 旗艦完美排版版)
修改重點：
1. UI 優化：加入 "size": "giga" 確保字卡橫向撐滿，提升手機閱讀舒服度。
2. Prompt 優化：嚴格禁止 AI 使用 Markdown 星號 (**)，確保標題乾淨。
3. 旗艦陣容：維持 Gemini 2.5 / 2.0 旗艦模型自動備援。
4. 環境變數：由 GitHub Secrets 安全讀取金鑰。
"""
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

# 1. 讀取 GitHub 金鑰 [cite: 279, 280, 281]
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_URL = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

def fetch_google_news():
    """抓取 Google News RSS 並過濾長網址 [cite: 284, 292, 301]"""
    try:
        response = requests.get(RSS_URL, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news_list = []
        for item in root.findall('./channel/item')[:10]:
            title = item.find('title').text
            link = item.find('link').text
            clean_title = title.split(' - ')[0]
            # 安全閥：避免網址過長導致 LINE API 錯誤 [cite: 298, 300]
            if len(link) > 990: link = "https://news.google.com/"
            news_list.append({'title': clean_title, 'link': link})
        return news_list
    except Exception as e:
        print(f"Fetch Error: {e}")
        return []

def get_gemini_summary(news_list):
    """AI 摘要生成 (含 Markdown 淨化與階梯式備援) [cite: 473, 520]"""
    if not GEMINI_API_KEY:
        return "❌ 錯誤：GitHub Secrets 未設定 GEMINI_API_KEY。"

    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    # 強制台灣時區設定 (UTC+8) [cite: 312, 313, 525]
    try:
        tw_timezone = timezone(timedelta(hours=8))
        current_hour = datetime.now(tw_timezone).hour
    except:
        current_hour = datetime.now().hour

    if 5 <= current_hour < 12: greeting, period = "早安", "今日上午"
    elif 12 <= current_hour < 18: greeting, period = "午安", "今日午間"
    else: greeting, period = "晚安", "今日晚間"
    opening = f"{greeting}，為您帶來{period}重點快報" [cite: 529, 530, 531, 532]

    # Prompt 嚴格要求排版淨化 [cite: 734]
    prompt = (
        f"以下是台灣今日熱門新聞標題：\n{titles_text}\n\n"
        f"請扮演專業主播，以『{opening}』作為開場白，"
        "為我生成一份「分段式」的重點快報，總字數約 250 字。"
        "⚠️ 分類要求：請根據新聞內容自然分類（例如：【政治焦點】、【財經動態】、【社會熱議】等）。"
        "⚠️ 排版嚴格要求：\n"
        "1. 類別標題請直接顯示，例如【政治焦點】，嚴禁在前後加上 ** 符號。\n"
        "2. 不要使用任何 Markdown 粗體語法。\n"
        "3. 段落之間空一行，語氣親切專業。"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)

    # 💎 2026 黃金陣容備援清單 [cite: 544, 737]
    models_to_try = [
        "gemini-2.5-flash",       
        "gemini-2.0-flash",       
        "gemini-2.0-flash-lite",  
        "gemini-3-flash-preview"  
    ]
    
    last_error = ""

    for model_name in models_to_try:
        try:
            print(f"🤖 正在呼叫旗艦模型: {model_name}...")
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt
            )
            print(f"✅ 成功！由 [{model_name}] 完成摘要。")
            # 二次保險：強制移除所有星號確保排版乾淨 [cite: 746]
            clean_text = response.text.replace("**", "")
            return clean_text
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ {model_name} 失敗，嘗試下一個...")
            continue
            
    return f"❌ AI 暫時無法回應。\n最後嘗試錯誤: {last_error}"

def send_flex_message(news_list, summary):
    """發送 LINE Flex Message (Giga 滿版舒服版) [cite: 344, 574]"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    
    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M") [cite: 578]
    
    # 建立 Flex 內容 [cite: 358, 580]
    flex = [{"type": "text", "text": f"📅 {tw_time} 新聞快報", "weight": "bold", "size": "md", "color": "#888888"}]
    
    header_color = "#1DB446"
    text_color = "#555555"
    if "❌" in summary:
        header_color = "#FF3333"
        text_color = "#FF0000"

    # AI 摘要區塊 [cite: 363, 583]
    flex.append({
        "type": "box", "layout": "vertical", "backgroundColor": "#f0f8ff", "cornerRadius": "md", "paddingAll": "md", "margin": "md",
        "contents": [
            {"type": "text", "text": "🤖 AI 重點摘要", "weight": "bold", "size": "md", "color": header_color},
            {"type": "text", "text": summary, "wrap": True, "size": "md", "margin": "md", "color": text_color, "lineSpacing": "6px"}
        ]
    })
    
    flex.append({"type": "separator", "margin": "xl"})
    flex.append({"type": "text", "text": "🔥 熱門頭條", "weight": "bold", "size": "xl", "margin": "xl"})
    
    # 新聞列表區塊 (使用 LG 大字體) [cite: 371, 591]
    for i, item in enumerate(news_list, 1):
        flex.append({
            "type": "box", "layout": "horizontal", "margin": "lg",
            "contents": [
                {"type": "text", "text": f"{i}.", "flex": 0, "color": "#aaaaaa", "size": "lg"},
                {"type": "text", "text": item['title'], "wrap": True, "size": "lg", "color": "#111111", "flex": 1, "margin": "md", 
                 "action": {"type": "uri", "uri": item['link']}}
            ]
        })

    # ✨ 關鍵優化：加入 "size": "giga" 確保字卡橫向滿版 
    payload = {
        "to": LINE_USER_ID, 
        "messages": [{
            "type": "flex", 
            "altText": f"🔔 {tw_time} 新聞快報", 
            "contents": {
                "type": "bubble", 
                "size": "giga", 
                "body": {"type": "box", "layout": "vertical", "contents": flex}
            }
        }]
    }
    try: 
        requests.post(url, headers=headers, data=json.dumps(payload))
    except: 
        pass

def update_pwa_data(news_list, summary):
    """更新 PWA JSON 資料 [cite: 780, 788]"""
    try:
        tw_timezone = timezone(timedelta(hours=8))
        data = {
            "updated_at": datetime.now(tw_timezone).strftime("%Y-%m-%d %H:%M"), 
            "summary": summary, 
            "news": news_list
        }
        with open('latest_news.json', 'w', encoding='utf-8') as f: 
            json.dump(data, f, ensure_ascii=False, indent=4)
    except: 
        pass

if __name__ == "__main__":
    news = fetch_google_news()
    if news:
        summary = get_gemini_summary(news)
        send_flex_message(news, summary)
        update_pwa_data(news, summary)
