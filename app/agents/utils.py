from app.agents.openai_client import OpenAIClient

def generate_subtopics(topic: str):
    client = OpenAIClient("You are an expert at generating subtopics for a given topic.")
    return client.send_message(f"Generate subtopics for {topic}")
