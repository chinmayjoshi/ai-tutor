import json
from app.agents.subtopics_generator import subtopics_generator_agent
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
import re
import openai
from pydantic import BaseModel
from typing import List, Optional


router = APIRouter()

class TopicRequest(BaseModel):
    topic: str

class SubtopicsResponse(BaseModel):
    subtopics: List[dict]

class YouTubeQuestionRequest(BaseModel):
    url: str

class YouTubeQuestionResponse(BaseModel):
    summary_of_transcript: str
    questions: List[str]

class FeedbackRequest(BaseModel):
    question: str
    answer: str

class FeedbackResponse(BaseModel):
    is_correct: bool
    explanation: str
    improvement_suggestions: Optional[List[str]]


@router.post("/get_subtopics", response_model=SubtopicsResponse)
async def get_subtopics(request: TopicRequest):
    topic = request.topic
    subtopics = subtopics_generator_agent.generate_subtopics(topic)
    subtopics = json.loads(subtopics)
    return SubtopicsResponse(subtopics=subtopics)

def extract_video_id(url: str) -> str:
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

def generate_summary_and_questions(transcript: str) -> dict:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes video transcripts and generates questions based on the content."},
                {"role": "user", "content": f"Based on the following transcript, provide a brief summary of the video content and generate 5 questions to test the viewer's understanding. Format your response as JSON with 'summary' and 'questions' fields. Give a json that I can directly use no trailing or leading characters\n\n{transcript}"}
            ],
            max_tokens=500
        )
        result = response.choices[0].message.content.strip()
        print(result)
        return json.loads(result)  # Parse the JSON string to a Python dictionary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary and questions: {str(e)}")

@router.post("/get_youtube_summary_and_questions", response_model=YouTubeQuestionResponse)
async def get_youtube_summary_and_questions(request: YouTubeQuestionRequest):
    try:
        video_id = extract_video_id(request.url)
        transcript = get_transcript(video_id)
        result = generate_summary_and_questions(transcript)
        return YouTubeQuestionResponse(summary_of_transcript=result['summary'], questions=result['questions'])
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    
@router.post("/get_answer_feedback", response_model=FeedbackResponse)
async def get_answer_feedback(request: FeedbackRequest):
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an educational assistant that provides feedback on answers to questions. Provide your response in JSON format with 'is_correct', 'explanation', and 'improvement_suggestions' fields."},
                {"role": "user", "content": f"Question: {request.question}\nAnswer: {request.answer}\n\nEvaluate if this answer is correct. Provide an explanation and suggestions for improvement if needed. Respond in JSON format."}
            ],
            max_tokens=300
        )
        result = json.loads(response.choices[0].message.content.strip())
        return FeedbackResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate feedback: {str(e)}")