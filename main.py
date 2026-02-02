#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai

# 🔑 讀取 GitHub Secrets 金鑰 (Success Mode)
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
    
    # 💎 維持 2026 旗艦備援陣容 (最穩定的設定)
    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash"]

    for model_name in models_to_try:
        try:
            print(f"🤖 嘗試使用模型: {model_name} ...")
            # 這裡維持最單純的呼叫 (無 config)，確保不會因為參數錯誤而崩潰
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt
            )
            print(f"✅ 成功！由 [{model_name}] 完成摘要。")
            # 二次保險淨化 Markdown
            return response.text.replace("**", "")
        except Exception as e:
            print(f"⚠️ {model_name} 暫時無法使用 ({e})，切換備援...")
            continue
            
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
