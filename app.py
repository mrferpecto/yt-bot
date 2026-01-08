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

# Competidores
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
Focus: Retention, CTR, and Algorithm Patterns.
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

# --- AI CORE ---
def get_available_model(api_key):
    genai.configure(api_key=api_key)
    try:
        models = genai.list_models()
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name: return m.name
        return 'models/gemini-1.5-flash'
    except: return 'models/gemini-1.5-flash'

def generate_ai_response(prompt, api_key, image=None):
    model_name = get_available_model(api_key)
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(model_name)
        inputs = [prompt, image] if image else prompt
        return model.generate_content(inputs).text
    except Exception as e:
        return f"⚠️ AI ERROR: {str(e)}"

def extract_json_from_ai(text):
    """Extrae JSON limpio de la respuesta de la IA"""
    try:
        # Busca el primer corchete [ o llave {
        match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except: pass
    return None

# --- INTERFAZ ---
def main():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 Login")
        user = st.text_input("User")
        pwd = st.text_input("Password", type="password")
        if st.button("Enter"):
            try:
                if user == st.secrets["login"]["username"] and pwd == st.secrets["login"]["password"]:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else: st.error("Wrong credentials")
            except: st.error("Secrets missing")
        return

    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except:
        st.error("Secrets configuration error.")
        st.stop()

    # TABS
    t1, t2, t3, t4, t5, t6 = st.tabs(["📊 Channel", "📥 Downloader", "👁️ Metadata", "💬 Engagement", "⚔️ Competitors", "💡 Ideation (Interactive)"])

    # 1. Channel
    with t1:
        st.header("📊 Channel Analysis")
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded_file and st.button("Analyze CSV"):
            df = pd.read_csv(uploaded_file)
            df = df.astype(str)
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

    # 4. Engagement (Placeholder)
    with t4:
        st.header("💬 Engagement")
        st.info("Module ready for expansion.")

    # 5. Competitors
    with t5:
        st.header("⚔️ Competitors")
        sel = st.selectbox("Select", list(COMPETITORS.keys()))
        if st.button("Scan"):
            vids = get_recent_videos(COMPETITORS[sel], YT_KEY)
            st.dataframe(pd.DataFrame(vids))

    # ==========================================
    # 6. IDEATION LAB (INTERACTIVE & CLICKABLE)
    # ==========================================
    with t6:
        st.header("💡 Ideation Lab (Interactive)")
        st.markdown("Generates clickable ideas. Click to expand and generate a full 13-25 min structure.")
        
        handle = st.text_input("Analyze Handle (e.g. @Sidemen):")
        
        # Estado para guardar las ideas generadas y no perderlas al clicar
        if "generated_ideas" not in st.session_state:
            st.session_state.generated_ideas = None

        if st.button("🚀 Generate 10 Viral Concepts"):
            with st.spinner("Analyzing channel DNA & Generating Concepts..."):
                vids = get_recent_videos(handle, YT_KEY, limit=10)
                if vids:
                    titles = "\n".join([v['Title'] for v in vids])
                    
                    # PROMPT ESPECIAL PARA JSON
                    prompt = f"""
                    {STRATEGIST_PERSONA}
                    Based on these successful titles:
                    {titles}
                    
                    Generate 10 NEW VIRAL VIDEO IDEAS tailored for this channel.
                    The format must be a valid JSON LIST of objects.
                    Each object must have:
                    - "title": The clickbaity title.
                    - "hook": A 1-sentence explanation of why it works.
                    
                    Example Output format:
                    [
                        {{"title": "I Spent 24H in a Freezer", "hook": "High stakes challenge..."}},
                        {{"title": "Sidemen vs Beta Squad", "hook": "Collab hype..."}}
                    ]
                    RETURN ONLY THE JSON.
                    """
                    
                    res = generate_ai_response(prompt, GEMINI_KEY)
                    ideas_json = extract_json_from_ai(res)
                    
                    if ideas_json:
                        st.session_state.generated_ideas = ideas_json
                        st.success("✅ Ideas generated! Click below to plan them.")
                    else:
                        st.error("AI returned invalid format. Try again.")
                        st.write(res) # Debug
                else:
                    st.error("Channel not found.")

        # RENDERIZADO DE LAS IDEAS CLICKABLES
        if st.session_state.generated_ideas:
            st.divider()
            st.subheader("🎬 Select an Idea to Blueprint")
            
            for i, idea in enumerate(st.session_state.generated_ideas):
                # Usamos expander para crear el efecto "Menú desplegable"
                with st.expander(f"📌 {i+1}. {idea.get('title', 'Unknown Title')}"):
                    st.write(f"**The Hook:** {idea.get('hook', '')}")
                    
                    # Botón único para cada idea
                    if st.button(f"⚡ Generate 20-Min Script Structure", key=f"btn_idea_{i}"):
                        with st.spinner("Architecting the perfect video..."):
                            deep_prompt = f"""
                            {STRATEGIST_PERSONA}
                            
                            TASK: Create a full production blueprint for a 13-25 minute YouTube video.
                            
                            TITLE: {idea.get('title')}
                            CONTEXT: Derived from a high-performance channel analysis.
                            
                            REQUIREMENTS:
                            1. **Thumbnail Concept:** Describe the visual.
                            2. **The Hook (0:00 - 1:30):** Exact scripting for the first minute to max retention.
                            3. **Pacing Structure (The Meat):** Break down the 15-20 minutes into 3-4 Acts/Segments. 
                            4. **Retention Spikes:** Where to add tension/twists to prevent drop-off.
                            5. **Outro/CTA:** Best way to convert subs.
                            6. **Optimized Description:** First 3 lines for SEO.
                            
                            Format nicely with Markdown.
                            """
                            
                            script_res = generate_ai_response(deep_prompt, GEMINI_KEY)
                            st.markdown(script_res)

if __name__ == "__main__":
    main()
