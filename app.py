import streamlit as st
import json
import io
from pydub import AudioSegment
from elevenlabs import ElevenLabs, VoiceSettings
import requests
import os
import base64
import database  # Import our database module
import uuid

# Initialize session state for API key
if 'api_key' not in st.session_state:
    st.session_state.api_key = st.secrets.get("ELEVENLABS_API_KEY", "")  # Get from secrets or empty string
    if not st.session_state.api_key:
        st.error("Please set up your ElevenLabs API key in the app settings")

# Function to initialize ElevenLabs client
def init_elevenlabs_client():
    return ElevenLabs(api_key=st.session_state.api_key)

# Get available voices from ElevenLabs
def get_available_voices():
    try:
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {
            "Accept": "application/json",
            "xi-api-key": st.session_state.api_key
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            voices_data = response.json()
            voices = {voice["name"]: {"voice_id": voice["voice_id"], "samples": voice.get("samples", [])} 
                     for voice in voices_data["voices"]}
            if not voices:
                st.error("No voices found in the ElevenLabs response")
                return {"Default Voice": {"voice_id": "21m00Tcm4TlvDq8ikWAM", "samples": []}}  # Default voice
            return voices
        else:
            st.error(f"Failed to fetch voices: {response.status_code}")
            # Return a default voice if API call fails
            return {"Default Voice": {"voice_id": "21m00Tcm4TlvDq8ikWAM", "samples": []}}
    except Exception as e:
        st.error(f"Error fetching voices: {str(e)}")
        # Return a default voice if anything fails
        return {"Default Voice": {"voice_id": "21m00Tcm4TlvDq8ikWAM", "samples": []}}

# Function to get and play voice sample
def get_voice_sample(voice_id, sample_id):
    try:
        client = init_elevenlabs_client()
        audio_data = client.samples.get_audio(voice_id=voice_id, sample_id=sample_id)
        return audio_data
    except Exception as e:
        st.error(f"Failed to get voice sample: {str(e)}")
        return None

# Function to load or initialize session state
def init_session_state():
    if 'script' not in st.session_state:
        st.session_state.script = []
    if 'config' not in st.session_state:
        st.session_state.config = {
            'intro_text': '',
            'intro_voice': '',
            'outro_text': '',
            'outro_voice': '',
            'intro_music': None,
            'podcasters': {},
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.8,
                'style': 0.1,
            }
        }
    if 'audio_segments' not in st.session_state:
        st.session_state.audio_segments = []
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 2
    if 'available_voices' not in st.session_state:
        st.session_state.available_voices = get_available_voices()

# Function to generate audio for a single line
def generate_audio(text, voice_id, speaker):
    client = init_elevenlabs_client()
    voice_settings = st.session_state.config['voice_settings_per_speaker'][speaker]
    settings = VoiceSettings(
        stability=voice_settings['stability'],
        similarity_boost=voice_settings['similarity_boost'],
        style=voice_settings['style']
    )
    audio_stream = client.text_to_speech.convert(
        voice_id=voice_id,
        optimize_streaming_latency=0,
        output_format="mp3_44100_128",
        text=text,
        voice_settings=settings,
        model_id="eleven_multilingual_v2",
    )
    audio_data = b''.join(chunk for chunk in audio_stream)
    return AudioSegment.from_mp3(io.BytesIO(audio_data))

# Function to display masked API key
def display_masked_api_key():
    if st.session_state.api_key:
        masked_key = st.session_state.api_key[:4] + "*" * (len(st.session_state.api_key) - 8) + st.session_state.api_key[-4:]
        st.sidebar.text(f"API Key: {masked_key}")

# Add this function near the top of the file, after the imports
def update_step(new_step):
    st.session_state.current_step = new_step

# Step 2: JSON Input
def step_2():
    st.header("Step 1: Input Script")
    
    # Add format selection
    input_format = st.radio("Select input format:", ["JSON", "Text Format"], index=1)
    
    if input_format == "JSON":
        json_input = st.text_area("Paste your JSON script here (format: [{'speaker': 'name', 'text': 'content'}, ...]):", height=300)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Load Script"):
                try:
                    script_data = json.loads(json_input)
                    if isinstance(script_data, list) and all(isinstance(item, dict) and 'speaker' in item and 'text' in item for item in script_data):
                        st.session_state.script = script_data
                        st.success("Script loaded successfully!")
                        st.session_state.script_loaded = True
                    else:
                        st.error("Invalid script format. Please ensure your JSON is a list of objects with 'speaker' and 'text' keys.")
                except json.JSONDecodeError:
                    st.error("Invalid JSON. Please check your input.")
        
        with col2:
            if st.button("Export Script"):
                script_json = json.dumps(st.session_state.script, indent=2)
                b64 = base64.b64encode(script_json.encode()).decode()
                href = f'<a href="data:application/json;base64,{b64}" download="podcast_script.json">Download JSON</a>'
                st.markdown(href, unsafe_allow_html=True)
    else:
        text_input = st.text_area("Paste your script here (format: Intro, Speaker sections, and Outro separated by '-------------'):", height=400)
        
        if st.button("Convert and Load Script"):
            try:
                # Split the text into sections
                sections = text_input.split('-------------')
                script_data = []
                
                # Process each section
                for section in sections:
                    section = section.strip()
                    if not section:
                        continue
                    # Check if it's an intro or outro
                    if section.startswith('Intro:'):
                        script_data.append({
                            'speaker': 'Presenter',
                            'text': section.replace('Intro:', '').strip()
                        })
                    elif section.startswith('Outro:'):
                        script_data.append({
                            'speaker': 'Presenter',
                            'text': section.replace('Outro:', '').strip()
                        })
                    else:
                        # Process speaker sections
                        lines = section.split('\n')
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            if ':' in line:
                                speaker, text = line.split(':', 1)
                                # If the speaker is 'Intro' or 'Outro', force to 'Presenter'
                                if speaker.strip() in ['Intro', 'Outro']:
                                    speaker = 'Presenter'
                                script_data.append({
                                    'speaker': speaker.strip(),
                                    'text': text.strip()
                                })
                
                if script_data:
                    st.session_state.script = script_data
                    st.success("Script converted and loaded successfully!")
                    st.session_state.script_loaded = True
                else:
                    st.error("No valid script content found. Please check your input format.")
            except Exception as e:
                st.error(f"Error processing script: {str(e)}")
        # Show 'Proceed to Edit Script' button if script was loaded
        if st.session_state.get('script_loaded', False):
            st.button("Proceed to Edit Script", on_click=update_step, args=(3,))
    
    uploaded_file = st.file_uploader("Import Script from JSON", type="json")
    if uploaded_file is not None:
        try:
            imported_script = json.load(uploaded_file)
            if isinstance(imported_script, list) and all(isinstance(item, dict) and 'speaker' in item and 'text' in item for item in imported_script):
                st.session_state.script = imported_script
                st.success("Script imported successfully!")
                st.session_state.current_step = 3
            else:
                st.error("Invalid script format in the imported file.")
        except json.JSONDecodeError:
            st.error("Invalid JSON in the imported file.")

# Step 3: Display and Edit Script
def step_3():
    st.header("Step 2: Edit Script")
    # Ensure each dialog has a unique 'uid'
    for dialog in st.session_state.script:
        if 'uid' not in dialog:
            dialog['uid'] = str(uuid.uuid4())
    for i, line in enumerate(st.session_state.script):
        uid = line['uid']
        with st.expander(f"Dialog {i+1}", expanded=True):
            is_intro = line['text'].startswith('Intro:')
            is_outro = line['text'].startswith('Outro:')
            if is_intro or is_outro:
                st.session_state.script[i]['speaker'] = 'Presenter'
                st.text_input("Speaker", 'Presenter', key=f"speaker_{uid}", disabled=True)
            else:
                st.session_state.script[i]['speaker'] = st.text_input("Speaker", line['speaker'], key=f"speaker_{uid}")
            st.session_state.script[i]['text'] = st.text_area("Dialog", line['text'], key=f"line_{uid}", height=100)
            col_add, col_delete = st.columns([1, 1])
            with col_add:
                if st.button("➕ Add Dialog Below", key=f"add_below_{uid}"):
                    st.session_state.script.insert(i+1, {"speaker": "", "text": "", "uid": str(uuid.uuid4())})
                    st.rerun()
            with col_delete:
                if st.button("🗑️ Delete Dialog", key=f"delete_{uid}"):
                    st.session_state.script.pop(i)
                    st.rerun()
    st.button("Proceed to Configuration", on_click=update_step, args=(4,))

# Step 4: Configuration
def step_4():
    st.header("Step 3: Configuration")
    
    # Ensure voices are loaded
    if not st.session_state.available_voices:
        st.session_state.available_voices = get_available_voices()
    
    st.subheader("Podcasters")
    podcasters = set(line['speaker'] for line in st.session_state.script)
    
    # Default voice mappings
    default_voices = {
        "Host 1": {"voice_id": "A9ATTqUUQ6GHu0coCz8t", "name": "Hamid"},
        "Presenter": {"voice_id": "cjVigY5qzO86Huf0OWal", "name": "Eric"},
        "Host 2": {"voice_id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda"}
    }
    
    # Initialize voice settings for each podcaster if not exists
    if 'voice_settings_per_speaker' not in st.session_state.config:
        st.session_state.config['voice_settings_per_speaker'] = {}
    
    for podcaster in podcasters:
        st.write(f"### Settings for {podcaster}")
        # Initialize settings for this podcaster if not exists
        if podcaster not in st.session_state.config['voice_settings_per_speaker']:
            st.session_state.config['voice_settings_per_speaker'][podcaster] = {
                'stability': 0.5,
                'similarity_boost': 0.8,
                'style': 0.1,
            }
        
        # Initialize podcaster voice with default if not set
        if podcaster not in st.session_state.config['podcasters']:
            # Set default voice if available, otherwise use first available voice
            if podcaster in default_voices:
                default_voice_name = default_voices[podcaster]["name"]
                # Find the full voice name from available voices that contains our default name
                matching_voice = next(
                    (voice for voice in st.session_state.available_voices.keys() 
                     if default_voices[podcaster]["name"] in voice),
                    list(st.session_state.available_voices.keys())[0]  # fallback to first voice if not found
                )
                st.session_state.config['podcasters'][podcaster] = matching_voice
            else:
                st.session_state.config['podcasters'][podcaster] = list(st.session_state.available_voices.keys())[0]
        
        # Voice selection
        available_voices = list(st.session_state.available_voices.keys())
        current_voice = st.session_state.config['podcasters'][podcaster]
        
        try:
            voice_index = available_voices.index(current_voice)
        except ValueError:
            voice_index = 0
            st.session_state.config['podcasters'][podcaster] = available_voices[0]
        
        st.session_state.config['podcasters'][podcaster] = st.selectbox(
            f"Voice for {podcaster}:", 
            available_voices,
            index=voice_index,
            key=f"voice_{podcaster}"
        )
        
        # Individual voice settings
        settings = st.session_state.config['voice_settings_per_speaker'][podcaster]
        col1, col2, col3 = st.columns(3)
        with col1:
            settings['stability'] = st.slider(
                f"Stability ({podcaster}):", 
                0.0, 1.0, 
                settings['stability'],
                key=f"stability_{podcaster}"
            )
        with col2:
            settings['similarity_boost'] = st.slider(
                f"Similarity Boost ({podcaster}):", 
                0.0, 1.0, 
                settings['similarity_boost'],
                key=f"similarity_{podcaster}"
            )
        with col3:
            settings['style'] = st.slider(
                f"Style ({podcaster}):", 
                0.0, 1.0, 
                settings['style'],
                key=f"style_{podcaster}"
            )
        
        if st.button(f"Play {podcaster} Voice Sample", key=f"sample_{podcaster}"):
            voice_data = st.session_state.available_voices[st.session_state.config['podcasters'][podcaster]]
            if voice_data['samples']:
                sample = get_voice_sample(voice_data['voice_id'], voice_data['samples'][0]['sample_id'])
                if sample:
                    st.audio(sample, format="audio/mp3")
                else:
                    st.warning("Sample could not be loaded for this voice.")
            else:
                st.warning("No sample available for this voice. Please select another voice or try generating audio.")
        
        st.divider()
    
    st.button("Proceed to Audio Generation", on_click=update_step, args=(5,))

# Step 5: Generate Audio
def step_5():
    st.header("Step 4: Generate Audio")
    # --- Save/Load Progress in SQLite ---
    st.markdown("**Save or Load Your Progress (Optional)**")
    col_save, col_load = st.columns([1, 1])
    with col_save:
        progress_name = st.text_input("Progress Name (Optional)", key="progress_name")
        if st.button("💾 Save Progress to App (Optional)", key="save_progress_sqlite"):
            if progress_name.strip():
                # Serialize audio_segments as base64-encoded MP3 bytes
                audio_segments_serialized = []
                for label, audio in st.session_state.audio_segments:
                    if audio:
                        buf = io.BytesIO()
                        audio.export(buf, format="mp3")
                        b64_audio = base64.b64encode(buf.getvalue()).decode()
                        audio_segments_serialized.append((label, b64_audio))
                    else:
                        audio_segments_serialized.append((label, None))
                database.save_progress(progress_name.strip(), st.session_state.script, st.session_state.config, audio_segments_serialized)
                st.success(f"Progress '{progress_name.strip()}' saved!")
            else:
                st.warning("Please enter a name for your progress.")
    with col_load:
        all_progress = database.get_all_progress()
        if all_progress:
            options = [f"{p['name']} ({p['created_at']})" for p in all_progress]
            selected = st.selectbox("Load Saved Progress", options, key="progress_select", index=None)
            if selected:
                idx = options.index(selected)
                progress_id = all_progress[idx]['id']
                if st.button("Load Selected Progress", key="load_progress_sqlite"):
                    loaded = database.load_progress_by_id(progress_id)
                    if loaded:
                        st.session_state.script = loaded['script']
                        st.session_state.config = loaded['config']
                        # Deserialize audio_segments
                        audio_segments_deserialized = []
                        if loaded.get('audio_segments'):
                            for label, b64_audio in loaded['audio_segments']:
                                if b64_audio:
                                    audio_bytes = base64.b64decode(b64_audio)
                                    audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
                                    audio_segments_deserialized.append((label, audio))
                                else:
                                    audio_segments_deserialized.append((label, None))
                            st.session_state.audio_segments = audio_segments_deserialized
                        else:
                            st.session_state.audio_segments = []
                        st.success("Progress loaded! You can continue editing or generating audio.")
                        st.rerun()
                # Add option to delete the selected progress
                if st.button("Delete Selected Progress", key="delete_progress_sqlite"):
                    database.delete_progress(progress_id)
                    st.success("Progress deleted successfully!")
                    st.rerun()
        else:
            st.info("No saved progress found.")
    # --- End Save/Load Progress ---
    if st.button("Generate All Audio"):
        st.session_state.audio_segments = []
        
        # Generate dialog audio
        for i, line in enumerate(st.session_state.script):
            speaker = line['speaker']
            voice_name = st.session_state.config['podcasters'][speaker]
            audio = generate_audio(
                line['text'],
                st.session_state.available_voices[voice_name]['voice_id'],
                speaker
            )
            st.session_state.audio_segments.append((f"Line {i+1}", audio))
        
        st.success("Audio generated successfully!")
    
    # Load saved generated audio if available
    if st.session_state.get('audio_segments'):
        st.subheader("Generated Audio Segments")
        for i, (label, audio) in enumerate(st.session_state.audio_segments):
            with st.container():
                st.subheader(label)
                st.audio(audio.export(format="mp3").read(), format="audio/mp3")
                
                line_index = int(label.split()[1]) - 1
                speaker = st.session_state.script[line_index]['speaker']
                new_text = st.text_area(f"Edit {label} text:", st.session_state.script[line_index]['text'], key=f"edit_{i}")
                
                if st.button(f"Regenerate {label}", key=f"regen_{i}"):
                    new_audio = generate_audio(
                        new_text,
                        st.session_state.available_voices[st.session_state.config['podcasters'][speaker]]['voice_id'],
                        speaker
                    )
                    st.session_state.script[line_index]['text'] = new_text
                    st.session_state.audio_segments[i] = (label, new_audio)
                    st.rerun()
    
    st.button("Proceed to Finalization", on_click=update_step, args=(6,))

# Step 6: Finalize
def step_6():
    st.header("Step 5: Finalize")
    
    # Add input for company and podcast title
    company = st.text_input("Company:", "")
    podcast_title = st.text_input("Podcast Title:", "")
    
    # Disable Finalize button if audio has not been generated or required fields are empty
    if not st.session_state.audio_segments:
        st.warning("Please generate audio before finalizing the podcast.")
    elif not company.strip() or not podcast_title.strip():
        st.warning("Please enter both Company and Podcast Title before finalizing.")
    else:
        if 'podcast_finalized' not in st.session_state:
            st.session_state.podcast_finalized = False

        if not st.session_state.podcast_finalized:
            if st.button("Finalize Podcast"):
                # Initialize audio segments
                intro_audio = AudioSegment.empty()
                outro_audio = AudioSegment.empty()
                hosts_discussion = AudioSegment.empty()
                
                for i, (label, audio) in enumerate(st.session_state.audio_segments):
                    # Add appropriate pause between segments
                    pause = AudioSegment.silent(duration=300)
                    if i == 0:
                        intro_audio += audio + pause
                    elif i == len(st.session_state.audio_segments) - 1:
                        outro_audio += audio + pause
                    else:
                        hosts_discussion += audio + pause
                
                try:
                    # Convert audio segments to bytes
                    intro_bytes = intro_audio.export(format="mp3").read() if len(intro_audio) > 0 else None
                    hosts_bytes = hosts_discussion.export(format="mp3").read() if len(hosts_discussion) > 0 else None
                    outro_bytes = outro_audio.export(format="mp3").read() if len(outro_audio) > 0 else None
                    
                    # Save to database
                    podcast_id = database.save_podcast(
                        title=f"{company.strip()} {podcast_title.strip()}",
                        intro_audio=intro_bytes,
                        hosts_audio=hosts_bytes,
                        outro_audio=outro_bytes
                    )
                    
                    st.success(f"Podcast '{company.strip()} {podcast_title.strip()}' saved successfully!")
                    st.session_state.podcast_finalized = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving podcast: {str(e)}")
        else:
            if st.button("Proceed to Play and Download"):
                st.session_state.current_step = 7
                st.rerun()

# Step 7: Play and Download
def step_7():
    st.header("Step 6: Play and Download")
    st.markdown("""
    ### 🎧 Listen, Download, and Manage Your Podcasts
    1. **Filter** your podcasts by name/company or creation date.
    2. **Select** a podcast from the list below to view and download its segments.
    3. **Download** or delete segments as needed.
    """)
    
    podcasts = database.get_all_podcasts()
    if not podcasts:
        st.warning("No podcasts have been generated yet.")
        return
    
    # --- Filtering UI ---
    # Filter by company name
    company_names = sorted(list(set(p['title'].split()[0] for p in podcasts)))
    selected_company = st.selectbox("Filter by company:", [""] + company_names)
    filtered_podcasts = [p for p in podcasts if selected_company.lower() in p['title'].lower()]
    def podcast_label(p):
        return f"{p['title']}  |  {p['created_at']}"
    options = [podcast_label(p) for p in filtered_podcasts]
    selected_option = st.selectbox(
        "Select a podcast:",
        options=["" ] + options,
        key="podcast_selectbox",
        format_func=lambda x: x if x else "🔍 Search by company or podcast name..."
    )
    if not selected_option:
        st.info("Please search and select a podcast to view details.")
        return
    selected_idx = options.index(selected_option)
    selected_podcast = podcasts[selected_idx]
    segments = database.get_podcast_segments(selected_podcast['id'])
    
    # --- Podcast Summary Card ---
    st.markdown(f"""
    <div style='background-color:#23272f;padding:1em;border-radius:8px;margin-bottom:1em;'>
    <b>🎙️ Podcast:</b> {selected_podcast['title']}<br>
    <b>🗓️ Created:</b> {selected_podcast['created_at']}<br>
    <b>📝 Last Updated:</b> {selected_podcast['updated_at']}
    </div>
    """, unsafe_allow_html=True)
    
    # --- Audio Segments ---
    col_intro, col_hosts, col_outro = st.columns(3)
    with col_intro:
        st.subheader("Intro")
        if 'intro' in segments:
            st.audio(segments['intro'], format="audio/mp3")
            st.download_button(
                label="⬇️ Download Intro",
                data=segments['intro'],
                file_name=f"{selected_podcast['title']}_intro.mp3",
                mime="audio/mp3",
                key="download_intro"
            )
    with col_hosts:
        st.subheader("Hosts Discussion")
        if 'hosts_discussion' in segments:
            st.audio(segments['hosts_discussion'], format="audio/mp3")
            st.download_button(
                label="⬇️ Download Hosts Discussion",
                data=segments['hosts_discussion'],
                file_name=f"{selected_podcast['title']}_hosts_discussion.mp3",
                mime="audio/mp3",
                key="download_hosts"
            )
    with col_outro:
        st.subheader("Outro")
        if 'outro' in segments:
            st.audio(segments['outro'], format="audio/mp3")
            st.download_button(
                label="⬇️ Download Outro",
                data=segments['outro'],
                file_name=f"{selected_podcast['title']}_outro.mp3",
                mime="audio/mp3",
                key="download_outro"
            )
    st.markdown("---")
    # --- Delete Button ---
    with st.expander("⚠️ Delete this podcast"):
        if st.button("🗑️ Delete Podcast", key="delete_podcast"):
            try:
                database.delete_podcast(selected_podcast['id'])
                st.success("Podcast deleted successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error deleting podcast: {str(e)}")

# Main Streamlit app
def main():
    st.set_page_config(layout="wide", page_title="Podcast Generator")
    st.title("Podcast Generator")
    
    init_session_state()
    
    # Navigation
    st.sidebar.title("Navigation")
    step_buttons = []
    for i, step in enumerate([
        "Input Script", "Edit Script", "Configuration",
        "Generate Audio", "Finalize", "Play and Download"
    ]):
        is_enabled = True
        step_buttons.append(st.sidebar.button(f"Step {i+1}: {step}", disabled=not is_enabled))
    
    if any(step_buttons):
        clicked_step = step_buttons.index(True)
        st.session_state.current_step = clicked_step + 2  # Start from step 2
    
    if st.session_state.current_step == 2:
        step_2()
    elif st.session_state.current_step == 3:
        step_3()
    elif st.session_state.current_step == 4:
        step_4()
    elif st.session_state.current_step == 5:
        step_5()
    elif st.session_state.current_step == 6:
        step_6()
    elif st.session_state.current_step == 7:
        step_7()

if __name__ == "__main__":
    main()
