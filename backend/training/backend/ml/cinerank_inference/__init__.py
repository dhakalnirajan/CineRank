"""CineRank production inference package."""
from .fast_recommender import FastRecommender, InferenceError  # noqa: F401

__all__ = ["FastRecommender", "InferenceError"]
