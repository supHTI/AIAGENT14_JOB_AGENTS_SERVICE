# Call Processing API Documentation

## Overview
The Call Processing API provides automated transcription and analysis of interview call recordings. It processes audio files through a complete pipeline including preprocessing, speech-to-text transcription, normalization, and intelligent chunking for LLM analysis.

## Features
- ✅ Multi-format audio support (MP3, WAV, M4A)
- ✅ Automatic audio preprocessing (normalization, silence trimming, noise reduction)
- ✅ Google Cloud Speech-to-Text integration with speaker diarization
- ✅ Intelligent transcript normalization and cleaning
- ✅ Token-aware chunking for LLM processing
- ✅ Asynchronous processing with Celery
- ✅ Real-time status tracking via Redis

## Prerequisites

### 1. System Dependencies
Install FFmpeg (required for audio processing):

**Windows:**
```powershell
# Using Chocolatey
choco install ffmpeg

# Or download from: https://ffmpeg.org/download.html
```

**Linux:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 2. Google Cloud Setup
1. Create a Google Cloud Project
2. Enable the Speech-to-Text API
3. Create a service account and download the credentials JSON
4. Set environment variable:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
```

### 3. Python Dependencies
Install the required packages:
```bash
# From the project directory
pip install -e .

# Or install manually:
pip install pydub google-cloud-speech tiktoken
```

## API Endpoints

### 1. Upload & Process Call
**POST** `/api/v1/call/process`

Upload an audio file and start asynchronous processing.

#### Request
**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| audio_file | file | Yes | Audio file (.wav, .mp3, .m4a) |
| candidate_id | int | Yes | Candidate identifier |
| job_id | int | Yes | Job identifier |
| language | string | No | Language code (default: en-IN) |
| diarization | boolean | No | Enable speaker diarization (default: true) |

#### Example Request
```python
import requests

url = "http://localhost:8000/api/v1/call/process"

files = {
    'audio_file': open('interview.mp3', 'rb')
}

data = {
    'candidate_id': 123,
    'job_id': 456,
    'language': 'en-IN',
    'diarization': True
}

response = requests.post(url, files=files, data=data)
print(response.json())
```

#### Response (Immediate)
**Status:** `202 Accepted`

```json
{
  "request_id": "c8b9c1a3",
  "status": "processing"
}
```

Processing continues asynchronously in the background.

---

### 2. Fetch Result
**GET** `/api/v1/call/result/{request_id}`

Retrieve the processing result for a specific request.

#### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| request_id | string | Yes | Request ID from process endpoint |

#### Example Request
```python
import requests

request_id = "c8b9c1a3"
url = f"http://localhost:8000/api/v1/call/result/{request_id}"

response = requests.get(url)
result = response.json()

if result['status'] == 'completed':
    print("Transcript:", result['result']['transcript']['raw_text'])
else:
    print("Status:", result['status'])
```

#### Response - Processing
**Status:** `200 OK`

```json
{
  "request_id": "c8b9c1a3",
  "status": "processing",
  "candidate_id": 123,
  "job_id": 456,
  "created_at": "2024-12-15T10:30:00",
  "stage": "transcription",
  "progress": 60
}
```

#### Response - Completed
**Status:** `200 OK`

```json
{
  "request_id": "c8b9c1a3",
  "status": "completed",
  "candidate_id": 123,
  "job_id": 456,
  "created_at": "2024-12-15T10:30:00",
  "completed_at": "2024-12-15T10:35:30",
  "result": {
    "transcript": {
      "segments": [
        {
          "speaker": "interviewer",
          "timestamp": "00:00:12",
          "text": "Can you tell me about your experience with Python?",
          "start_time": 12.4,
          "end_time": 15.7
        },
        {
          "speaker": "candidate",
          "timestamp": "00:00:16",
          "text": "I have 5 years of experience in Python and Django",
          "start_time": 16.2,
          "end_time": 19.8
        }
      ],
      "statistics": {
        "total_segments": 45,
        "total_duration": 1820.5,
        "total_words": 2340,
        "speaker_breakdown": {
          "candidate": {
            "segments": 23,
            "words": 1200,
            "duration": 900.2
          },
          "interviewer": {
            "segments": 22,
            "words": 1140,
            "duration": 920.3
          }
        }
      },
      "raw_text": "Full transcript..."
    },
    "chunks": [
      {
        "chunk_id": 1,
        "text": "Chunked text for LLM...",
        "tokens": 3500,
        "start_time": 0.0,
        "end_time": 120.5,
        "speakers": ["candidate", "interviewer"],
        "segment_count": 12
      }
    ],
    "chunk_summary": {
      "total_chunks": 5,
      "total_tokens": 15000,
      "avg_tokens_per_chunk": 3000,
      "min_tokens": 2800,
      "max_tokens": 3500
    },
    "audio_info": {
      "filename": "interview.mp3",
      "language": "en-IN",
      "diarization_enabled": true
    }
  }
}
```

#### Response - Failed
**Status:** `200 OK`

```json
{
  "request_id": "c8b9c1a3",
  "status": "failed",
  "candidate_id": 123,
  "job_id": 456,
  "created_at": "2024-12-15T10:30:00",
  "completed_at": "2024-12-15T10:31:00",
  "error": "Audio file is corrupted or unsupported format"
}
```

#### Response - Not Found
**Status:** `404 Not Found`

```json
{
  "detail": "No result found for request_id: c8b9c1a3"
}
```

---

### 3. Delete Result
**DELETE** `/api/v1/call/result/{request_id}`

Delete a processing result from cache.

#### Example Request
```python
import requests

request_id = "c8b9c1a3"
url = f"http://localhost:8000/api/v1/call/result/{request_id}"

response = requests.delete(url)
print(response.json())
```

#### Response
**Status:** `200 OK`

```json
{
  "message": "Successfully deleted result for request_id: c8b9c1a3"
}
```

## Audio Processing Pipeline

### Stage 1: Audio Preprocessing
```
Raw Audio (MP3/WAV/M4A)
  ↓
Format Normalization (16kHz, mono, WAV)
  ↓
Silence Trimming
  ↓
Noise Reduction (optional)
  ↓
Preprocessed Audio
```

**Python Example:**
```python
from pydub import AudioSegment

audio = AudioSegment.from_file("interview.mp3")
audio = audio.set_frame_rate(16000).set_channels(1)
audio = audio.normalize()
audio.export("processed.wav", format="wav")
```

### Stage 2: Speech-to-Text Transcription

**Google STT Configuration:**
```python
config = {
    "model": "latest_long",
    "encoding": "LINEAR16",
    "sample_rate": 16000,
    "language": "en-IN",
    "diarization": True,
    "max_speakers": 2
}
```

**Raw Output:**
```json
{
  "speaker": "Speaker 1",
  "start_time": 12.4,
  "end_time": 15.7,
  "text": "I have five years of experience in Python"
}
```

### Stage 3: Transcript Normalization

**Operations:**
1. Merge overlapping segments
2. Normalize numbers: "five" → "5"
3. Remove fillers: "uh", "umm", "like"
4. Standardize tech terms: "python" → "Python", "react js" → "React"
5. Format timestamps: 84.5 → "01:24"
6. Map speakers: "Speaker 1" → "candidate"

**Normalized Output:**
```json
{
  "speaker": "candidate",
  "timestamp": "00:01:24",
  "text": "I have 5 years of experience in Python and Django"
}
```

### Stage 4: Intelligent Chunking

**Why Chunking?**
- LLM token limits (typically 4000-8000 tokens)
- Context separation for focused analysis
- Domain-specific extraction

**Strategies:**
1. **Token-based**: Chunk by token count with overlap
2. **Speaker-based**: Chunk by speaker turns
3. **Topic-based**: Chunk by keywords/topics
4. **Q&A-based**: Group questions with answers

**Example Chunk:**
```json
{
  "chunk_id": 1,
  "text": "Combined text from multiple segments...",
  "tokens": 3500,
  "start_time": 0.0,
  "end_time": 120.5,
  "speakers": ["candidate", "interviewer"],
  "segment_count": 12
}
```

## Architecture

```
┌─────────────────┐
│   Client App    │
└────────┬────────┘
         │ POST /api/v1/call/process
         ↓
┌─────────────────┐
│  FastAPI Server │
└────────┬────────┘
         │ Queue Task
         ↓
┌─────────────────┐      ┌─────────────────┐
│  Celery Worker  │ ←──→ │   Redis Cache   │
└────────┬────────┘      └─────────────────┘
         │
         ├──→ Audio Preprocessing
         │
         ├──→ Google STT API
         │
         ├──→ Normalization
         │
         └──→ Chunking
              │
              ↓
         Store Result in Redis
              │
              ↓
┌─────────────────┐
│   Client App    │ GET /api/v1/call/result/{id}
└─────────────────┘
```

## Running the Service

### 1. Start Redis
```bash
# Using Docker
docker run -d -p 6379:6379 redis:latest

# Or install locally and run
redis-server
```

### 2. Start Celery Worker
```bash
cd AIAGENT14_JOB_AGENTS_SERVICE
celery -A app.celery.celery_config.celery_app worker --loglevel=info --pool=threads --concurrency=4
```

### 3. Start FastAPI Server
```bash
cd AIAGENT14_JOB_AGENTS_SERVICE
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Test the API
```bash
# Upload audio file
curl -X POST "http://localhost:8000/api/v1/call/process" \
  -F "audio_file=@interview.mp3" \
  -F "candidate_id=123" \
  -F "job_id=456" \
  -F "language=en-IN"

# Check result
curl "http://localhost:8000/api/v1/call/result/c8b9c1a3"
```

## Supported Languages

Common language codes for Google STT:
- `en-US`: English (US)
- `en-IN`: English (India)
- `en-GB`: English (UK)
- `hi-IN`: Hindi (India)
- `es-ES`: Spanish (Spain)
- `fr-FR`: French (France)
- `de-DE`: German (Germany)
- `ja-JP`: Japanese (Japan)
- `zh-CN`: Chinese (Simplified)

[Full list](https://cloud.google.com/speech-to-text/docs/languages)

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 400 Bad Request | Invalid file format | Use MP3, WAV, or M4A |
| 400 Bad Request | Invalid candidate/job ID | Use positive integers |
| 404 Not Found | Request ID doesn't exist | Check the request ID |
| 500 Internal Error | Google credentials missing | Set GOOGLE_APPLICATION_CREDENTIALS |
| 500 Internal Error | FFmpeg not installed | Install FFmpeg |

### Example Error Response
```json
{
  "detail": "Unsupported file format. Supported formats: .wav, .mp3, .m4a"
}
```

## Performance Considerations

### Processing Time
- Audio preprocessing: ~5-10 seconds per minute of audio
- Google STT: ~30-60 seconds per minute of audio
- Normalization: ~1-2 seconds
- Chunking: ~1-2 seconds

**Total**: Approximately 1-2 minutes to process a 30-minute call.

### Token Limits
- Default chunk size: 4000 tokens
- Overlap: 200 tokens
- Average: 1 token ≈ 4 characters

### Storage
- Redis TTL: 7 days for completed results
- Redis TTL: 1 day for failed results

## Advanced Usage

### Custom Chunking Strategy
```python
from app.utils.transcript_chunker import chunk_transcript

# Topic-based chunking
result = chunk_transcript(
    segments=normalized_segments,
    strategy="topic",
    topic_keywords={
        "experience": ["years", "experience", "worked", "projects"],
        "skills": ["python", "java", "programming", "languages"],
        "education": ["degree", "university", "studied"]
    }
)
```

### Custom Normalization
```python
from app.utils.transcript_normalizer import TranscriptNormalizer

normalizer = TranscriptNormalizer()

# Add custom tech terms
normalizer.TECH_TERMS.update({
    'tensorflow': 'TensorFlow',
    'scikit learn': 'scikit-learn'
})

normalized = normalizer.normalize(segments)
```

## Troubleshooting

### Issue: "Google credentials not found"
**Solution:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
# Or set in code
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/path/to/credentials.json"
```

### Issue: "FFmpeg not found"
**Solution:**
```bash
# Check FFmpeg installation
ffmpeg -version

# If not installed, install it (see Prerequisites)
```

### Issue: "Celery worker not processing tasks"
**Solution:**
```bash
# Check Redis connection
redis-cli ping

# Restart Celery worker with logs
celery -A app.celery.celery_config.celery_app worker --loglevel=debug
```

### Issue: "Audio file too large"
**Solution:**
- For files > 10MB, consider splitting the audio
- Or use Google STT's async API with GCS storage

## API Testing with Swagger

Access the interactive API documentation:
- Swagger UI: `http://localhost:8000/model/api/docs`
- ReDoc: `http://localhost:8000/redoc`

## Next Steps

1. **LLM Integration**: Connect the chunks to your LLM service for analysis
2. **Database Storage**: Store transcripts in MySQL for long-term storage
3. **Real-time Updates**: Implement WebSocket for live progress updates
4. **Batch Processing**: Process multiple calls in parallel
5. **Advanced Analysis**: Extract insights like sentiment, skills, confidence level

## Support

For issues or questions:
- Check logs: `tail -f app.log`
- Enable debug logging: Set `logging.level=DEBUG`
- Contact: [Your Support Email]
