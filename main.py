#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai
# ⚠️ 注意：這裡完全移除了導致錯誤的 types 引用，回歸 15:05 的成功狀態

# 🔑 讀取 GitHub Secrets 金鑰
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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
            if len(link) > 990: link = "https://news.google.com/"
            news_list.append({'title': clean_title, 'link': link})
        return news_list
    except Exception as e:
        print(f"Fetch Error: {e}"); return []

def get_gemini_summary(news_list):
    """AI 摘要生成 (15:05 成功核心 + 分類提示詞修正)"""
    if not GEMINI_API_KEY: return "❌ 缺少 API Key"
    
    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    try:
        tw_time = datetime.now(timezone(timedelta(hours=8)))
        h = tw_time.hour
    except: h = datetime.now().hour

    greeting = "早安" if 5 <= h < 12 else "午安" if 12 <= h < 18 else "晚安"

    # 📝 這裡是唯一的改變：用純文字告訴 AI 要分類，不要改程式碼
    prompt = (
        f"以下是台灣今日熱門新聞：\n{titles_text}\n\n"
        f"請以『{greeting}，為您帶來重點快報』開場，生成一份約 300 字的重點摘要。"
        "⚠️ 格式要求："
        "1. 請務必加上分類標題，例如【政治焦點】、【國際情勢】、【社會動態】、【財經消息】等。"
        "2. 每個【分類標題】獨佔一行。"
        "3. 不同分類之間請空一行，保持版面整潔。"
        "4. 內容請用條列式，不要用 Markdown 粗體符號 (**)。"
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 💎 這是 15:05 驗證過絕對能跑的模型
    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]

    for model_name in models_to_try:
        try:
            print(f"🤖 嘗試使用模型: {model_name} ...")
            # ⚠️ 關鍵：這裡不放任何 config 設定，回歸最原始的呼叫方式
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt
            )
            print(f"✅ 成功！由 [{model_name}] 完成摘要。")
            return response.text.replace("**", "") 
        except Exception as e:
            print(f"⚠️ {model_name} 失敗 ({e})，切換備援...")
            continue
            
    return "❌ AI 暫時無法回應 (所有模型皆忙碌)"

def send_flex_message(news_list, summary):
    """發送滿版舒服版訊息"""
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
        
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": f"🔔 {tw_time} 新聞", "contents": {"type": "bubble", "size": "giga", "body": {"type": "box", "layout": "vertical", "contents": flex}}}]}
    requests.post(url, headers=headers, data=json.dumps(payload))

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
        update_pwa_data(news, summary)
