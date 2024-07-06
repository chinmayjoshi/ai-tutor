import json
import autogen
from app.core.config import settings

class MasteryEvaluatorAgent:
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
            system_message="You are a helpful assistant specialized in evaluating the mastery level of a student in a topic."
        )

        self.user_proxy = autogen.UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
            code_execution_config={"work_dir": "coding"},
            llm_config=self.llm_config,
            system_message="""Execute the following steps:
            1. Evaluate the mastery level of the student in the given topic from the list of subtopics provided and all the subtopics shown to the user
            2. Use your intuition on the subtopics selected and the total subtopics to evaluate the mastery level of the student in the given topic
            3. Generate a mastery level of the user on the given topic from one of these: "beginner" or "intermediate" or "advanced"
            4. Ensure that the mastery level generated belongs to {"beginner", "intermediate", "advanced"}
            5. End your message with 'TERMINATE'."""
        )

    def evaluate_mastery(self, selected_subtopics, total_subtopics) -> list:
        self.user_proxy.initiate_chat(
            self.assistant,
            message=f"Selected subtopics: {selected_subtopics} \n Total subtopics: {total_subtopics}"
        )
        final_message = self.user_proxy.chat_messages[self.assistant][-2]["content"]
        final_message = final_message.replace("TERMINATE", "").strip()
        levels = ["beginner", "intermediate", "advanced"]
        for level in levels:
            if level in final_message:
                return level
        return "beginner"

mastery_evaluator_agent = MasteryEvaluatorAgent()