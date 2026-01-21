#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案名稱：Google News AI 智能新聞秘書 (完美排版 + 滿版大字版)
修改重點：
1. UI 優化：在 Flex Message 加入 "size": "giga"，讓字卡與手機同寬，字體視覺顯大。
2. Prompt 優化：嚴禁 AI 使用 Markdown 星號 (**)，確保標題乾淨。
3. 旗艦陣容：維持 Gemini 2.5 / 2.0 旗艦模型自動備援。
4. 環境變數：由 GitHub Secrets 安全讀取金鑰，不影響推播成功基礎。
"""
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

# 1. 讀取 GitHub 金鑰 (維持成功模式)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_URL = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

def fetch_google_news():
    """抓取新聞 (含安全閥)"""
    try:
        response = requests.get(RSS_URL, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news_list = []
        for item in root.findall('./channel/item')[:10]:
            title = item.find('title').text
            link = item.find('link').text
            clean_title = title.split(' - ')[0]
            if len(link) > 990: link = "https://news.google.com/"
            news_list.append({'title': clean_title, 'link': link})
        return news_list
    except Exception as e:
        print(f"Fetch Error: {e}")
        return []

def get_gemini_summary(news_list):
    """AI 摘要生成 (淨化排版版)"""
    if not GEMINI_API_KEY:
        return "❌ 錯誤：GitHub Secrets 未設定 GEMINI_API_KEY。"

    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    # 時區設定 (UTC+8)
    try:
        tw_timezone = timezone(timedelta(hours=8))
        current_hour = datetime.now(tw_timezone).hour
    except:
        current_hour = datetime.now().hour

    if 5 <= current_hour < 12: greeting, period = "早安", "今日上午"
    elif 12 <= current_hour < 18: greeting, period = "午安", "今日午間"
    else: greeting, period = "晚安", "今日晚間"
    opening = f"{greeting}，為您帶來{period}重點快報"

    prompt = (
        f"以下是台灣今日熱門新聞標題：\n{titles_text}\n\n"
        f"請扮演專業主播，以『{opening}』作為開場白，"
        "為我生成一份「分段式」的重點快報，總字數約 250 字。"
        "⚠️ 分類要求：請根據新聞內容自然分類（例如：【政治焦點】、【財經動態】等）。"
        "⚠️ 排版嚴格要求：\n"
        "1. 類別標題請直接顯示，例如【政治焦點】，嚴禁在前後加上 ** 符號。\n"
        "2. 不要使用任何 Markdown 粗體語法。\n"
        "3. 段落之間空一行，語氣親切專業。"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)

    # 💎 2026 旗艦備援陣容
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
            clean_text = response.text.replace("**", "")
            return clean_text
        except Exception as e:
            last_error = str(e)
            continue
            
    return f"❌ AI 暫時無法回應。\n最後嘗試錯誤: {last_error}"

def send_flex_message(news_list, summary):
    """發送 LINE 滿版訊息 (修正版)"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    
    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    # 建立 Flex 結構 (大字體設定)
    flex = [{"type": "text", "text": f"📅 {tw_time} 新聞快報", "weight": "bold", "size": "md", "color": "#888888"}]
    
    header_color = "#1DB446"
    text_color = "#555555"
    if "❌" in summary:
        header_color = "#FF3333"
        text_color = "#FF0000"

    # AI 摘要區塊 (優化行距)
    flex.append({
        "type": "box", "layout": "vertical", "backgroundColor": "#f0f8ff", "cornerRadius": "md", "paddingAll": "md", "margin": "md",
        "contents": [
            {"type": "text", "text": "🤖 AI 重點摘要", "weight": "bold", "size": "md", "color": header_color},
            {"type": "text", "text": summary, "wrap": True, "size": "md", "margin": "md", "color": text_color, "lineSpacing": "6px"}
        ]
    })
    
    flex.append({"type": "separator", "margin": "xl"})
    flex.append({"type": "text", "text": "🔥 熱門頭條", "weight": "bold", "size": "xl", "margin": "xl"})
    
    # 新聞清單 (LG 大字體)
    for i, item in enumerate(news_list, 1):
        flex.append({
            "type": "box", "layout": "horizontal", "margin": "lg",
            "contents": [
                {"type": "text", "text": f"{i}.", "flex": 0, "color": "#aaaaaa", "size": "lg"},
                {"type": "text", "text": item['title'], "wrap": True, "size": "lg", "color": "#111111", "flex": 1, "margin": "md", 
                 "action": {"type": "uri", "uri": item['link']}}
            ]
        })

    # ✨ 關鍵優化：將 size 設定為 giga，讓字卡滿版，解決留白問題
    payload = {
        "to": LINE_USER_ID, 
        "messages": [{
            "type": "flex", 
            "altText": f"🔔 {tw_time} 新聞", 
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
    """更新 PWA 資料"""
    try:
        tw_timezone = timezone(timedelta(hours=8))
        data = {"updated_at": datetime.now(tw_timezone).strftime("%Y-%m-%d %H:%M"), "summary": summary, "news": news_list}
        with open('latest_news.json', 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

if __name__ == "__main__":
    news = fetch_google_news()
    if news:
        summary = get_gemini_summary(news)
        send_flex_message(news, summary)
        update_pwa_data(news, summary)
