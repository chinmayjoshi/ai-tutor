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

from faunadb import query as q
from faunadb.errors import FaunaError

def update_or_create_mastery_level(user: str, topic: str, updated_mastery_levels: dict):
    """
    Update a user's mastery level for a topic or create a new entry if it doesn't exist.
    
    :param user: User identifier
    :param topic: Topic name
    :param updated_mastery_levels: Updated dictionary of subtopics and their mastery levels
    :return: True if update/creation was successful, False otherwise
    """
    try:
        result = fauna_client.query(
            q.let(
                {
                    "match": q.match(q.index("user_topic_mastery_by_user_and_topic"), user, topic)
                },
                q.if_(
                    q.exists(q.var("match")),
                    # If the entry exists, update it
                    q.update(
                        q.select(["ref"], q.get(q.var("match"))),
                        {"data": {"mastery_levels": updated_mastery_levels}}
                    ),
                    # If the entry doesn't exist, create a new one
                    q.create(
                        q.collection("user_topic_mastery"),
                        {
                            "data": {
                                "user": user,
                                "topic": topic,
                                "mastery_levels": updated_mastery_levels
                            }
                        }
                    )
                )
            )
        )
        print(f"Mastery level for user '{user}' and topic '{topic}' updated or created successfully.")
        return True
    except FaunaError as e:
        print(f"An error occurred while updating or creating the mastery level: {e}")
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
        q.get(q.ref(q.collection(RESOURCES_COLLECTION), resource_id))
    )
    
    # Get the current users or initialize an empty list
    users = resource["data"].get("users", [])
    
    # Append the new user
    users.append(user)
    
    # Update the document
    fauna_client.query(
        q.update(
            q.ref(q.collection(RESOURCES_COLLECTION), resource_id),
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
                {"role": "user", "content": f"Based on the following transcript, provide a brief summary of the video content and generate 5 questions to test the viewer's understanding. Format your response as JSON with 'summary' and 'questions' fields. Give a JSON that I can directly use with no trailing or leading characters. Do not have any backticks or the word json in the beginning or end.\n\n{transcript}"}
            ],
            max_tokens=500
        )
        result = response.choices[0].message.content.strip()
        
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            # If JSON parsing fails, use the backup formatter
            return backup_json_formatter(result)
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


    
def backup_feedback_formatter(original_response: str) -> dict:
    try:
        prompt = f"""
        The following response should be formatted as JSON with 'is_correct', 'explanation', and 'improvement_suggestions' fields.
        However, it may have formatting issues:

        {original_response}

        Please correct any formatting issues and return a valid JSON object with the expected fields.
        The 'is_correct' field should be a boolean.
        The 'explanation' field should be a string.
        The 'improvement_suggestions' field should always be a list of strings, even if it's empty.
        """

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that corrects JSON formatting for educational feedback."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        
        corrected_json = json.loads(response.choices[0].message.content.strip())
        return corrected_json
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to correct feedback JSON formatting: {str(e)}")



def backup_json_formatter(original_response: str) -> dict:
    try:
        prompt = f"""
        Fix the json formatting:
        {original_response}
        Please correct any formatting issues and return a valid JSON object with 'summary' and 'questions' fields. The 'questions' field should be a list of strings.
        """

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that corrects JSON formatting."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        
        corrected_json = json.loads(response.choices[0].message.content.strip())
        return corrected_json
    except Exception as e:
        return backup_json_formatter(original_response)
        raise HTTPException(status_code=500, detail=f"Failed to correct JSON formatting: {str(e)}")


@router.post("/get_resource", response_model=ResourceResponse)
async def get_resource(request: TopicRequest):
    user = request.user
    topic = request.topic
    selected_subtopics = request.subtopics
    mastery_level = await get_mastery_level(user, topic, selected_subtopics)
    resources = fetch_all_resources()
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
    mastery_level = mastery_multi_evaluator_agent.evaluate_mastery(questions, topic, summary, current_mastery, resource_id)
    current_mastery.update(mastery_level)
    update_or_create_mastery_level(user, topic, current_mastery)
    return MasteryLevelResponse(mastery_level=current_mastery)

class MasteryLevelRequest(BaseModel):
    user: str
    topic: str
    mastery_levels: Dict[str, str]

class MasteryLevelMarkdownResponse(BaseModel):
    markdown: str

def generate_markdown(topic: str, mastery_levels: Dict[str, str]) -> str:
    markdown = f"# Mastery Levels for {topic}\n\n"
    markdown += "| Subtopic | Mastery Level |\n"
    markdown += "|----------|---------------|\n"
    
    for subtopic, level in mastery_levels.items():
        emoji = {
            "BEGINNER": "🐣",
            "INTERMEDIATE": "🦋",
            "ADVANCED": "🚀",
        }.get(level.upper(), "🌱")
        
        markdown += f"| {subtopic} | {emoji} {level.capitalize()} |\n"
    
    return markdown

@router.post("/get_mastery_level_markdown", response_model=MasteryLevelMarkdownResponse)
async def get_mastery_level_markdown(request: MasteryLevelRequest):
    try:
        markdown = generate_markdown(request.topic, request.mastery_levels)
        return MasteryLevelMarkdownResponse(markdown=markdown)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate markdown: {str(e)}")
    
class FakeThoughtsRequest(BaseModel):
    user: str
    topic: str
    summary_of_transcript: str
    resource_id: str
    questions: List[str]
    answers: List[str]

class FakeThoughtsResponse(BaseModel):
    thoughts: str

@router.post("/thought", response_model=FakeThoughtsResponse)
async def thoughts(request: FakeThoughtsRequest):
    try:
        # Prepare the input for GPT
        questions_and_answers = [
            f"Question: {q}\nAnswer: {a}" 
            for q, a in zip(request.questions, request.answers)
        ]
        qa_text = "\n\n".join(questions_and_answers)
        
        prompt = f"""
        As a tutor, analyze the following information and generate thoughts about the student's performance:

        Topic: {request.topic}
        Summary of the learning material: {request.summary_of_transcript}

        Questions and Answers:
        {qa_text}

        Based on this information, provide thoughts on the student's performance, areas that need improvement, and any other relevant insights. Format your response as a JSON string with a single key 'thoughts'
        Structure it like its an ongoing thought chain ending with , based on this let me find the right resource for you. Keep overall thing within 3-4 sentences .
        """

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an insightful tutor providing feedback on a student's performance."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        
        result = json.loads(response.choices[0].message.content.strip())
        return FakeThoughtsResponse(thoughts=result['thoughts'])
    
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse GPT response: {str(e)}")
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Missing required field in GPT response: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate fake thoughts: {str(e)}")

