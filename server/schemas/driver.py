from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

# Fuel Log Schemas
class FuelLogCreate(BaseModel):
    odometer: int
    liters: float
    cost: float

class FuelLogResponse(BaseModel):
    id: int
    driver_id: int
    odometer: int
    liters: float
    cost: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FuelLogsSummaryResponse(BaseModel):
    logs: List[FuelLogResponse]
    current_fuel_level: Optional[int] = None
    avg_consumption: Optional[float] = None
    total_spent: float

# Performance Schemas
class WeeklyTrendBar(BaseModel):
    day: str
    h: str
    active: bool
    value: Optional[str] = None

class Achievement(BaseModel):
    title: str
    subtitle: str
    unlocked: bool
    icon: str

class LeaderboardEntry(BaseModel):
    rank: int
    initials: str
    name: str
    points: int
    is_you: bool

class PerformanceOverviewResponse(BaseModel):
    collection_efficiency: Optional[str] = None
    collection_efficiency_pct: Optional[str] = None
    eco_coins_balance: int
    eco_coins_earned: Optional[str] = None
    fuel_economy: Optional[str] = None
    fuel_economy_pct: Optional[str] = None
    safety_score: Optional[str] = None
    safety_score_pct: Optional[str] = None
    weekly_trends: List[WeeklyTrendBar]
    achievements: List[Achievement]
    leaderboard: List[LeaderboardEntry]

# Message/Chat Schemas
class MessageCreate(BaseModel):
    body: str

class MessageResponse(BaseModel):
    id: int
    sender_name: str
    sender_role: str
    recipient_id: Optional[int] = None
    body: str
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationThread(BaseModel):
    name: str
    lastMessage: str
    time: str
    active: bool
    role: str

class MessagesOverviewResponse(BaseModel):
    conversations: List[ConversationThread]
    messages: List[MessageResponse]
