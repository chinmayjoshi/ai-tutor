from pydantic import BaseModel, Field
from typing import Optional

class TopicCreate(BaseModel):
    user_id: int
    topic: str

class Topic(TopicCreate):
    id: Optional[str] = Field(None, alias="ref")

    class Config:
        allow_population_by_field_name = True
