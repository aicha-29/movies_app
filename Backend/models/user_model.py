# backend/models/user_model.py
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, validator

class UserBase(BaseModel):
    email: str
    name: str = ""
    age: int = 25
    gender: str = "M"
    occupation: str = "other"
    
    @validator('age')
    def validate_age(cls, v):
        if v < 1 or v > 120:
            raise ValueError('Age must be between 1 and 120')
        return v
    
    @validator('gender')
    def validate_gender(cls, v):
        if v.upper() not in ['M', 'F', 'O']:
            raise ValueError('Gender must be M, F, or O')
        return v.upper()

class UserCreate(UserBase):
    password: str
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        return v

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(UserBase):
    id: str
    created_at: datetime
    cluster_id: Optional[int] = None
    preferences: Dict = {}
    
    class Config:
        from_attributes = True

class MovieBase(BaseModel):
    movie_id: int
    title: str
    year: Optional[int] = None
    genres: List[str] = []
    imdb_url: Optional[str] = None

class MovieResponse(MovieBase):
    average_rating: float = 0.0
    ratings_count: int = 0
    bayesian_rating: float = 0.0
    created_at: datetime
    
    class Config:
        from_attributes = True

class RatingBase(BaseModel):
    user_id: int
    movie_id: int
    rating: float = Field(..., ge=1.0, le=5.0)
    timestamp: datetime = datetime.now()

class RatingResponse(RatingBase):
    id: str
    
    class Config:
        from_attributes = True

class RecommendationRequest(BaseModel):
    user_id: str
    top_n: int = 20
    include_explanations: bool = True

class RecommendationResponse(BaseModel):
    movie_id: int
    title: str
    score: float
    explanation: Optional[str] = None
    score_details: Optional[Dict] = None
    genres: List[str] = []
    year: Optional[int] = None
    
    class Config:
        from_attributes = True

# Modèles pour les requêtes MongoDB
class User:
    def __init__(self, data):
        self.email = data.get('email')
        self.name = data.get('name', '')
        self.age = data.get('age', 25)
        self.gender = data.get('gender', 'M')
        self.occupation = data.get('occupation', 'other')
        self.password = data.get('password')
        self.created_at = data.get('created_at', datetime.now())
        self.preferences = data.get('preferences', {})
        self.cluster_id = data.get('cluster_id')
        self.user_id = data.get('user_id')
        self.similar_users = data.get('similar_users', {})

class Movie:
    def __init__(self, data):
        self.movie_id = data.get('movie_id')
        self.title = data.get('title')
        self.year = data.get('year')
        self.genres = data.get('genres', [])
        self.imdb_url = data.get('imdb_url')
        self.average_rating = data.get('average_rating', 0.0)
        self.ratings_count = data.get('ratings_count', 0)
        self.bayesian_rating = data.get('bayesian_rating', 0.0)
        self.created_at = data.get('created_at', datetime.now())
        self.cluster_popularity = data.get('cluster_popularity', {})
        self.item_similarities = data.get('item_similarities', {})
        self.content_similarities = data.get('content_similarities', {})

class Rating:
    def __init__(self, data):
        self.user_id = data.get('user_id')
        self.movie_id = data.get('movie_id')
        self.rating = data.get('rating', 0.0)
        self.timestamp = data.get('timestamp', datetime.now())