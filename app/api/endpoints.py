import json
from app.agents.subtopics_generator import subtopics_generator_agent
from app.agents.mastery_evaluator import mastery_evaluator_agent
from fastapi import APIRouter, HTTPException
from app.db.fauna_client import fauna_client
from pydantic import BaseModel
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

@router.post("/get_subtopics", response_model=SubtopicsResponse)
async def get_subtopics(request: TopicRequest):
    user = request.user
    topic = request.topic
    subtopics = subtopics_generator_agent.generate_subtopics(topic)
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
