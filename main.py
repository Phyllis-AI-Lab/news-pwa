#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案名稱：Google News AI 智能新聞秘書 (Gemini 2.0 成功復刻版)
核心功能：
1. 嚴格採用 Gemini 2.0 Flash (您指定的最新模型)
2. 恢復「早安/午安」問候語與「分類摘要」
3. GitHub Actions 專用架構
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
    """抓取 Google News RSS"""
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
    """Gemini 2.0 摘要生成 (成功模式邏輯)"""
    # 🔍 關鍵檢查：如果沒鑰匙，直接報錯給 LINE
    if not GEMINI_API_KEY:
        return "❌ 錯誤：GitHub Secrets 未設定 GEMINI_API_KEY，請至 Settings 補上。"

    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    # 🕒 強制鎖定台灣時間 (UTC+8)
    try:
        tw_timezone = timezone(timedelta(hours=8))
        current_hour = datetime.now(tw_timezone).hour
    except:
        current_hour = datetime.now().hour

    # 您的成功模式問候語邏輯
    if 5 <= current_hour < 12: greeting, period = "早安", "今日上午"
    elif 12 <= current_hour < 18: greeting, period = "午安", "今日午間"
    else: greeting, period = "晚安", "今日晚間"
    
    opening = f"{greeting}，為您帶來{period}重點快報"

    # 📝 這是您指定的分類 Prompt
    prompt = (
        f"以下是台灣今日熱門新聞標題：\n{titles_text}\n\n"
        f"請扮演專業主播，以『{opening}』作為開場白，"
        "為我生成一份「分段式」的重點快報，總字數約 200-250 字。"
        "⚠️ 分類建議：請根據新聞內容自然分類（如【財經動態】、【政治焦點】、【社會動態】、【國際消息】等）。"
        "若新聞涉及財經，請準確歸類於【財經動態】。"
        "⚠️ 格式要求：主題間換行並空一行，語氣簡潔有力，不用 Markdown 符號。"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)

    # 🎯 成功模式的核心：Gemini 2.0 黃金陣容
    # 依序嘗試，直到成功
    models_to_try = [
        "gemini-2.0-flash",       # 主力：最新且額度高
        "gemini-2.0-flash-lite",  # 備援1：極速輕量
        "gemini-2.0-flash-exp"    # 備援2：實驗版
    ]
    
    last_error = ""

    for model_name in models_to_try:
        try:
            print(f"🤖 嘗試使用模型: {model_name} ...")
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt,
                config=types.GenerateContentConfig(
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE")
                    ]
                )
            )
            print(f"✅ 成功！由 [{model_name}] 完成摘要。")
            return response.text
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ {model_name} 失敗，切換備援...")
            continue 

    # 如果還是失敗，直接回傳錯誤給 LINE，讓您知道原因
    return f"❌ AI 摘要生成失敗 (金鑰可能過期或額度已滿)。\n錯誤訊息: {last_error}"

def send_flex_message(news_list, summary):
    """發送 LINE Flex Message"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    
    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    flex = [{"type": "text", "text": f"📅 {tw_time} 新聞快報", "weight": "bold", "size": "md", "color": "#888888"}]
    
    # 處理 AI 摘要顯示 (支援顯示錯誤訊息)
    header_color = "#1DB446"
    text_color = "#555555"
    if "❌" in summary: # 如果是錯誤訊息，變紅色提醒
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
    flex.append({"type": "text", "text": "🔥 熱門頭條 (點擊閱讀)", "weight": "bold", "size": "xl", "margin": "xl"})
    
    for i, item in enumerate(news_list, 1):
        flex.append({
            "type": "box", "layout": "horizontal", "margin": "lg",
            "contents": [
                {"type": "text", "text": f"{i}.", "flex": 0, "color": "#aaaaaa", "size": "lg", "gravity": "center"},
                {"type": "text", "text": item['title'], "wrap": True, "size": "lg", "color": "#111111", "flex": 1, "margin": "md", 
                 "action": {"type": "uri", "uri": item['link']}}
            ]
        })

    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": f"🔔 {tw_time} 新聞", "contents": {"type": "bubble", "size": "giga", "body": {"type": "box", "layout": "vertical", "contents": flex}}}]}
    
    try: requests.post(url, headers=headers, data=json.dumps(payload))
    except: pass

def update_pwa_data(news_list, summary):
    """PWA 資料存檔"""
    try:
        tw_timezone = timezone(timedelta(hours=8))
        data = {
            "updated_at": datetime.now(tw_timezone).strftime("%Y-%m-%d %H:%M"),
            "summary": summary if summary else "本日暫無摘要",
            "news": news_list
        }
        with open('latest_news.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

if __name__ == "__main__":
    news = fetch_google_news()
    if news:
        summary = get_gemini_summary(news)
        send_flex_message(news, summary)
        update_pwa_data(news, summary)
