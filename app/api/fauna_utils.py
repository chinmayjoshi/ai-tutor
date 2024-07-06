from faunadb import query as q
from faunadb.errors import FaunaError
from app.db.fauna_client import fauna_client

def store_topic_data(user_id: str, topic: str, sub_topics: list, selected_subtopics: list=None):
    """
    Store topic data for a user in Fauna.
    
    :param user_id: The ID of the user
    :param topic: The main topic
    :param sub_topics: List of all subtopics
    :param selected_subtopics: List of subtopics selected by the user
    :return: The ID of the created document
    """
    try:
        result = fauna_client.query(
            q.create(
                q.collection("mastery"),
                {
                    "data": {
                        "userId": user_id,
                        "topic": topic,
                        "subTopics": sub_topics,
                        "selectedSubtopics": selected_subtopics if selected_subtopics else []
                    }
                }
            )
        )
        print(f"Document stored successfully with ID: {result['ref'].id()}")
        return result['ref'].id()
    except FaunaError as e:
        print(f"An error occurred while storing the document: {e}")
        return None

def query_topic_data(user_id: str, topic: str):
    try:
        result = fauna_client.query(
            q.map_(
                lambda x: q.get(x),
                q.paginate(
                    q.match(q.index("user_topics_by_user_and_topic"), user_id, topic)
                )
            )
        )
        documents = [{"id": doc["ref"].id(), "data": doc["data"]} for doc in result["data"]]
        print(f"Found {len(documents)} matching documents")
        return documents
    except FaunaError as e:
        print(f"An error occurred while querying the documents: {e}")
        return None
    