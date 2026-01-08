import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yt_dlp
import isodate
import io
import time
import re
import requests
import json
from datetime import datetime
from PIL import Image

# Configuración básica
st.set_page_config(page_title="Front Three's AI Studio", page_icon="⚡", layout="wide")

# --- DATABASE ---
COMPETITORS = {
    "Sidemen": "Sidemen", "Beta Squad": "BetaSquad", "The Overlap": "TheOverlap",
    "Ben Foster": "BenFosterTheCyclingGK", "Pitch Side": "PitchSide", "FilthyFellas": "FilthyFellas",
    "The Fellas": "TheFellas", "John Nellis": "JohnNellis", "ChrisMD": "ChrisMD",
    "Miniminter": "Miniminter", "Thogden": "Thogden", "Box2Box Show": "Box2BoxShow",
    "Get Stuck In": "GetStuckIn", "Sports Dr": "SportsDr", "Rio Ferdinand Presents": "RioFerdinandPresents",
    "Stick to Football": "StickToFootball", "Club 1872": "Club1872", "Shoot for Love": "ShootForLove",
    "UMM": "UMM", "JD Sports": "JDSports", "Footasylum": "Footasylum",
    "Bleacher Report Football": "BleacherReportFootball", "Sky Sports Premier League": "SkySportsPL",
    "SpencerFC": "SpencerFC", "Calfreezy": "Calfreezy", "Zerkaa": "Zerkaa",
    "Danny Aarons": "DannyAarons", "Girth N Turf": "GirthNTurf", "Sharky": "Sharky", "Chunkz": "Chunkz"
}

STRATEGIST_PERSONA = """
Role: Senior YouTube Strategist.
Tone: Direct, Surgical, High-Value.
Instructions: No intro/outro. Bullet points only. Focus on patterns.
"""

# --- DEBUG & HELPERS ---
def get_channel_id(handle, api_key):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        r = youtube.search().list(part="id", q=handle, type="channel", maxResults=1).execute()
        if r['items']: return r['items'][0]['id']['channelId']
    except Exception as e:
        return None

def get_recent_videos(channel_handle, api_key, limit=10):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        ch_id = get_channel_id(channel_handle, api_key)
        if not ch_id: return []
        
        ch_req = youtube.channels().list(part="contentDetails", id=ch_id).execute()
        uploads_id = ch_req['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        videos = []
        pl_req = youtube.playlistItems().list(part="contentDetails", playlistId=uploads_id, maxResults=limit).execute()
        vid_ids = [x['contentDetails']['videoId'] for x in pl_req['items']]
        
        vid_req = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(vid_ids)).execute()
        
        for v in vid_req['items']:
            dur_iso = v['contentDetails']['duration']
            seconds = isodate.parse_duration(dur_iso).total_seconds()
            videos.append({
                "ID": v['id'],
                "Title": v['snippet']['title'],
                "Published": v['snippet']['publishedAt'],
                "Views": int(v['statistics'].get('viewCount', 0)),
                "Likes": int(v['statistics'].get('likeCount', 0)),
                "Comments": int(v['statistics'].get('commentCount', 0)),
                "Type": "Short" if seconds <= 60 else "Longform",
                "Description": v['snippet']['description'],
                "Thumbnail": v['snippet']['thumbnails']['high']['url'],
                "Competitor": channel_handle 
            })
        return videos
    except Exception as e:
        st.error(f"YouTube API Error: {e}")
        return []

# --- AI CORE (SIMPLIFICADO) ---
def generate_ai_response(prompt, api_key, image=None):
    genai.configure(api_key=api_key)
    
    # Modelo por defecto, el más estable para flash
    model_name = 'models/gemini-1.5-flash'
    
    try:
        model = genai.GenerativeModel(model_name)
        inputs = [prompt, image] if image else prompt
        return model.generate_content(inputs).text
    except Exception as e:
        return f"⚠️ AI ERROR: {str(e)}"

# --- INTERFAZ ---
def main():
    # Login simple
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 Login")
        user = st.text_input("User")
        pwd = st.text_input("Password", type="password")
        if st.button("Enter"):
            if user == st.secrets["login"]["username"] and pwd == st.secrets["login"]["password"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Wrong credentials")
        return

    # App Principal
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except:
        st.error("Secrets no configurados correctamente.")
        st.stop()

    st.sidebar.success("System Online 🟢")
    
    # TABS
    t1, t2, t3, t4, t5, t6 = st.tabs(["📊 Channel", "📥 Downloader", "👁️ Metadata", "💬 Engagement", "⚔️ Competitors", "💡 Ideation"])

    # 1. Channel
    with t1:
        st.header("📊 Channel Pattern Recognition")
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded_file and st.button("Find Patterns"):
            df = pd.read_csv(uploaded_file)
            # Limpieza bruta para evitar errores
            df = df.astype(str) 
            data_sample = df.head(40).to_csv(index=False)
            prompt = f"{STRATEGIST_PERSONA}\nAnalyze this data:\n{data_sample}"
            res = generate_ai_response(prompt, GEMINI_KEY)
            st.markdown(res)

    # 2. Downloader
    with t2:
        st.header("📥 Downloader")
        url = st.text_input("YouTube URL:")
        if url and st.button("Get Link"):
            try:
                ydl_opts = {'quiet': True, 'format': 'best[ext=mp4]'}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    st.markdown(f"[Download MP4]({info['url']})")
            except Exception as e: st.error(e)

    # 3. Metadata
    with t3:
        st.header("👁️ Metadata Audit")
        url = st.text_input("Video URL for audit:")
        if url and st.button("Audit Thumbnail"):
            vid_id = url.split("v=")[-1][:11]
            img_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
            st.image(img_url, width=300)
            
            resp = requests.get(img_url)
            img = Image.open(io.BytesIO(resp.content))
            res = generate_ai_response(f"{STRATEGIST_PERSONA}\nRate this thumbnail 0-10.", GEMINI_KEY, img)
            st.markdown(res)

    # 4. Engagement (Placeholder simple para probar)
    with t4:
        st.header("💬 Engagement")
        st.info("Module under maintenance for API safety.")

    # 5. Competitors
    with t5:
        st.header("⚔️ Competitors")
        sel = st.selectbox("Competitor", list(COMPETITORS.keys()))
        if st.button("Analyze Competitor"):
            vids = get_recent_videos(COMPETITORS[sel], YT_KEY, limit=10)
            if vids:
                df = pd.DataFrame(vids)
                st.dataframe(df)
            else:
                st.error("No videos found (Check API Key quota)")

    # 6. Ideation (EL QUE FALLABA)
    with t6:
        st.header("💡 Ideation Lab")
        handle = st.text_input("Handle (e.g. @Sidemen):")
        if st.button("Generate Ideas"):
            with st.spinner("Processing..."):
                vids = get_recent_videos(handle, YT_KEY, limit=10)
                if vids:
                    titles = "\n".join([v['Title'] for v in vids])
                    prompt = f"{STRATEGIST_PERSONA}\nBased on these titles:\n{titles}\nGenerate 10 ideas."
                    res = generate_ai_response(prompt, GEMINI_KEY)
                    st.markdown(res)
                else:
                    st.error("Could not fetch videos. Check handle or API.")

if __name__ == "__main__":
    main()
