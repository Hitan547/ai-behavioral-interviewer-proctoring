# AI Behavioral Interviewer with Proctoring – Design

## System Architecture

The system consists of four main modules:

1. Interview Interface
2. NLP Analysis Engine
3. Proctoring & Engagement Engine
4. Reporting Module

---

## Interview Interface
- Displays behavioral questions
- Captures candidate responses
- Captures webcam video
- Tracks interview timing

Frontend: Web interface (HTML/JS)
Backend API: FastAPI / Flask

---

## NLP Analysis Engine
Processes candidate responses to extract behavioral indicators.

### Features
- Text preprocessing
- Keyword and phrase detection
- Response length and structure analysis
- Behavioral signal scoring

Output:
- Communication score
- Depth score
- Relevance score

---

## Proctoring & Engagement Engine

### Face Detection
- Detect face presence
- Detect multiple faces

### Attention Estimation
- Head pose estimation
- Gaze direction approximation

### Engagement Metrics
- Facial movement variance
- Stillness duration
- Distraction events

Tools:
- OpenCV
- MediaPipe

Output:
- Attention %
- Presence %
- Proctoring flags

---

## Reporting Module
Combines NLP and vision signals into structured interview report.

Example Output:
- Communication: High
- Depth: Medium
- Attention: 85%
- Distraction events: 1
- Proctoring flags: None

---

## Data Flow

Candidate → Interview UI →  
Text → NLP Engine  
Video → Proctoring Engine  
↓  
Scoring Aggregation  
↓  
Final Interview Report
