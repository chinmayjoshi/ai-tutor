import json
from app.agents.subtopics_generator import subtopics_generator_agent
from app.agents.mastery_evaluator import mastery_evaluator_agent
from app.agents.resource_allocator import resource_allocator_agent
from fastapi import APIRouter, HTTPException
from app.db.fauna_client import fauna_client
from pydantic import BaseModel
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
from faunadb import query as q
from faunadb.errors import FaunaError
import re
import openai
from typing import List, Dict
from app.api.fauna_utils import query_topic_data, store_topic_data


RESOURCES_COLLECTION = "resources"
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

class ResourceResponse(BaseModel):
    url: str
    title: str

def fetch_all_resources():
    try:
        results = fauna_client.query(
            q.map_(
                lambda x: q.get(x),
                q.paginate(q.documents(q.collection(RESOURCES_COLLECTION)), size=100000)
            )
        )
        resources = [
            {
                "topic": doc["data"]["topic"],
                "skill_level": doc["data"]["skill_level"],
                "link": doc["data"]["link"]
            }
            for doc in results["data"]
        ]
        return resources
    except FaunaError as e:
        return None

@router.post("/get_subtopics", response_model=SubtopicsResponse)
async def get_subtopics(request: TopicRequest):
    user = request.user
    topic = request.topic
    subtopics = subtopics_generator_agent.generate_subtopics(topic)
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

async def get_mastery_level(user, topic, selected_subtopics):
    generated_subtopics = query_topic_data(user, topic)
    mastery_level = mastery_evaluator_agent.evaluate_mastery(selected_subtopics, generated_subtopics)
    return MasteryLevelResponse(mastery_level=mastery_level)


@router.post("/get_resource", response_model=ResourceResponse)
async def get_resource(request: TopicRequest):
    user = request.user
    topic = request.topic
    selected_subtopics = request.subtopics
    mastery_level = await get_mastery_level(user, topic, selected_subtopics)
    resources = fetch_all_resources()
    resource = resource_allocator_agent.evaluate_mastery(resources, mastery_level, topic)
    resource = json.loads(resource)
    return ResourceResponse(url=resource['url'], title=resource['title'])
