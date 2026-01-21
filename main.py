#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案名稱：Google News AI 智能新聞秘書 (GitHub Actions 版)
功能：
1. 自動從 GitHub Secrets 讀取金鑰 (無伺服器架構核心)
2. Gemini 模型自動備援 (Failover)
3. LINE Flex Message 特大字體推播
4. 自動更新 PWA 資料檔 (latest_news.json)
"""
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

# ========================================================
#  🔑  GitHub Actions 專用設定區 (讀取環境變數)
# ========================================================
# 在 GitHub Settings -> Secrets 中設定這些變數，不要直接填在這裡
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_URL = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

def fetch_google_news():
    """抓取 Google News RSS 並執行安全檢查"""
    try:
        print(" 📡  [FETCH] 正在抓取 Google News...")
        response = requests.get(RSS_URL, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        news_list = []
        for item in root.findall('./channel/item')[:10]: # 取前 10 則
            title = item.find('title').text
            link = item.find('link').text
            clean_title = title.split(' - ')[0]
            
            # 🛡️ 安全閥：防止超長連結導致 LINE 報錯 (Error 400)
            final_link = link
            if len(link) > 990:
                print(f"  ⚠️  網址過長，已自動替換為首頁")
                final_link = "https://news.google.com/?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            
            news_list.append({'title': clean_title, 'link': final_link})
            
        return news_list
    except Exception as e:
        print(f" ❌  Fetch Error: {e}")
        return []

def get_gemini_summary(news_list):
    """Gemini AI 摘要生成 (含自動備援機制)"""
    if not news_list or not GEMINI_API_KEY:
        print(" ⚠️  無新聞資料或缺少 Gemini Key，跳過摘要生成。")
        return None

    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    # 🕒 強制鎖定台灣時間 (UTC+8)
    try:
        tw_timezone = timezone(timedelta(hours=8))
        tw_time = datetime.now(tw_timezone)
        current_hour = tw_time.hour
    except:
        current_hour = datetime.now().hour

    # 依時段決定問候語
    if 5 <= current_hour < 12: greeting, period = "早安", "今日上午"
    elif 12 <= current_hour < 18: greeting, period = "午安", "今日午間"
    else: greeting, period = "晚安", "今日晚間"
    
    opening = f"{greeting}，為您帶來{period}重點快報"

    prompt = (
        f"以下是台灣今日熱門新聞標題：\n{titles_text}\n\n"
        f"請扮演專業主播，以『{opening}』作為開場白，"
        "為我生成一份「分段式」的重點快報，總字數約 150-200 字。"
        "⚠️ 分類建議：請根據新聞內容自然分類（如【財經動態】、【政治焦點】、【社會動態】等）。"
        "若新聞涉及財經，請準確歸類於【財經動態】。"
        "⚠️ 格式要求：主題間換行並空一行，語氣簡潔有力。"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)

    # 🎯 黃金備援清單：依序嘗試，直到成功
    models_to_try = [
        "gemini-2.0-flash",       # 主力：穩定且額度高
        "gemini-2.0-flash-lite",  # 備援1：極速輕量
        "gemini-2.5-flash"        # 備援2：最新強效型
    ]
    
    for model_name in models_to_try:
        try:
            print(f" 🤖  嘗試使用模型: {model_name} ...")
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
            print(f" ✅  成功！由 [{model_name}] 完成摘要。")
            return response.text
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg: print(f" ⚠️  {model_name} 額度滿 (429)，切換備援...")
            elif "404" in error_msg: print(f" ⚠️  {model_name} 異常 (404)，切換備援...")
            else: print(f" ⚠️  {model_name} 錯誤 ({e})，切換備援...")
            continue 

    print(" ❌  所有模型嘗試失敗，今日暫無摘要。")
    return None

def send_flex_message(news_list, summary):
    """發送 LINE Flex Message (XL 特大字體版)"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print(" ⚠️  缺少 LINE Token 或 User ID，無法發送訊息。")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    # 取得台灣時間用於標題
    tw_timezone = timezone(timedelta(hours=8))
    current_time = datetime.now(tw_timezone).strftime("%Y-%m-%d %H:%M")
    
    # 建構 Flex Message 內容
    flex = [{"type": "text", "text": f"📅 {current_time} 新聞快報", "weight": "bold", "size": "md", "color": "#888888"}]
    
    if summary:
        flex.append({
            "type": "box", "layout": "vertical", "backgroundColor": "#f0f8ff", "cornerRadius": "md", "paddingAll": "md", "margin": "md",
            "contents": [
                {"type": "text", "text": "🤖 AI 重點摘要", "weight": "bold", "size": "md", "color": "#1DB446"},
                {"type": "text", "text": summary, "wrap": True, "size": "md", "margin": "md", "color": "#555555", "lineSpacing": "6px"}
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

    payload = {
        "to": LINE_USER_ID,
        "messages": [{
            "type": "flex", 
            "altText": f"🔔 {current_time} 智能新聞快報", 
            "contents": {"type": "bubble", "size": "giga", "body": {"type": "box", "layout": "vertical", "contents": flex}}
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            print(" ✅  LINE 訊息發送成功！")
        else:
            print(f" ❌  LINE 發送失敗: {response.status_code} {response.text}")
    except Exception as e:
        print(f" ❌  連線錯誤: {e}")

def update_pwa_data(news_list, summary):
    """更新 PWA 所需的 JSON 檔案 (如果有的話)"""
    try:
        tw_timezone = timezone(timedelta(hours=8))
        data = {
            "updated_at": datetime.now(tw_timezone).strftime("%Y-%m-%d %H:%M"),
            "summary": summary if summary else "本日暫無摘要",
            "news": news_list
        }
        with open('latest_news.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(" 💾  latest_news.json 更新完成")
    except Exception as e:
        print(f" ⚠️  JSON 存檔失敗 (非必要): {e}")

if __name__ == "__main__":
    print(" 🚀  Starting Bot (GitHub Actions Mode)...")
    
    # 1. 抓新聞
    news = fetch_google_news()
    
    if news:
        # 2. 生成摘要
        summary = get_gemini_summary(news)
        
        # 3. 發送 LINE
        send_flex_message(news, summary)
        
        # 4. 更新本地檔案 (供 GitHub Actions 後續 Commit 使用)
        update_pwa_data(news, summary)
    else:
        print(" ❌  未抓取到任何新聞，程式結束。")
