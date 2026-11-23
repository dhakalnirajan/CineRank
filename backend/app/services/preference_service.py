"""Application service for explicit per-user recommendation preferences."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.entities import UserPreference
from app.schemas.schemas import UserPreferencesIn, UserPreferencesOut


class PreferenceService:
    def get(self, db: Session, user_id: int) -> UserPreferencesOut:
        row = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        if row is None:
            return UserPreferencesOut()
        try:
            preferred = json.loads(row.preferred_genres_json or "[]")
            excluded = json.loads(row.excluded_genres_json or "[]")
        except (TypeError, ValueError):
            preferred, excluded = [], []
        return UserPreferencesOut(
            preferred_genres=preferred,
            excluded_genres=excluded,
            include_adult=bool(row.include_adult),
            min_year=row.min_year,
            max_runtime=row.max_runtime,
            updated_at=row.updated_at,
        )

    def replace(self, db: Session, user_id: int, payload: UserPreferencesIn) -> UserPreferencesOut:
        row = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        if row is None:
            row = UserPreference(user_id=user_id)
            db.add(row)
        row.preferred_genres_json = json.dumps(payload.preferred_genres, ensure_ascii=False)
        row.excluded_genres_json = json.dumps(payload.excluded_genres, ensure_ascii=False)
        row.include_adult = payload.include_adult
        row.min_year = payload.min_year
        row.max_runtime = payload.max_runtime
        db.commit()
        db.refresh(row)
        return UserPreferencesOut(
            preferred_genres=payload.preferred_genres,
            excluded_genres=payload.excluded_genres,
            include_adult=payload.include_adult,
            min_year=payload.min_year,
            max_runtime=payload.max_runtime,
            updated_at=row.updated_at,
        )


preference_service = PreferenceService()
