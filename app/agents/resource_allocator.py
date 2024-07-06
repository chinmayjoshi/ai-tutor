import json
import autogen
from app.core.config import settings

class ResourceAllocatorAgent:
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
            system_message="You are a helpful assistant specialized in allocating resources to a student.",
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
            1. Read all the resources and then find the one that would be the most relevant for the user
            2. Return the url, title and id of the resource in the json format if you find something that is relevant else return 'None'
            3. End your message with 'TERMINATE'."""
        )

    def allocate_resource(self, resources: str, skill_level: str, topic: str, user: str) -> list:
        filtered_resources = []
        for resource in resources:
            if user not in resource["users"]:
                filtered_resources.append(resource)
        self.user_proxy.initiate_chat(
            self.assistant,
            message=f"Find the most relevant resource from the list of resources: {filtered_resources} for skill level: {skill_level} and topic: {topic}"
        )
        final_message = self.user_proxy.chat_messages[self.assistant][-2]["content"]
        final_message = final_message.replace("TERMINATE", "").strip()
        if "None" in final_message:
            return None
        else:
            return json.loads(final_message)

resource_allocator_agent = ResourceAllocatorAgent()