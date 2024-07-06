import json
import autogen
from app.core.config import settings

class SubtopicsGeneratorAgent:
    def __init__(self):
        self.config_list = [
            {
                'model': 'gpt-3.5-turbo',
                'api_key': settings.OPENAI_API_KEY,
            }
        ]
        
        self.llm_config = {
            "config_list": self.config_list,
            "temperature": 0.5,
            "seed": 42,
        }

        self.assistant = autogen.AssistantAgent(
            name="assistant",
            llm_config=self.llm_config,
            system_message="You are a helpful assistant specialized in breaking down topics into subtopics.",
            code_execution_config=False
        )

        self.user_proxy = autogen.UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
            code_execution_config={"work_dir": "coding"},
            llm_config=self.llm_config,
            system_message="""Execute the following steps:
            1. Generate a list of upto 10 subtopics for the given main topic with each subtopic having a level attached to it (beginner/intermediate/advanced).
            2. Reflect on the generated subtopics and refine them if necessary.
            3. Provide a final, refined list of subtopics in JSON format like this: [{"subtopic": "subtopic1", "level": "beginner"}, {"subtopic": "subtopic2", "level": "intermediate"}, {"subtopic": "subtopic3", "level": "advanced"}]
            4. End your message with 'TERMINATE'."""
        )

    def generate_subtopics(self, main_topic) -> list:
        self.user_proxy.initiate_chat(
            self.assistant,
            message=f"Generate subtopics for the main topic: {main_topic}"
        )
        final_message = self.user_proxy.chat_messages[self.assistant][-2]["content"]
        final_message = final_message.replace("TERMINATE", "").strip()
        final_message = json.loads(final_message)
        return final_message

subtopics_generator_agent = SubtopicsGeneratorAgent()