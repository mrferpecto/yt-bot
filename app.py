import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
import pandas as pd
import yt_dlp
import os
import zipfile
import io
import time
import re

# --- CONFIGURATION ---
st.set_page_config(page_title="FrontThree Suite", page_icon="⚡", layout="wide")

# --- AUTHENTICATION ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]: return True

    st.title("🔒 Debug Mode Login")
    
    # --- ZONA DE DIAGNÓSTICO ---
    st.write("--- INFO DE SECRETOS ---")
    try:
        # 1. Verificar si existen secretos
        if not st.secrets:
            st.error("❌ st.secrets está VACÍO. La app no detecta ninguna configuración en la nube.")
            st.info("Pista: Asegúrate de haber pegado los secretos en 'App Settings > Secrets' y haber guardado.")
        else:
            st.success("✅ st.secrets detectado.")
            # 2. Imprimir las secciones disponibles (sin mostrar contraseñas)
            st.write(f"Secciones encontradas: {list(st.secrets.keys())}")
            
            if "login" in st.secrets:
                st.write("✅ Sección [login] encontrada.")
                st.write(f"Claves dentro de login: {list(st.secrets['login'].keys())}")
            else:
                st.error("❌ NO se encuentra la sección [login].")
                st.text("Streamlit ve esto:")
                st.write(st.secrets)

    except Exception as e:
        st.error(f"💥 Error crítico leyendo secretos: {e}")
    # ---------------------------

    with st.form("login"):
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            try:
                # Intento directo sin try/except genérico
                real_user = st.secrets["login"]["username"]
                real_pass = st.secrets["login"]["password"]
                
                if user == real_user and password == real_pass:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error(f"❌ Incorrecto. Tú pusiste: '{user}'")
            except Exception as e:
                st.error(f"❌ Error al validar: {e}")
                
    return False

# --- API HELPERS ---
def get_channel_videos(api_key, max_results=20):
    """Fetches stats for the latest N videos from a channel ID (derived from search)"""
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # 1. Get Channel Uploads Playlist ID (Requires Channel ID logic, simplified here to search 'mine' or user input)
    # Note: Search is expensive on quota. Using a simplified search for specific channel handle or keyword.
    # For this demo, we will search for videos by a specific channel ID provided by user or use generic search
    # TO KEEP IT SIMPLE: We will analyze a list of IDs provided or search by a Handle.
    pass 
    # *Simplified for this script*: We will fetch stats for a list of Video URLs provided by user in the Chat section
    # to avoid complex Channel ID extraction logic in this snippet.

def get_video_details(video_ids, api_key):
    """Get stats for a list of video IDs"""
    youtube = build('youtube', 'v3', developerKey=api_key)
    request = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids)
    )
    response = request.execute()
    return response['items']

def download_video_yt_dlp(url, type="video"):
    """Downloads video or thumbnail to a buffer using yt-dlp"""
    buffer = io.BytesIO()
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }

    if type == "thumbnail":
        ydl_opts['writethumbnail'] = True
        ydl_opts['skip_download'] = True
        ydl_opts['outtmpl'] = '-' # Pipe to stdout
    else:
        # Video download (Warning: Heavy for Cloud)
        ydl_opts['format'] = 'best[ext=mp4]/best'
        ydl_opts['outtmpl'] = '-' 
    
    # Note: yt-dlp streaming to memory buffer is complex in Streamlit Cloud.
    # We will use a simpler approach: Download to temp file then read to buffer.
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if type == "thumbnail":
                # Get the best thumbnail URL
                thumb_url = info['thumbnail']
                import requests
                img_data = requests.get(thumb_url).content
                return img_data, f"{info['title']}.jpg"
            else:
                # For video, we return the direct URL or info for this demo 
                # because downloading 100MB+ to RAM in cloud will crash.
                return info['url'], f"{info['title']}.mp4"
    except Exception as e:
        return None,str(e)

# --- MAIN APP ---
def main_app():
    # Load Keys
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except:
        st.error("API Keys missing.")
        st.stop()

    st.sidebar.title("⚡ Navigation")
    
    # TABS STRUCTURE
    tab1, tab2, tab3 = st.tabs(["📊 Global Analytics & Chat", "📥 Downloader Center", "🔴 Single Video Deep-Dive"])

    # ==========================================
    # TAB 1: GLOBAL ANALYTICS & CHAT
    # ==========================================
    with tab1:
        st.header("🧠 Chat with your Channel Data")
        st.info("Paste a list of video URLs to analyze patterns, best thumbnails, and SEO.")

        # Batch Input
        urls_input = st.text_area("Paste Video URLs (comma or newline separated):", height=100)
        
        if "analytics_df" not in st.session_state:
            st.session_state.analytics_df = None

        if st.button("Fetch Data & Initialize Brain"):
            # Extract IDs
            import re
            ids = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", urls_input)
            ids = list(set(ids)) # Remove duplicates
            
            if not ids:
                st.warning("No valid YouTube URLs found.")
            else:
                with st.spinner(f"Analyzing {len(ids)} videos..."):
                    data = get_video_details(ids, YT_KEY)
                    
                    # Process into simple structure for AI
                    clean_data = []
                    for item in data:
                        stats = item['statistics']
                        snippet = item['snippet']
                        clean_data.append({
                            "Title": snippet['title'],
                            "Views": int(stats.get('viewCount', 0)),
                            "Likes": int(stats.get('likeCount', 0)),
                            "Comments": int(stats.get('commentCount', 0)),
                            "Tags": str(snippet.get('tags', [])),
                            "Date": snippet['publishedAt']
                        })
                    
                    st.session_state.analytics_df = pd.DataFrame(clean_data)
                    st.success("✅ Data Loaded into AI Memory!")

        # The Chat Interface
        if st.session_state.analytics_df is not None:
            st.dataframe(st.session_state.analytics_df, hide_index=True)
            
            st.markdown("---")
            st.subheader("💬 Ask the Bot")
            
            # Initialize Chat History
            if "messages" not in st.session_state:
                st.session_state.messages = []

            # Display History
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # Chat Input
            if prompt := st.chat_input("Ex: Which video has the best engagement?"):
                # Add user message
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                # Generate AI Response
                with st.chat_message("assistant"):
                    with st.spinner("Analyzing data..."):
                        # Prepare Context
                        data_context = st.session_state.analytics_df.to_string()
                        full_prompt = (
                            f"You are a YouTube Strategy Expert. Here is the data of my videos:\n{data_context}\n\n"
                            f"User Question: {prompt}\n"
                            f"Answer based strictly on the data provided. Be insightful."
                        )
                        
                        genai.configure(api_key=GEMINI_KEY)
                        model = genai.GenerativeModel('gemini-pro')
                        response = model.generate_content(full_prompt)
                        
                        st.markdown(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": response.text})

    # ==========================================
    # TAB 2: DOWNLOADER CENTER
    # ==========================================
    with tab2:
        st.header("📥 Media Downloader")
        st.warning("⚠️ Cloud Warning: Downloading large videos (MP4) may fail on Streamlit Cloud due to memory limits. Use Local for best results.")

        dl_urls = st.text_area("Paste URLs for Download (Comma separated):")
        
        col1, col2 = st.columns(2)
        
        if col1.button("Process for Thumbnails"):
            urls = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_urls)
            if urls:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    progress_bar = st.progress(0)
                    for i, vid_id in enumerate(urls):
                        full_url = f"https://www.youtube.com/watch?v={vid_id}"
                        data, name = download_video_yt_dlp(full_url, type="thumbnail")
                        if data:
                            zf.writestr(name, data)
                        progress_bar.progress((i + 1) / len(urls))
                
                st.success("Thumbnails Ready!")
                st.download_button(
                    label="Download All Thumbnails (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="thumbnails.zip",
                    mime="application/zip"
                )

        if col2.button("Get MP4 Download Links"):
            st.info("Direct downloading to server is disabled for stability. Generating direct high-speed links instead.")
            urls = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_urls)
            if urls:
                for vid_id in urls:
                    full_url = f"https://www.youtube.com/watch?v={vid_id}"
                    try:
                        with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
                            info = ydl.extract_info(full_url, download=False)
                            st.write(f"**{info['title']}**")
                            # Looking for best MP4
                            for f in info['formats']:
                                if f.get('ext') == 'mp4' and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                                    st.markdown(f"[Click to Download (MP4)]({f['url']})")
                                    break
                    except:
                        st.error(f"Could not fetch link for ID {vid_id}")

    # ==========================================
    # TAB 3: SINGLE VIDEO (Legacy)
    # ==========================================
    with tab3:
        st.header("🔴 Single Video Deep Dive")
        # (This uses the logic from previous version, simplified here)
        sv_url = st.text_input("Video URL:", key="sv_input")
        if st.button("Analyze Single Video"):
            # Reuse your logic here for comments extraction
            st.info("This section connects to the logic we built in the previous step (Get Comments -> Analyze).")
            # You can paste the previous logic here inside this block.

if __name__ == "__main__":
    if check_login():
        main_app()
