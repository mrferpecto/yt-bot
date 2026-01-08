import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
import pandas as pd
import yt_dlp
import zipfile
import io
import time
import re
import requests

# --- CONFIGURATION ---
st.set_page_config(page_title="FrontThree Suite", page_icon="⚡", layout="wide")

# --- AUTHENTICATION ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.title("🔒 Restricted Access")
    st.markdown("Please log in to access the FrontThree Tools.")

    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password") 
        submit_button = st.form_submit_button("Login")

        if submit_button:
            try:
                real_user = st.secrets["login"]["username"]
                real_pass = st.secrets["login"]["password"]

                if username_input == real_user and password_input == real_pass:
                    st.session_state["authenticated"] = True
                    st.success("✅ Access Granted.")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Access Denied.")
            except KeyError:
                st.error("🚨 System Error: Secrets not configured correctly.")
    return False

# --- API HELPER FUNCTIONS ---

def get_video_stats_batch(video_ids, api_key):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        all_items = []
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i+50]
            request = youtube.videos().list(
                part="snippet,statistics",
                id=",".join(chunk)
            )
            response = request.execute()
            all_items.extend(response.get('items', []))
        return all_items
    except Exception as e:
        st.error(f"YouTube API Error: {e}")
        return []

def get_video_comments(video_id, api_key, max_limit=300):
    """Fetches comments with pagination up to max_limit."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        comments = []
        next_page_token = None
        
        # Loop to fetch multiple pages (Pagination)
        while len(comments) < max_limit:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100, # Max allowed per page
                textFormat="plainText",
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response['items']:
                text = item['snippet']['topLevelComment']['snippet']['textDisplay']
                comments.append(text)
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break # No more comments
                
        return comments
    except Exception as e:
        st.error(f"Error fetching comments: {e}")
        return comments # Return whatever we got so far

def download_thumbnail_bytes(url):
    try:
        ydl_opts = {'quiet': True, 'writethumbnail': True, 'skip_download': True, 'outtmpl': '-'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumb_url = info['thumbnail']
            # Direct request to image URL
            response = requests.get(thumb_url)
            safe_title = re.sub(r'[\\/*?:"<>|]', "", info['title'])
            return response.content, f"{safe_title[:30]}.jpg"
    except Exception as e:
        return None, str(e)

# --- AI WRAPPER (THE FALLBACK FIX) ---
def ask_gemini(prompt, api_key):
    """Tries Flash first, falls back to Pro if it fails."""
    genai.configure(api_key=api_key)
    
    # Intento 1: Flash (Rápido)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        return model.generate_content(prompt).text
    except Exception:
        # Intento 2: Pro (Estándar - Fallback)
        try:
            model = genai.GenerativeModel('gemini-pro')
            return model.generate_content(prompt).text
        except Exception as e:
            return f"❌ AI Error: {e}. (Check requirements.txt version)"

# --- MAIN APPLICATION ---

def main_app():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except KeyError:
        st.error("🚨 API Keys missing in secrets.")
        st.stop()

    st.sidebar.success(f"User: {st.secrets['login']['username']}")
    if st.sidebar.button("Logout"):
        st.session_state["authenticated"] = False
        st.rerun()

    st.title("⚡ FrontThree YT Management Suite")
    tab1, tab2, tab3 = st.tabs(["📊 Analytics Chat", "📥 Downloader", "🔴 Deep Dive"])

    # TAB 1: ANALYTICS
    with tab1:
        st.header("🧠 Chat with your Data")
        urls_input = st.text_area("Paste Video URLs:", height=100)
        
        if "analytics_data" not in st.session_state:
            st.session_state.analytics_data = None

        if st.button("Load Data"):
            ids = list(set(re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", urls_input)))
            if ids:
                with st.spinner(f"Analyzing {len(ids)} videos..."):
                    raw_data = get_video_stats_batch(ids, YT_KEY)
                    clean_data = [{
                        "Title": item['snippet']['title'],
                        "Views": int(item['statistics'].get('viewCount', 0)),
                        "Likes": int(item['statistics'].get('likeCount', 0)),
                        "Comments": int(item['statistics'].get('commentCount', 0)),
                        "Date": item['snippet']['publishedAt'][:10]
                    } for item in raw_data]
                    st.session_state.analytics_data = pd.DataFrame(clean_data)
                    st.success("✅ Data Loaded!")
            else:
                st.warning("No valid URLs.")

        if st.session_state.analytics_data is not None:
            st.dataframe(st.session_state.analytics_data, hide_index=True)
            if "messages" not in st.session_state: st.session_state.messages = []
            
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]): st.markdown(msg["content"])

            if prompt := st.chat_input("Ask about your data..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        context = st.session_state.analytics_data.to_string()
                        full_prompt = f"Data:\n{context}\n\nUser Question: {prompt}\nAnswer in English."
                        response = ask_gemini(full_prompt, GEMINI_KEY)
                        st.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})

    # TAB 2: DOWNLOADER
    with tab2:
        st.header("📥 Downloader")
        st.info("ℹ️ Note: Cloud downloads are limited to the best single file (usually 720p) to preserve audio. For 1080p/4K, run this tool locally.")
        
        dl_urls = st.text_area("Paste URLs to download:", key="dl_area")
        video_ids = list(set(re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_urls)))
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Download Thumbnails (ZIP)"):
                if video_ids:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        prog = st.progress(0)
                        for i, vid in enumerate(video_ids):
                            d, n = download_thumbnail_bytes(f"https://youtu.be/{vid}")
                            if d: zf.writestr(n, d)
                            prog.progress((i+1)/len(video_ids))
                    st.download_button("⬇️ Download ZIP", zip_buffer.getvalue(), "thumbs.zip", "application/zip")

        with col2:
            if st.button("Get Video Links"):
                if video_ids:
                    for vid in video_ids:
                        try:
                            # Search for best MP4 that HAS audio
                            with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
                                info = ydl.extract_info(f"https://youtu.be/{vid}", download=False)
                                
                                # Filter formats manually to get best resolution with audio
                                best_url = None
                                best_res = 0
                                
                                for f in info['formats']:
                                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                                        height = f.get('height', 0)
                                        if height > best_res:
                                            best_res = height
                                            best_url = f['url']
                                
                                if best_url:
                                    st.markdown(f"🎥 **{info['title']}** ({best_res}p): [Download MP4]({best_url})")
                                else:
                                    st.warning(f"No direct link found for {info['title']}")
                        except: st.error(f"Error: {vid}")

    # TAB 3: DEEP DIVE
    with tab3:
        st.header("🔴 Single Video Analysis")
        sv_url = st.text_input("URL:")
        task = st.selectbox("Action:", ["Summarize Comments", "Generate Video Ideas", "Detect Questions", "SEO Optimization"])
        
        if st.button("Analyze"):
            vid = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", sv_url)
            if vid:
                with st.spinner("Fetching UP TO 300 comments..."):
                    # Using the new pagination function
                    comments = get_video_comments(vid.group(1), YT_KEY, max_limit=300)
                
                if comments:
                    st.success(f"Successfully analyzed {len(comments)} comments!")
                    
                    # Truncate text if it's too huge for Gemini (Safety limit)
                    full_text = "\n".join(comments)
                    if len(full_text) > 30000: 
                        full_text = full_text[:30000] + "\n...(truncated)"
                    
                    prompts = {
                        "Summarize Comments": f"Summarize sentiment and key topics:\n{full_text}",
                        "Generate Video Ideas": f"Suggest 5 future video ideas based on this feedback:\n{full_text}",
                        "Detect Questions": f"Extract unanswered questions asking for help:\n{full_text}",
                        "SEO Optimization": f"Generate SEO tags and description based on:\n{full_text}"
                    }
                    with st.spinner("Gemini is thinking..."):
                        response = ask_gemini(prompts[task], GEMINI_KEY)
                        st.markdown("### 🤖 Results")
                        st.markdown(response)
                else: st.warning("No comments found.")

if __name__ == "__main__":
    if check_login():
        main_app()
