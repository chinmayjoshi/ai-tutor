import openai
from typing import List, Dict
from app.core.config import settings

class OpenAIClient:
    def __init__(self, system_prompt: str):
        openai.api_key = settings.OPENAI_API_KEY
        self.system_prompt = system_prompt
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

    def send_message(self, message: str) -> str:
        self.messages.append({"role": "user", "content": message})
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.messages
        )
        
        assistant_message = response.choices[0].message['content']
        self.messages.append({"role": "assistant", "content": assistant_message})
        
        return assistant_message

    def reset_conversation(self):
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def get_conversation_history(self) -> List[Dict[str, str]]:
        return self.messages[1:]  # Exclude the system message