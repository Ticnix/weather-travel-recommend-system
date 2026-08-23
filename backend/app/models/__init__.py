from app.models.feedback import Feedback
from app.models.knowledge import KnowledgeChunk
from app.models.landmark import Landmark
from app.models.news import News
from app.models.user import User
from app.models.weather import WeatherHistory

__all__ = [
    "User",
    "News",
    "Feedback",
    "WeatherHistory",
    "Landmark",
    "KnowledgeChunk",
]
