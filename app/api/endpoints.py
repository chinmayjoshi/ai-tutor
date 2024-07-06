import json
from app.agents.subtopics_generator import subtopics_generator_agent
from app.agents.mastery_evaluator import mastery_evaluator_agent
from fastapi import APIRouter, HTTPException
from app.db.fauna_client import fauna_client
from pydantic import BaseModel
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
import re
import openai
from typing import List, Dict
from app.api.fauna_utils import query_topic_data, store_topic_data

router = APIRouter()

class TopicRequest(BaseModel):
    user: str
    topic: str
    subtopics: List[Dict] = None

class SubtopicsResponse(BaseModel):
    subtopics: List[Dict]

class MasteryLevelResponse(BaseModel):
    mastery_level: str

class YouTubeQuestionRequest(BaseModel):
    url: str

class YouTubeQuestionResponse(BaseModel):
    summary_of_transcript: str
    questions: List[str]

@router.post("/get_subtopics", response_model=SubtopicsResponse)
async def get_subtopics(request: TopicRequest):
    user = request.user
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

    store_topic_data(user, topic, subtopics)
    return SubtopicsResponse(subtopics=subtopics)

@router.post("/get_mastery_level", response_model=MasteryLevelResponse)
async def get_mastery_level(request: TopicRequest):
    user = request.user
    topic = request.topic
    selected_subtopics = request.subtopics
    generated_subtopics = query_topic_data(user, topic)
    mastery_level = mastery_evaluator_agent.evaluate_mastery(selected_subtopics, generated_subtopics)
    return MasteryLevelResponse(mastery_level=mastery_level)
