#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai
# ❌ 移除所有導致崩潰的 types 引用，回歸純淨

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
    """AI 摘要生成 (純淨版 + 分類提示詞)"""
    if not GEMINI_API_KEY: return "❌ 缺少 API Key"
    
    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    try:
        tw_time = datetime.now(timezone(timedelta(hours=8)))
        h = tw_time.hour
    except: h = datetime.now().hour

    greeting = "早安" if 5 <= h < 12 else "午安" if 12 <= h < 18 else "晚安"

    # 📝 僅修改這裡：用文字引導 AI 做分類，而不改動程式結構
    prompt = (
        f"以下是台灣今日熱門新聞：\n{titles_text}\n\n"
        f"請以『{greeting}，為您帶來重點快報』開場，生成一份約 300 字的重點摘要。"
        "⚠️ 格式嚴格要求："
        "1. 請根據新聞內容自動分類，標題格式為【分類名稱】，例如【政治焦點】、【國際情勢】、【社會動態】等。"
        "2. 每個分類標題請獨佔一行，分類之間務必空一行。"
        "3. 內容請用條列式呈現，客觀中立，重點清晰。"
        "4. 請直接輸出純文字，不要使用 Markdown 星號 (**)。"
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 💎 使用你驗證過成功的模型清單
    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]

    for model_name in models_to_try:
        try:
            print(f"🤖 嘗試使用模型: {model_name} ...")
            # 不加任何 config，避免報錯
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt
            )
            print(f"✅ 成功！由 [{model_name}] 完成摘要。")
            return response.text.replace("**", "") 
        except Exception as e:
            # 如果真的遇到錯誤，印出詳細訊息
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
