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

# Configuración
st.set_page_config(page_title="Front Three's AI Studio", page_icon="⚡", layout="wide")

# Database Competidores
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

# --- HELPERS ---
def get_channel_id(handle, api_key):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        r = youtube.search().list(part="id", q=handle, type="channel", maxResults=1).execute()
        if r['items']: return r['items'][0]['id']['channelId']
    except: return None

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
                "Competitor": channel_handle 
            })
        return videos
    except: return []

# --- AI CORE INTELIGENTE ---
def get_available_model(api_key):
    """Pregunta a Google qué modelos existen para evitar errores 404"""
    genai.configure(api_key=api_key)
    try:
        # Intenta listar modelos compatibles
        models = genai.list_models()
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                # Priorizar los rápidos si existen
                if 'flash' in m.name: return m.name
                if 'pro' in m.name: return m.name
        # Si no encuentra preferidos, devuelve el primero genérico
        return 'models/gemini-pro'
    except:
        # Fallback de emergencia si list_models falla
        return 'models/gemini-1.5-flash'

def generate_ai_response(prompt, api_key, image=None):
    # 1. Autodetectar modelo
    model_name = get_available_model(api_key)
    genai.configure(api_key=api_key)
    
    try:
        model = genai.GenerativeModel(model_name)
        inputs = [prompt, image] if image else prompt
        return model.generate_content(inputs).text
    except Exception as e:
        return f"⚠️ AI ERROR ({model_name}): {str(e)}"

# --- INTERFAZ ---
def main():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 Login")
        user = st.text_input("User")
        pwd = st.text_input("Password", type="password")
        if st.button("Enter"):
            # Comprobación de seguridad para que no explote si faltan secrets
            try:
                real_u = st.secrets["login"]["username"]
                real_p = st.secrets["login"]["password"]
            except:
                st.error("Secrets missing!")
                st.stop()
                
            if user == real_u and pwd == real_p:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Wrong credentials")
        return

    # Cargar API Keys
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except:
        st.error("Secrets missing. Check configuration.")
        st.stop()

    st.sidebar.info(f"System Ready 🟢")

    # TABS
    t1, t2, t3, t4, t5, t6 = st.tabs(["📊 Channel", "📥 Downloader", "👁️ Metadata", "💬 Engagement", "⚔️ Competitors", "💡 Ideation"])

    # 1. Channel
    with t1:
        st.header("📊 Channel Analysis")
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded_file and st.button("Analyze CSV"):
            df = pd.read_csv(uploaded_file)
            df = df.astype(str) # Evita TypeError
            data_sample = df.head(40).to_csv(index=False)
            prompt = f"{STRATEGIST_PERSONA}\nAnalyze this data:\n{data_sample}"
            res = generate_ai_response(prompt, GEMINI_KEY)
            st.markdown(res)

    # 2. Downloader
    with t2:
        st.header("📥 Downloader")
        url = st.text_input("URL:")
        if url and st.button("Get Link"):
            try:
                ydl_opts = {'quiet': True, 'format': 'best[ext=mp4]'}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    st.markdown(f"[Download MP4]({info['url']})")
            except Exception as e: st.error(e)

    # 3. Metadata
    with t3:
        st.header("👁️ Thumbnail Audit")
        url = st.text_input("Video URL for audit:")
        if url and st.button("Audit"):
            try:
                vid_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url).group(1)
                img_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
                st.image(img_url, width=300)
                resp = requests.get(img_url)
                img = Image.open(io.BytesIO(resp.content))
                res = generate_ai_response(f"{STRATEGIST_PERSONA}\nRate 0-10.", GEMINI_KEY, img)
                st.markdown(res)
            except: st.error("Error loading image")

    # 4. Engagement (Simplified)
    with t4:
        st.header("💬 Engagement")
        st.info("Coming soon")

    # 5. Competitors
    with t5:
        st.header("⚔️ Competitors")
        sel = st.selectbox("Select", list(COMPETITORS.keys()))
        if st.button("Scan"):
            vids = get_recent_videos(COMPETITORS[sel], YT_KEY)
            st.dataframe(pd.DataFrame(vids))

    # 6. Ideation (EL QUE FALLABA)
    with t6:
        st.header("💡 Ideation Lab")
        handle = st.text_input("Handle (e.g. @Sidemen):")
        if st.button("Generate Ideas"):
            with st.spinner("Analyzing..."):
                vids = get_recent_videos(handle, YT_KEY, limit=10)
                if vids:
                    titles = "\n".join([v['Title'] for v in vids])
                    prompt = f"{STRATEGIST_PERSONA}\nBased on these titles:\n{titles}\nGenerate 10 ideas."
                    # AQUÍ ESTÁ LA MAGIA: Usamos la función inteligente
                    res = generate_ai_response(prompt, GEMINI_KEY)
                    st.markdown(res)
                else:
                    st.error("No videos found. Check handle or API Quota.")

if __name__ == "__main__":
    main()
