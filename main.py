#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from google import genai

# 🔑 讀取 GitHub Secrets 環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_URL = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

def fetch_google_news():
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
    if not GEMINI_API_KEY: 
        print("❌ 錯誤：找不到 GEMINI_API_KEY，請檢查 GitHub Secrets！")
        return None
    
    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    # 強制台灣時間
    tw_time = datetime.now(timezone(timedelta(hours=8)))
    h = tw_time.hour
    greeting = "早安" if 5 <= h < 12 else "午安" if 12 <= h < 18 else "晚安"
    
    prompt = (
        f"以下是台灣今日熱門新聞：\n{titles_text}\n\n"
        f"請以『{greeting}，為您帶來重點快報』開場，生成分段式摘要 (約250字)。"
        "⚠️ 嚴禁使用 Markdown 星號 (**)，主題間請空一行。"
    )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        # 階梯式備援：確保一定能產出
        for model_name in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]:
            try:
                print(f"🤖 嘗試模型: {model_name}")
                response = client.models.generate_content(model=model_name, contents=prompt)
                return response.text.replace("**", "")
            except: continue
        return "❌ AI 暫時無法回應 (所有模型皆忙碌)"
    except Exception as e:
        print(f"AI Error: {e}")
        return None

def send_flex_message(news_list, summary):
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

if __name__ == "__main__":
    news = fetch_google_news()
    if news:
        summary = get_gemini_summary(news)
        send_flex_message(news, summary)
