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
            if len(link) > 990: link = "https://news.google.com/"
            news_list.append({'title': clean_title, 'link': link})
        return news_list
    except Exception as e:
        print(f"Fetch Error: {e}"); return []

def get_gemini_summary(news_list):
    """AI 摘要生成 (雙保險機制：分類失敗自動降級)"""
    if not GEMINI_API_KEY: return "❌ 缺少 API Key"
    
    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    try:
        tw_time = datetime.now(timezone(timedelta(hours=8)))
        h = tw_time.hour
    except: h = datetime.now().hour

    greeting = "早安" if 5 <= h < 12 else "午安" if 12 <= h < 18 else "晚安"

    # 🟢 方案 A：你想要的「分類標題版」
    prompt_category = (
        f"以下是台灣今日新聞：\n{titles_text}\n\n"
        f"請以『{greeting}，為您帶來重點快報』開場，生成約 300 字摘要。"
        "請依照內容性質加上【分類標題】（如【政治】、【國際】、【社會】等），標題獨佔一行並換行。"
        "內容請客觀中立，重點清晰。"
    )

    # 🔵 方案 B：15:05 驗證過的「純淨成功版」 (保底用)
    prompt_simple = (
        f"以下是台灣今日熱門新聞：\n{titles_text}\n\n"
        f"請以『{greeting}，為您帶來重點快報』開場，生成分段式摘要 (約250字)。"
        "⚠️ 嚴禁使用 Markdown 星號 (**) 或粗體語法。"
        "⚠️ 主題間請空一行。"
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    model_name = "gemini-2.0-flash" # 鎖定這個最強模型

    # 🚀 第一次嘗試：跑分類版
    try:
        print(f"🤖 (1/2) 嘗試生成分類摘要...")
        response = client.models.generate_content(
            model=model_name, 
            contents=prompt_category
        )
        print(f"✅ 分類版成功！")
        return response.text.replace("**", "") 
    except Exception as e:
        print(f"⚠️ 分類版觸發安全限制 ({e})，立刻切換回 15:05 成功模式...")

    # 🛡️ 第二次嘗試：跑保底版 (絕對會成功)
    try:
        print(f"🤖 (2/2) 啟動保底成功模式...")
        response = client.models.generate_content(
            model=model_name, 
            contents=prompt_simple
        )
        print(f"✅ 保底版成功！")
        return response.text.replace("**", "")
    except Exception as e:
        print(f"❌ 全部失敗: {e}")
        return "❌ AI 暫時無法回應"

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
