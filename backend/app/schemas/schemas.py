from datetime import datetime
from typing import Annotated, List, Optional
from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, computed_field

from app.core.serial_numbers import format_title_serial
from app.services.title_display import normalize_display_title

SerialNumber = Annotated[str, BeforeValidator(format_title_serial)]


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=12, max_length=256)


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    email_verified_at: Optional[datetime] = Field(None, exclude=True)
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class EmailVerificationIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)


class PasswordForgotIn(BaseModel):
    email: EmailStr


class PasswordResetIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    new_password: str = Field(..., min_length=12, max_length=256)


class EmailActionOut(BaseModel):
    status: str


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: Optional[EmailStr] = None
    current_password: Optional[str] = Field(None, min_length=1, max_length=256)
    password: Optional[str] = Field(None, min_length=12, max_length=256)
    avatar_url: Optional[str] = Field(None, max_length=500000)




class UserPreferencesIn(BaseModel):
    preferred_genres: List[str] = Field(default_factory=list, max_length=20)
    excluded_genres: List[str] = Field(default_factory=list, max_length=20)
    include_adult: bool = False
    min_year: Optional[int] = Field(None, ge=1888, le=2100)
    max_runtime: Optional[int] = Field(None, ge=30, le=600)

    @staticmethod
    def _normalise_genres(values: List[str]) -> List[str]:
        cleaned = []
        seen = set()
        for value in values:
            name = " ".join(value.strip().split())
            key = name.casefold()
            if not name or len(name) > 40 or key in seen:
                continue
            seen.add(key)
            cleaned.append(name)
        return cleaned

    def model_post_init(self, __context) -> None:
        self.preferred_genres = self._normalise_genres(self.preferred_genres)
        self.excluded_genres = self._normalise_genres(self.excluded_genres)
        excluded = {value.casefold() for value in self.excluded_genres}
        self.preferred_genres = [value for value in self.preferred_genres if value.casefold() not in excluded]


class UserPreferencesOut(UserPreferencesIn):
    updated_at: Optional[datetime] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionOut(BaseModel):
    id: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    user_agent: Optional[str] = None
    current: bool = False
    model_config = ConfigDict(from_attributes=True)


class MovieOut(BaseModel):
    title_id: str
    serial_number: SerialNumber
    media_type: str
    movielens_id: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    title: str
    original_title: Optional[str] = None
    genres: str = ""
    year: Optional[int] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    popularity: float = 0.0
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    runtime: Optional[int] = None
    directors_json: Optional[str] = None
    cast_json: Optional[str] = None
    is_adult: bool = False
    source: str = "unknown"
    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def display_title(self) -> str:
        return normalize_display_title(self.title)


class RatingCreate(BaseModel):
    title_id: str = Field(..., min_length=42, max_length=42)
    rating: float = Field(..., ge=0.5, le=5.0)
    relevance: float = Field(1.0, ge=0.0, le=1.0)


class InteractionCreate(BaseModel):
    title_id: str = Field(..., min_length=42, max_length=42)
    event_type: str = Field(..., pattern=r"^(impression|click|play|complete|like|dislike|skip|rating|watched)$")
    value: float = Field(1.0, ge=-1.0, le=10.0)
    metadata: Optional[dict] = None


class RatingOut(BaseModel):
    id: int
    user_id: int
    title_id: str
    rating: float
    relevance: float
    timestamp: datetime
    is_implicit: bool
    model_config = ConfigDict(from_attributes=True)


class RecommendationItem(MovieOut):
    """A model-ranked title hydrated from the canonical catalogue record.

    The model returns provider item identifiers and ranking scores only. The
    recommendation service resolves those identifiers to ``Movie`` rows, then
    serializes the full MovieOut metadata contract plus ranking information.
    Keep this schema extended from MovieOut so new catalogue fields are not
    silently omitted from recommendation payloads.
    """
    score: float
    reason: Optional[str] = None


class RecommendationResponse(BaseModel):
    user_id: int
    model: str
    k: int
    items: List[RecommendationItem]
    generated_at: datetime


class SimilarTitlesResponse(BaseModel):
    title_id: str
    model: str
    items: List[MovieOut]


class SearchResponse(BaseModel):
    query: str
    count: int
    results: List[MovieOut]


class HistoryItem(BaseModel):
    title_id: str
    serial_number: SerialNumber
    media_type: str
    title: str
    genres: str = ""
    rating: float
    timestamp: datetime

    @computed_field
    @property
    def display_title(self) -> str:
        return normalize_display_title(self.title)


class UserHistoryResponse(BaseModel):
    user_id: int
    count: int
    items: List[HistoryItem]


class WatchlistOut(BaseModel):
    title_id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
