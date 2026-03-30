from pydantic import BaseModel, Field


class PlaceRecommendation(BaseModel):
    """A single recommendation returned to the agent."""

    name: str
    city: str
    neighborhood: str | None = None
    cuisine_tags: list[str] = Field(default_factory=list)
    sentiment_summary: str
    positive_pct: float
    total_reviews: int
    last_reviewed: str | None = None


class SearchResult(BaseModel):
    """Response from search_recommendations."""

    recommendations: list[PlaceRecommendation]
    message: str


class FeedbackResult(BaseModel):
    """Response from log_feedback."""

    success: bool
    place_name: str
    total_reviews: int
    message: str


class TrendingResult(BaseModel):
    """Response from get_trending."""

    trending: list[PlaceRecommendation]
    period: str
    message: str
