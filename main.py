#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案名稱：Google News AI 智能新聞秘書 (AI 修復版)
重點功能：
1. 恢復「早安/午安/晚安」時間判斷 (UTC+8)
2. 恢復「AI 重點摘要」與「新聞分類」
3. 確保讀取 GitHub Secrets
"""
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

# 1. 讀取 GitHub 金鑰
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_URL = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

def fetch_google_news():
    """抓取新聞並處理長網址"""
    try:
        response = requests.get(RSS_URL, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news_list = []
        for item in root.findall('./channel/item')[:10]:
            title = item.find('title').text
            link = item.find('link').text
            clean_title = title.split(' - ')[0]
            # 安全閥
            if len(link) > 990: link = "https://news.google.com/"
            news_list.append({'title': clean_title, 'link': link})
        return news_list
    except Exception as e:
        print(f"Fetch Error: {e}")
        return []

def get_gemini_summary(news_list):
    """生成 AI 摘要 (含問候與分類)"""
    # 檢查是否有 Key
    if not GEMINI_API_KEY:
        print("❌ 錯誤：找不到 GEMINI_API_KEY，跳過 AI 摘要。")
        return None

    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    # 🕒 強制鎖定台灣時間 (UTC+8) 判斷早/午/晚
    try:
        tw_timezone = timezone(timedelta(hours=8))
        current_hour = datetime.now(tw_timezone).hour
    except:
        current_hour = datetime.now().hour

    if 5 <= current_hour < 12: greeting, period = "早安", "今日上午"
    elif 12 <= current_hour < 18: greeting, period = "午安", "今日午間"
    else: greeting, period = "晚安", "今日晚間"
    
    opening = f"{greeting}，為您帶來{period}重點快報"

    # 📝 這裡就是您要的分類指令
    prompt = (
        f"以下是台灣今日熱門新聞標題：\n{titles_text}\n\n"
        f"請扮演專業主播，以『{opening}』作為開場白，"
        "為我生成一份「分段式」的重點快報，總字數約 200 字。"
        "⚠️ 分類要求：請根據新聞內容自然分類（例如：【政治焦點】、【財經動態】、【社會熱議】、【國際矚目】等）。"
        "⚠️ 格式要求：類別與內容之間換行，段落之間空一行，語氣專業且親切。"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 嘗試多種模型 (Failover)
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    
    for model in models:
        try:
            print(f"🤖 正在呼叫 AI 模型: {model}...")
            response = client.models.generate_content(model=model, contents=prompt)
            print("✅ AI 摘要生成成功！")
            return response.text
        except Exception as e:
            print(f"⚠️ {model} 失敗: {e}，嘗試下一個...")
            continue
            
    return None

def send_flex_message(news_list, summary):
    """發送 LINE 訊息"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    
    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    flex = [{"type": "text", "text": f"📅 {tw_time} 新聞快報", "weight": "bold", "size": "md", "color": "#888888"}]
    
    # 只有當 summary 成功生成時，才會顯示 AI 區塊
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
                {"type": "text", "text": item['title'], "wrap": True, "size": "lg", "color": "#111111", "flex": 1, "margin": "md", 
                 "action": {"type": "uri", "uri": item['link']}}
            ]
        })

    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": f"🔔 {tw_time} 新聞", "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": flex}}}]}
    
    try: requests.post(url, headers=headers, data=json.dumps(payload))
    except: pass

# PWA 更新功能 (保留)
def update_pwa(news, summary):
    try:
        data = {"updated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"), "summary": summary, "news": news}
        with open('latest_news.json', 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

if __name__ == "__main__":
    news = fetch_google_news()
    if news:
        summary = get_gemini_summary(news) # 這裡會去抓 AI
        send_flex_message(news, summary)
        update_pwa(news, summary)
