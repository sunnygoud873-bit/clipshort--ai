# ClipShort AI

A Streamlit app that transcribes a video locally with faster-whisper, selects highlight windows using transcript scoring, optionally asks an OpenAI model to rank candidate moments, then renders vertical 9:16 MP4 clips with burned-in subtitles.

## Requirements
- Python 3.10+
- FFmpeg installed and available on PATH (recommended)
- Enough disk space for the source, extracted WAV, model files, and rendered clips
- For optional API selection: an OpenAI API key

## Install (Windows)
1. Install Python 3.10 or newer.
2. Install FFmpeg and add its `bin` folder to PATH.
3. Extract this project ZIP.
4. Open Command Prompt in the project folder.
5. Run:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

The first transcription run downloads the selected Whisper model. Choose `base` for lower resource use, `small` for a good balance, or `medium` for better accuracy at higher cost.

## Optional OpenAI highlight selection
Set an environment variable before starting Streamlit:

```bat
set OPENAI_API_KEY=your_api_key_here
set OPENAI_MODEL=gpt-5.5
streamlit run app.py
```

Or enter the key in the app sidebar. The API is optional; without it the app uses local transcript-based ranking. API use may incur charges. Keep API keys private and do not commit them to source control.

The app uses the OpenAI Responses API for text-based candidate ranking. See:
https://developers.openai.com/api/reference/python/resources/responses/methods/create

## 4 GB uploads
`.streamlit/config.toml` sets Streamlit's `maxUploadSize` and `maxMessageSize` to 4096 MB. A reverse proxy, hosting platform, container, and available disk space may impose lower limits. A 4 GB upload can consume substantial memory and storage; use a machine/server with sufficient resources. Streamlit's standard uploader buffers uploads before the app writes them to disk, so this is not an ideal architecture for multi-gigabyte public production uploads.

## YouTube
The app uses yt-dlp. YouTube may block automated access, require sign-in, or restrict certain videos. Browser-cookie import works only if the selected browser profile is available on the machine running the app. This is not a bypass for access controls. Use only videos you own or have permission to download and process.

## Limitations
- Current vertical framing is center-crop, not face tracking. A true face/speaker tracking pipeline needs an additional vision model.
- Local highlight scoring is heuristic, not a real virality prediction.
- The OpenAI model ranks transcript candidates; it does not watch the video pixels.
- Long videos require significant CPU/GPU time and disk space.
