import json
from app.agents.subtopics_generator import subtopics_generator_agent
from app.agents.mastery_evaluator import mastery_evaluator_agent
from app.agents.resource_allocator import resource_allocator_agent
from app.agents.mastery_updater import mastery_multi_evaluator_agent
from fastapi import APIRouter, HTTPException
from app.db.fauna_client import fauna_client
from pydantic import BaseModel
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
from faunadb import query as q
from faunadb.errors import FaunaError
import re
import openai
from pydantic import BaseModel
from typing import List, Optional,Dict
from app.api.fauna_utils import query_topic_data, store_topic_data


def fetch_mastery_level(user: str, topic: str):
    """
    Fetch a user's mastery level for a topic.
    
    :param user: User identifier
    :param topic: Topic name
    :return: The mastery levels dictionary if found, None otherwise
    """
    try:
        result = fauna_client.query(
            q.get(q.match(q.index("user_topic_mastery_by_user_and_topic"), user, topic))
        )
        return result["data"]["mastery_levels"]
    except FaunaError as e:
        if "instance not found" in str(e):
            print(f"No mastery level found for user '{user}' and topic '{topic}'")
        else:
            print(f"An error occurred while fetching the mastery level: {e}")
        return {}

def update_mastery_level(user: str, topic: str, updated_mastery_levels: dict):
    """
    Update a user's mastery level for a topic.
    
    :param user: User identifier
    :param topic: Topic name
    :param updated_mastery_levels: Updated dictionary of subtopics and their mastery levels
    :return: True if update was successful, False otherwise
    """
    try:
        fauna_client.query(
            q.update(
                q.select(["ref"], q.get(q.match(q.index("user_topic_mastery_by_user_and_topic"), user, topic))),
                {"data": {"mastery_levels": updated_mastery_levels}}
            )
        )
        print(f"Mastery level for user '{user}' and topic '{topic}' updated successfully.")
        return True
    except FaunaError as e:
        print(f"An error occurred while updating the mastery level: {e}")
        return False


RESOURCES_COLLECTION = "resources"
router = APIRouter()

class TopicRequest(BaseModel):
    user: str
    topic: str
    subtopics: List[Dict] = None

class UpdateMasteryLevelRequest(BaseModel):
    user: str
    topic: str
    summary_of_transcript: str
    resource_id: str
    questions: List[str]
    answers: List[str]

class SubtopicsResponse(BaseModel):
    subtopics: List[Dict]

class MasteryLevelResponse(BaseModel):
    mastery_level: dict

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


class ResourceResponse(BaseModel):
    url: str
    title: str
    id: str

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
                "id": doc["ref"].id(),
                "topic": doc["data"]["topic"],
                "skill_level": doc["data"]["skill_level"],
                "link": doc["data"]["link"],
                "users": doc["data"].get("users", [])
            }
            for doc in results["data"]
        ]
        return resources
    except FaunaError as e:
        return None

def update_resource_user(resource_id, user):
    # Fetch the resource document directly using its ID
    resource = fauna_client.query(
        q.get(q.ref(q.collection("mastery"), resource_id))
    )
    
    # Get the current users or initialize an empty list
    users = resource["data"].get("users", [])
    
    # Append the new user
    users.append(user)
    
    # Update the document
    fauna_client.query(
        q.update(
            q.ref(q.collection("mastery"), resource_id),
            {"data": {"users": users}}
        )
    )


@router.post("/get_subtopics", response_model=SubtopicsResponse)
async def get_subtopics(request: TopicRequest):
    user = request.user
    topic = request.topic
    subtopics = query_topic_data(user, topic)
    if subtopics is None:
        subtopics = subtopics_generator_agent.generate_subtopics(topic)
        store_topic_data(user, topic, subtopics)
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
                {"role": "user", "content": f"Based on the following transcript, provide a brief summary of the video content and generate 5 questions to test the viewer's understanding. Format your response as JSON with 'summary' and 'questions' fields.  Give a json that I can directly use no trailing or leading characters. Do not have any backticks or the word json in the beginning or end. Please.\n\n{transcript}"}
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
    return mastery_level


@router.post("/get_answer_feedback", response_model=FeedbackResponse)
async def get_answer_feedback(request: FeedbackRequest):
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an educational assistant that provides feedback on answers to questions. Provide your response in JSON format with 'is_correct', 'explanation', and 'improvement_suggestions' fields. The 'improvement_suggestions' should always be a list of strings, even if it's empty."},
                {"role": "user", "content": f"Question: {request.question}\nAnswer: {request.answer}\n\nEvaluate if this answer is correct. Provide an explanation and suggestions for improvement if needed. Respond in JSON format."}
            ],
            max_tokens=300
        )
        
        gpt_response = json.loads(response.choices[0].message.content.strip())

        if isinstance(gpt_response.get('improvement_suggestions'), str):
            gpt_response['improvement_suggestions'] = [gpt_response['improvement_suggestions']]
        elif 'improvement_suggestions' not in gpt_response:
            gpt_response['improvement_suggestions'] = []
        
        feedback = FeedbackResponse(
            is_correct=gpt_response['is_correct'],
            explanation=gpt_response['explanation'],
            improvement_suggestions=gpt_response['improvement_suggestions']
        )
        
        return feedback
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse GPT response: {str(e)}")
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Missing required field in GPT response: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate feedback: {str(e)}")


@router.post("/get_resource", response_model=ResourceResponse)
async def get_resource(request: TopicRequest):
    user = request.user
    topic = request.topic
    selected_subtopics = request.subtopics
    mastery_level = await get_mastery_level(user, topic, selected_subtopics)
    resources = fetch_all_resources()
    print(resources)
    resource = resource_allocator_agent.allocate_resource(resources, mastery_level, topic, user)
    return ResourceResponse(url=resource['url'], title=resource['title'], id=resource['id'])

@router.post("/update_mastery_level", response_model=MasteryLevelResponse)
async def update_mastery_level(request: UpdateMasteryLevelRequest):
    user = request.user
    topic = request.topic
    questions = request.questions
    answers = request.answers
    summary = request.summary_of_transcript
    resource_id = request.resource_id
    questions = [{"question": question, "answer": answer} for question, answer in zip(questions, answers)]
    update_resource_user(resource_id, user)
    current_mastery = fetch_mastery_level(user, topic)
    mastery_level = mastery_multi_evaluator_agent.evaluate_mastery(questions, topic, current_mastery, summary, resource_id)
    mastery_level = json.loads(mastery_level)
    current_mastery.update(mastery_level)
    update_mastery_level(user, topic, current_mastery)
    return MasteryLevelResponse(mastery_level=current_mastery)
