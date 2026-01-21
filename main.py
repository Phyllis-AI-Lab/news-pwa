#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案名稱：Google News AI 智能新聞秘書 (PWA Sync 旗艦版)
版本：2026-01-21 穩定版
功能：
1. 核心推播：延用 18:00 成功的 LINE Flex Message 邏輯 
2. AI 分類：強化指令，自動生成【分類標題】
3. 網頁同步：推播後自動產生 JSON 供 PWA 讀取 
"""
import os
import requests
import json
import xml.etree.ElementTree as ET
from google import genai
from google.genai import types
from datetime import datetime, timedelta, timezone

# 🔑 [延用成功版] 從 GitHub Secrets 讀取金鑰 [cite: 648-650]
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_URL = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

def fetch_google_news():
    """[延用成功版] 抓取新聞並過濾長網址 """
    try:
        response = requests.get(RSS_URL, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news_list = []
        for item in root.findall('./channel/item')[:10]:
            title = item.find('title').text
            link = item.find('link').text
            clean_title = title.split(' - ')[0]
            # [成功安全閥] 防止網址超過 990 字元導致 400 報錯 [cite: 663, 870]
            if len(link) > 990: link = "https://news.google.com/"
            news_list.append({'title': clean_title, 'link': link})
        return news_list
    except Exception as e:
        print(f"Fetch Error: {e}"); return []

def get_gemini_summary(news_list):
    """[延用成功版 + 分類強化] AI 摘要生成 [cite: 668-688]"""
    if not news_list: return None
    titles_text = "\n".join([f"- {n['title']}" for n in news_list])
    
    tw_time = datetime.now(timezone(timedelta(hours=8)))
    h = tw_time.hour
    greeting = "早安" if 5 <= h < 12 else "午安" if 12 <= h < 18 else "晚安"

    # 🎯 [強化指令] 要求分類標題，確保網頁版與 LINE 同步有條理 
    prompt = (
        f"以下是台灣今日熱門新聞：\n{titles_text}\n\n"
        f"請扮演專業主播，以『{greeting}，為您帶來重點快報』作為開場白。"
        "請根據新聞性質分段，每段必須以【分類名稱】開頭 (如：【政治焦點】、【財經動態】等)。"
        "⚠️ 格式嚴格要求：段落之間請「換行並空一行」，嚴禁使用任何 Markdown 符號 (如 **)。"
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    # [備援模型清單] 確保 AI 不斷線 [cite: 683, 899]
    for model_name in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text.replace("**", "") # 二次保險淨化 [cite: 686]
        except: continue
    return None

def send_flex_message(news_list, summary):
    """[延用成功版] 發送滿版舒服版訊息 (Giga Size) """
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
    flex.append({"type": "text", "text": "🔥 熱門頭條 (點擊閱讀)", "weight": "bold", "size": "xl", "margin": "xl"})

    for i, item in enumerate(news_list, 1):
        flex.append({
            "type": "box", "layout": "horizontal", "margin": "lg",
            "contents": [
                {"type": "text", "text": f"{i}.", "flex": 0, "color": "#aaaaaa", "size": "lg"},
                {"type": "text", "text": item['title'], "wrap": True, "size": "lg", "color": "#111111", "flex": 1, "margin": "md", "action": {"type": "uri", "uri": item['link']}}
            ]
        })

    # [關鍵尺寸] Giga 確保手機滿版閱讀舒服 [cite: 712, 782, 939]
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": f"🔔 {tw_time} 新聞", "contents": {"type": "bubble", "size": "giga", "body": {"type": "box", "layout": "vertical", "contents": flex}}}]}
    requests.post(url, headers=headers, data=json.dumps(payload))

def update_pwa_data(news_list, summary):
    """[PWA 新功能] 同步資料至 JSON 檔 [cite: 715-722, 942-959]"""
    try:
        tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        data = {"updated_at": tw_time, "summary": summary, "news": news_list}
        with open('latest_news.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(" ✅ PWA 資料存檔成功")
    except: pass

if __name__ == "__main__":
    print(" 🚀 Starting bot (Safe Flagship Version)...")
    news = fetch_google_news()
    if news:
        summary = get_gemini_summary(news)
        # 第一順位：確保 LINE 推播成功 (與 18:00 成功的路徑一致) [cite: 973]
        send_flex_message(news, summary)
        print(" ✅ LINE 發送完成")
        
        # 第二順位：同步更新網頁資料 (失敗不影響推播) [cite: 975]
        update_pwa_data(news, summary)
