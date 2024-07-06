import json
from app.agents.subtopics_generator import subtopics_generator_agent
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

router = APIRouter()

class TopicRequest(BaseModel):
    topic: str

class SubtopicsResponse(BaseModel):
    subtopics: List[dict]

@router.post("/get_subtopics", response_model=SubtopicsResponse)
async def get_subtopics(request: TopicRequest):
    topic = request.topic
    subtopics = subtopics_generator_agent.generate_subtopics(topic)
    subtopics = json.loads(subtopics)
    # print(f"Generated subtopics: {type(subtopics)}")
    return SubtopicsResponse(subtopics=subtopics)
