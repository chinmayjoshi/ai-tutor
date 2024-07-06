import json
import autogen
from app.core.config import settings

class MasteryMultiEvaluatorAgent:
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
            system_message="You are a helpful assistant specialized in evaluating the mastery level of a student in various subtopics based on their responses to questions.",
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
            1. Analyze the given questions and student responses for each subtopic.
            2. Evaluate the mastery level of the student for each subtopic based on their responses.
            3. Generate a mastery level for each subtopic from one of these: "beginner", "intermediate", or "advanced".
            4. Provide a brief explanation for each evaluation.
            5. Format your response as a JSON string with the following structure:
               {
                 "subtopic1": {"level": "beginner|intermediate|advanced", "explanation": "brief explanation"},
                 "subtopic2": {"level": "beginner|intermediate|advanced", "explanation": "brief explanation"},
                 ...
               }
            6. End your message with 'TERMINATE'."""
        )

    def evaluate_mastery(self, questions_and_responses, topic, summary):
        """
        Evaluate the mastery level of a student based on their responses to questions.

        :param questions_and_responses: A dictionary where keys are subtopics and values are lists of dictionaries,
                                        each containing a question and the student's response.
        :return: A dictionary of subtopics with their evaluated mastery levels and explanations.
        """
        input_message = json.dumps(questions_and_responses, indent=2)
        self.user_proxy.initiate_chat(
            self.assistant,
            message=f"Evaluate the student's mastery dict for {topic}: {summary} based on these questions and responses:\n{input_message}\n"
        )
        
        final_message = self.user_proxy.chat_messages[self.assistant][-2]["content"]
        final_message = final_message.replace("TERMINATE", "").strip()
        
        try:
            mastery_dict = json.loads(final_message)
            return mastery_dict
        except json.JSONDecodeError:
            print("Error: Could not parse the assistant's response as JSON.")
            return {}

mastery_multi_evaluator_agent = MasteryMultiEvaluatorAgent()