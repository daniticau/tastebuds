from pydantic import BaseModel, Field


class PlaceRecommendation(BaseModel):
    """A single recommendation returned to the agent."""

    name: str
    city: str
    neighborhood: str | None = None
    address: str | None = None
    cuisine_tags: list[str] = Field(default_factory=list)
    sentiment_summary: str
    positive_pct: float
    total_reviews: int
    confidence: str = "low"
    order_this: list[str] = Field(default_factory=list)
    skip_this: list[str] = Field(default_factory=list)
    price_level: int | None = None
    good_for: list[str] = Field(default_factory=list)
    vibes: list[str] = Field(default_factory=list)
    dietary_fit: list[str] = Field(default_factory=list)
    distance_km: float | None = None
    your_history: str | None = None
    why: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    last_reviewed: str | None = None


class SearchResult(BaseModel):
    """Response from search_recommendations."""

    recommendations: list[PlaceRecommendation]
    message: str
    agent_note: str | None = None


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


class CircleInfo(BaseModel):
    name: str | None = None
    invite_code: str
    member_count: int
    active: bool


class FriendInfo(BaseModel):
    """One linked friend. friend_ref is the invite code; the agent maps it to a contact."""

    friend_ref: str
    closeness: int


class LearnedTaste(BaseModel):
    """What the engine learned from the person's own opinions."""

    opinion_count: int = 0
    top_cuisines: list[str] = Field(default_factory=list)
    loved_places: list[str] = Field(default_factory=list)
    avoided_places: list[str] = Field(default_factory=list)


class TasteProfile(BaseModel):
    """Everything the engine remembers about one anonymous person."""

    taste_id: str
    exists: bool = True
    home_city: str | None = None
    neighborhoods: list[str] = Field(default_factory=list)
    dietary: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    liked_cuisines: list[str] = Field(default_factory=list)
    disliked_cuisines: list[str] = Field(default_factory=list)
    vibes: list[str] = Field(default_factory=list)
    budget: int | None = None
    spice_level: int | None = None
    notes: str | None = None
    learned: LearnedTaste = Field(default_factory=LearnedTaste)
    circles: list[CircleInfo] = Field(default_factory=list)
    friends: list[FriendInfo] = Field(default_factory=list)
    friend_signals_active: bool = False


class FollowUp(BaseModel):
    place_name: str
    city: str
    recommended_days_ago: int


class FollowUpsResult(BaseModel):
    follow_ups: list[FollowUp]
    message: str
