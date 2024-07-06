import json
from app.agents.subtopics_generator import subtopics_generator_agent
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
import re
import openai

router = APIRouter()

class TopicRequest(BaseModel):
    topic: str

class SubtopicsResponse(BaseModel):
    subtopics: List[dict]

class YouTubeQuestionRequest(BaseModel):
    url: str

class YouTubeQuestionResponse(BaseModel):
    questions: List[str]

@router.post("/get_subtopics", response_model=SubtopicsResponse)
async def get_subtopics(request: TopicRequest):
    topic = request.topic
    subtopics = subtopics_generator_agent.generate_subtopics(topic)
    subtopics = json.loads(subtopics)
    # print(f"Generated subtopics: {type(subtopics)}")
    return SubtopicsResponse(subtopics=subtopics)

def extract_video_id(url: str) -> str:
    # Extract video ID from various YouTube URL formats
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:embed\/|v\/|youtu.be\/)([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Invalid YouTube URL")

def get_transcript(video_id: str) -> str:
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry['text'] for entry in transcript])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch transcript: {str(e)}")

def generate_questions(transcript: str) -> List[str]:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates questions based on video transcripts."},
                {"role": "user", "content": f"Based on the following transcript, generate 5 questions to test the viewer's understanding of the video content:\n\n{transcript}"}
            ],
            max_tokens=300
        )
        questions = response.choices[0].message.content.strip().split('\n')

        return [q.strip() for q in questions if q.strip()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")

@router.post("/get_youtube_questions", response_model=YouTubeQuestionResponse)
async def get_youtube_questions(request: YouTubeQuestionRequest):
    try:
        video_id = extract_video_id(request.url)
        transcript = get_transcript(video_id)
        questions = generate_questions(transcript)
        return YouTubeQuestionResponse(questions=questions)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))