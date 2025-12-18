# Call Audio Processing Workflow

This document provides an overview of the call audio processing workflow, including the steps involved, the output generated, and a graphical representation of the process.

---

## Workflow Steps

### 1. **Audio Preprocessing**
- **Input**: MP3 audio file (e.g., "Fresher Mock Interview PYTHON.mp3").
- **Steps**:
  - Load audio file.
  - Convert stereo audio to mono.
  - Resample audio to 16kHz.
  - Trim silence.
  - Apply noise reduction.
  - Export audio to WAV format.
- **Output**: Preprocessed WAV file (e.g., 21.22 MB).

### 2. **Audio Transcription**
- **Input**: Preprocessed WAV file.
- **Steps**:
  - Initialize Gemini STT model (`gemini-2.5-flash`).
  - If the file is large (>15MB), split it into chunks (~10MB each).
  - Transcribe each chunk using the Gemini API.
  - Combine transcriptions into segments.
- **Output**: Transcript segments (e.g., 163 segments).

### 3. **Transcript Normalization**
- **Input**: Transcript segments.
- **Steps**:
  - Merge segments to reduce redundancy.
  - Normalize text (e.g., punctuation, capitalization).
- **Output**: Normalized transcript (e.g., 2 segments).

### 4. **Transcript Chunking**
- **Input**: Normalized transcript.
- **Steps**:
  - Chunk transcript based on token limits.
- **Output**: Transcript chunks (e.g., 1 chunk).

### 5. **Final Output**
- **Result**:
  - Transcript text.
  - Statistics (e.g., total words, duration, speaker breakdown).

---

## Graphical Representation

```mermaid
graph TD
    A[Audio File (MP3)] --> B[Preprocessing]
    B --> C[Preprocessed WAV File]
    C --> D[Transcription]
    D --> E[Transcript Segments]
    E --> F[Normalization]
    F --> G[Normalized Transcript]
    G --> H[Chunking]
    H --> I[Final Output]
```

---

## Example Output

### Transcript Statistics
- **Total Segments**: 2
- **Total Duration**: 697.36 seconds
- **Total Words**: 984
- **Speaker Breakdown**:
  - **Candidate**:
    - Segments: 2
    - Words: 984
    - Duration: 380.18 seconds

### Transcript Text (Excerpt)
```
Yeah. Okay, hi Rakesh. I welcome you for this interview, okay?
Okay sir. Right, so, can you introduce yourself in brief?
Good afternoon, sir. Thank you for giving this opportunity. My myself Bhimaguni Rakesh...
```

---

## Notes
- The workflow is designed to handle large audio files efficiently by chunking and parallel processing.
- The Gemini STT model ensures high accuracy in transcription.
- Normalization and chunking optimize the transcript for downstream processing.
