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

# Configuración visual segura
try:
    from wordcloud import WordCloud
    import matplotlib.pyplot as plt
    WORDCLOUD_AVAILABLE = True
except ImportError:
    WORDCLOUD_AVAILABLE = False

# --- CONFIGURACIÓN ---
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

# --- PERSONA QUIRÚRGICA ---
STRATEGIST_PERSONA = """
Role: Senior YouTube Strategist.
Tone: Surgical, Brutally Direct, No Fluff.
Rules:
1. NO INTROS. Start directly with the insight.
2. Be specific ("Switch red font to yellow").
3. Max 300 words. Bullet points only.
4. If analysing retention, correlate it with the topic/hook.
"""

# --- LOGIN ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]: return True

    st.title("🔒 Front Three's AI Studio")
    
    # Verificación silenciosa de secretos
    try:
        real_user = st.secrets["login"]["username"]
        real_pass = st.secrets["login"]["password"]
    except:
        st.error("🚨 Error: Secretos no configurados.")
        return False

    with st.form("login"):
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Enter System"):
            if user == real_user and pwd == real_pass:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Invalid Credentials")
    return False

# --- AI CORE (AUTO-DETECT) ---
def get_best_available_model(api_key):
    genai.configure(api_key=api_key)
    try:
        # Preguntar a la cuenta qué modelos tiene
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Lista de preferencia (Nuevos -> Viejos)
        priority_list = [
            'models/gemini-2.5-flash', 
            'models/gemini-2.0-flash', 
            'models/gemini-1.5-flash',
            'models/gemini-1.5-pro'
        ]
        
        for p in priority_list:
            if p in available_models: return p
            
        # Si no, devolver el primero disponible
        return available_models[0] if available_models else None
    except: return None

def generate_ai_response(prompt, api_key, image=None):
    genai.configure(api_key=api_key)
    model_name = get_best_available_model(api_key)
    
    if not model_name: return "❌ AI Error: No models found/authorized."

    try:
        model = genai.GenerativeModel(model_name)
        inputs = [prompt, image] if image else prompt
        return model.generate_content(inputs).text
    except Exception as e:
        if "429" in str(e): return "⚠️ Tráfico Alto (Quota Limit). Espera 30s."
        return f"AI Error ({model_name}): {e}"

def extract_json_from_ai(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match: return json.loads(match.group(0))
    except: pass
    return None

def download_image_from_url(url):
    try:
        resp = requests.get(url, stream=True)
        return Image.open(io.BytesIO(resp.content))
    except: return None

# --- YOUTUBE API (HYBRID SEARCH) ---
def get_video_id_by_title(title, api_key):
    """Busca video por título. Maneja errores si no encuentra nada."""
    if not title or pd.isna(title): return None
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        # Busca solo en videos para ser más preciso
        search_response = youtube.search().list(
            q=str(title), 
            part="id", 
            maxResults=1, 
            type="video"
        ).execute()
        
        if search_response['items']:
            return search_response['items'][0]['id']['videoId']
    except: return None
    return None

def get_deep_video_details(video_id, api_key):
    if not video_id: return None
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        vid_req = youtube.videos().list(part="snippet,statistics", id=video_id).execute()
        if not vid_req['items']: return None
        item = vid_req['items'][0]
        
        comments = []
        try:
            c_req = youtube.commentThreads().list(part="snippet", videoId=video_id, maxResults=10, textFormat="plainText", order="relevance").execute()
            comments = [c['snippet']['topLevelComment']['snippet']['textDisplay'] for c in c_req['items']]
        except: comments = ["Comments disabled/Hidden"]
        
        return {
            "Title": item['snippet']['title'],
            "Tags": item['snippet'].get('tags', []),
            "Comments Sample": comments
        }
    except: return None

# --- GENERAL API UTILS ---
def get_channel_id(handle, api_key):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        r = youtube.search().list(part="id", q=handle, type="channel", maxResults=1).execute()
        if r['items']: return r['items'][0]['id']['channelId']
    except: return None

@st.cache_data(ttl=3600) 
def get_recent_videos(channel_handle, api_key, limit=20):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
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

# --- TABS ---

def tab_channel_analyzer(api_key):
    st.header("📊 Channel Analyzer (Hybrid Engine)")
    st.info("Subida de CSV + Búsqueda Live en YouTube (Top 3 / Flop 3).")
    
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
    
    if uploaded_file and st.button("🧠 Run Hybrid Analysis"):
        try:
            df = pd.read_csv(uploaded_file)
            
            # Limpieza de nombres de columnas
            possible_title_cols = [c for c in df.columns if 'title' in c.lower() or 'título' in c.lower()]
            possible_view_cols = [c for c in df.columns if 'views' in c.lower() or 'visualizaciones' in c.lower()]
            
            if not possible_title_cols or not possible_view_cols:
                st.error("Error CSV: No se encuentran columnas de 'Title' o 'Views'.")
                return

            title_col = possible_title_cols[0]
            view_col = possible_view_cols[0]
            
            # Limpiar datos nulos y asegurar tipos
            df = df.dropna(subset=[title_col, view_col])
            df[view_col] = pd.to_numeric(df[view_col], errors='coerce').fillna(0)
            
            # Top y Flop
            df_sorted = df.sort_values(by=view_col, ascending=False)
            top_3 = df_sorted.head(3)
            flop_3 = df_sorted.tail(3)
            targets = pd.concat([top_3, flop_3])
            
            enriched_data = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total_items = len(targets)
            
            for i, (index, row) in enumerate(targets.iterrows()):
                # FIX: Convertir explícitamente a string para evitar TypeError
                title = str(row[title_col])
                views = row[view_col]
                
                status_text.text(f"🛰️ Deep Scanning: {title[:40]}...")
                
                # Pausa para evitar error 429
                time.sleep(1.5) 
                
                vid_id = get_video_id_by_title(title, api_key)
                live_data = None
                
                if vid_id:
                    live_data = get_deep_video_details(vid_id, api_key)
                
                enriched_data.append({
                    "CSV_Title": title,
                    "CSV_Views": views,
                    "Live_Comments": live_data['Comments Sample'] if live_data else "N/A",
                    "Status": "Top Performer" if i < 3 else "Underperformer"
                })
                
                progress_bar.progress((i + 1) / total_items)
                
            progress_bar.empty()
            status_text.empty()
            
            # Prompt Quirúrgico
            prompt = f"""
            {STRATEGIST_PERSONA}
            
            TASK: Hybrid Analysis (CSV Metrics + Live Audience Sentiment).
            DEEP DATA SET:
            {json.dumps(enriched_data, indent=2)}
            
            OUTPUT:
            1. 🟢 **WINNING FORMULA:** (Correlate Views with Comment Sentiment).
            2. 🔴 **FLOP DIAGNOSIS:** (Why did they fail?).
            3. ⚡ **3 SURGICAL ACTIONS:** Specific changes for next upload.
            """
            
            with st.spinner("Synthesizing Report..."):
                res = generate_ai_response(prompt, api_key)
                st.markdown(res)
                
        except Exception as e:
            st.error(f"Error procesando el archivo: {e}")

def tab_downloader():
    st.header("📥 Downloader")
    url = st.text_input("Paste YouTube URL:")
    if url:
        vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
        if vid_match:
            vid_id = vid_match.group(1)
            c1, c2 = st.columns(2)
            with c1:
                st.info("🖼️ **THUMBNAIL**")
                img_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
                st.image(img_url, use_container_width=True)
                st.markdown(f"[⬇️ Download JPG]({img_url})")
            with c2:
                st.success("🎥 **VIDEO**")
                if st.button("Generate Video Link", use_container_width=True):
                    with st.spinner("Processing..."):
                        try:
                            ydl_opts = {'quiet': True, 'format': 'best[height<=720][ext=mp4]/best[ext=mp4]', 'extractor_args': {'youtube': {'player_client': ['android', 'web']}}}
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(url, download=False)
                                st.markdown(f"### [👉 Click to Download MP4]({info['url']})")
                        except Exception as e: st.error(f"Error: {e}")

def tab_metadata_analyzer(api_key):
    st.header("👁️ Metadata Audit")
    c1, c2 = st.columns(2)
    img = None
    with c1:
        u = st.text_input("YouTube URL:")
        if u:
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", u)
            if vid_match:
                img = download_image_from_url(f"https://img.youtube.com/vi/{vid_match.group(1)}/maxresdefault.jpg")
    with c2:
        up = st.file_uploader("Or Upload Image", type=['jpg','png'])
        if up: img = Image.open(up)
    if img:
        st.image(img, width=350)
        if st.button("🎯 Rate Thumbnail"):
            with st.spinner("Auditing..."):
                prompt = f"{STRATEGIST_PERSONA}\nRate thumbnail 0-10. JSON: {{'Legibility':0, 'Emotion':0, 'Contrast':0, 'Curiosity':0}}\nShort specific critique."
                res = generate_ai_response(prompt, api_key, img)
                data = extract_json_from_ai(res)
                if data:
                    fig = go.Figure(data=go.Scatterpolar(r=list(data.values()), theta=list(data.keys()), fill='toself'))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                st.write(res.replace("{", "").replace("}", "") if data else res)

def tab_engagement_room(api_key):
    st.header("💬 Engagement Visualizer")
    url = st.text_input("Video URL:", key="eng_url")
    if st.button("⚡ Analyze"):
        with st.spinner("Fetching..."):
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
            if vid_match:
                data = get_deep_video_details(vid_match.group(1), api_key)
                if data and data['Comments Sample']:
                    text = " ".join(data['Comments Sample'])
                    if WORDCLOUD_AVAILABLE:
                        wc = WordCloud(width=800, height=300, background_color='black').generate(text)
                        fig, ax = plt.subplots(figsize=(10, 4))
                        ax.imshow(wc, interpolation='bilinear'); ax.axis("off")
                        st.pyplot(fig)
                    prompt = f"Analyze sentiment: '{text[:1000]}'. JSON: {{'Positive':0, 'Neutral':0, 'Negative':0}}"
                    res = generate_ai_response(prompt, api_key)
                    s_data = extract_json_from_ai(res)
                    if s_data:
                        fig = px.pie(values=list(s_data.values()), names=list(s_data.keys()), hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                        st.plotly_chart(fig, use_container_width=True)
                    st.write(generate_ai_response(f"Specific insights from comments: {text[:1000]}", api_key))
                else: st.error("No comments found.")

def tab_competitor_analysis(api_key):
    st.header("⚔️ Competitor Heatmaps")
    sel = st.multiselect("Select Rivals:", list(COMPETITORS.keys()), default=["Sidemen"], max_selections=3)
    if st.button("Generate"):
        with st.spinner("Scouting..."):
            all_vids = []
            for name in sel:
                vids = get_recent_videos(COMPETITORS[name], api_key, limit=20)
                for v in vids: v['Competitor'] = name
                all_vids.extend(vids)
            df = pd.DataFrame(all_vids)
            if not df.empty:
                df['Published_DT'] = pd.to_datetime(df['Published'])
                df['Hour'] = df['Published_DT'].dt.hour
                df['Day'] = df['Published_DT'].dt.day_name()
                c1, c2 = st.columns(2)
                with c1:
                    fig = px.density_heatmap(df, x="Hour", y="Day", z="Views", color_continuous_scale="Magma")
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    fig2 = px.scatter(df, x="Views", y="Likes", size="Comments", color="Competitor", hover_name="Title")
                    st.plotly_chart(fig2, use_container_width=True)
            else: st.warning("No data found.")

def tab_ideation(api_key):
    st.header("💡 Ideation Lab")
    handle = st.text_input("Handle (e.g. @Sidemen):")
    if st.button("Generate Ideas"):
        with st.spinner("Thinking..."):
            vids = get_recent_videos(handle, api_key, limit=10)
            if vids:
                titles = "\n".join([v['Title'] for v in vids])
                prompt = f"{STRATEGIST_PERSONA}\nBased on:\n{titles}\nGenerate 10 VIRAL IDEAS."
                res = generate_ai_response(prompt, api_key)
                st.markdown(res)
            else: st.error("Channel not found.")

# --- MAIN ---
def main():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except: st.stop()

    if check_login():
        t1, t2, t3, t4, t5, t6 = st.tabs(["📊 Channel", "📥 Downloader", "👁️ Metadata", "💬 Engagement", "⚔️ Competitors", "💡 Ideation"])
        with t1: tab_channel_analyzer(GEMINI_KEY)
        with t2: tab_downloader()
        with t3: tab_metadata_analyzer(GEMINI_KEY)
        with t4: tab_engagement_room(GEMINI_KEY)
        with t5: tab_competitor_analysis(YT_KEY)
        with t6: tab_ideation(YT_KEY)

if __name__ == "__main__":
    main()
