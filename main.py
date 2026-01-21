#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案名稱：Google News AI 智能新聞秘書 (2026 旗艦版)
核心升級：
1. 啟用 Gemini 2.5 Flash (最新主力)
2. 備援 Gemini 2.0 Flash (穩定正式版)
3. 移除舊版與實驗版，確保額度與穩定性
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
    """抓取新聞"""
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
    """AI 摘要生成 (2026 旗艦模型版)"""
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
        "⚠️ 分類要求：請根據新聞內容自然分類（例如：【政治焦點】、【財經動態】、【社會熱議】等）。"
        "⚠️ 格式要求：段落之間空一行，語氣親切專業。"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)

    # 💎 2026 黃金陣容：根據您查到的權限清單排序
    models_to_try = [
        "gemini-2.5-flash",       # 第一順位：2026 主流極速版
        "gemini-2.0-flash",       # 第二順位：超穩定正式版 (非 exp)
        "gemini-2.0-flash-lite",  # 第三順位：輕量省流版
        "gemini-3-flash-preview"  # 第四順位：嚐鮮預覽版
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
            return response.text
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ {model_name} 失敗，嘗試下一個...")
            continue
            
    return f"❌ AI 暫時無法回應。\n最後嘗試錯誤: {last_error}"

def send_flex_message(news_list, summary):
    """發送 LINE 訊息"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    
    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    flex = [{"type": "text", "text": f"📅 {tw_time} 新聞快報", "weight": "bold", "size": "md", "color": "#888888"}]
    
    # 狀態顏色
    header_color = "#1DB446"
    text_color = "#555555"
    if "❌" in summary:
        header_color = "#FF3333"
        text_color = "#FF0000"

    flex.append({
        "type": "box", "layout": "vertical", "backgroundColor": "#f0f8ff", "cornerRadius": "md", "paddingAll": "md", "margin": "md",
        "contents": [
            {"type": "text", "text": "🤖 AI 重點摘要", "weight": "bold", "size": "md", "color": header_color},
            {"type": "text", "text": summary, "wrap": True, "size": "md", "margin": "md", "color": text_color, "lineSpacing": "6px"}
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

def update_pwa_data(news_list, summary):
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
