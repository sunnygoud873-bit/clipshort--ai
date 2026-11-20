# ClipShort AI Pro starter

## Features
- Professional dark studio UI
- Upload video, YouTube URL, or public Google Drive link
- Generate 1–30 clips
- Select 15, 30, 45, 60 or 90 second clip length
- Automatic speech transcription and burned-in subtitles
- Caption font, size, text colour, outline colour/thickness, position, bold and uppercase settings
- Upload background music; adjust music and source audio volume
- Vertical 1080x1920 MP4 exports packaged as ZIP
- Render health endpoint at /health

## Deploy
1. Upload all project files/folders to the root of your GitHub repository.
2. In Render choose New > Blueprint and connect the repository.
3. Render reads render.yaml and builds the Docker image.
4. Open the service after deployment.

## Important limitations
This is a functional starter, not a finished commercial editor. Clip selection ranks windows by detected speech activity; it does not understand GTA action scenes, visual highlights, virality, or speaker emotion. No manual timeline editor, preview player, per-word animated captions, login, cloud storage, YouTube publishing, or direct Drive OAuth is included.
Render Free resources are generally insufficient for long videos and Whisper/FFmpeg jobs may be slow or time out. Use short source videos for testing. For production, use a paid worker/background queue and persistent object storage.
Only process content you own or are authorized to download/edit. Follow YouTube terms and copyright law.
