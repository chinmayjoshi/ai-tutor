from faunadb import query as q
from faunadb.client import FaunaClient
from app.core.config import settings

fauna_client = FaunaClient(secret=settings.FAUNA_SECRET)

def get_fauna_client():
    return fauna_client