import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base

USERS_ID_COLUMN = "Users.id"
TASKS_ID_COLUMN = "Tasks.id"

class User(Base):
    __tablename__ = "Users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    lists = relationship("List", back_populates="user")
    tasks = relationship("Task", back_populates="user")
    memos = relationship("Memo", back_populates="user")
    yelpReviews = relationship("YelpReview", back_populates="user")
    credential = relationship("UserCredential", back_populates="user", uselist=False)

class List(Base):
    __tablename__ = "Lists"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    color = Column(String, default="#3B82F6")
    icon = Column(String, default="📋")
    sortOrder = Column(Integer, default=0)
    userId = Column(UUID(as_uuid=True), ForeignKey(USERS_ID_COLUMN), nullable=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", back_populates="lists")
    tasks = relationship("Task", back_populates="list")

class Task(Base):
    __tablename__ = "Tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    estimatedTime = Column(Integer, default=0)
    actualTime = Column(Integer, default=0)
    dueDate = Column(DateTime, nullable=True)
    completed = Column(Boolean, default=False)
    priority = Column(Enum("low", "medium", "high", "urgent", name="task_priority"), default="medium")
    sortOrder = Column(Integer, default=0)
    recurring = Column(JSONB, default={})
    listId = Column(UUID(as_uuid=True), ForeignKey("Lists.id"), nullable=True)
    userId = Column(UUID(as_uuid=True), ForeignKey(USERS_ID_COLUMN), nullable=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", back_populates="tasks")
    list = relationship("List", back_populates="tasks")
    subtasks = relationship("Subtask", back_populates="task")
    notes = relationship("Note", back_populates="task")
    sessions = relationship("Session", back_populates="task")

class Subtask(Base):
    __tablename__ = "Subtasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    completed = Column(Boolean, default=False)
    sortOrder = Column(Integer, default=0)
    taskId = Column(UUID(as_uuid=True), ForeignKey(TASKS_ID_COLUMN), nullable=False)
    userId = Column(UUID(as_uuid=True), ForeignKey(USERS_ID_COLUMN), nullable=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    task = relationship("Task", back_populates="subtasks")

class Note(Base):
    __tablename__ = "Notes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(String, nullable=False)
    links = Column(JSONB, default=[])
    taskId = Column(UUID(as_uuid=True), ForeignKey(TASKS_ID_COLUMN), nullable=True)
    userId = Column(UUID(as_uuid=True), ForeignKey(USERS_ID_COLUMN), nullable=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    task = relationship("Task", back_populates="notes")

class Session(Base):
    __tablename__ = "Sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startTime = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    endTime = Column(DateTime, nullable=True)
    duration = Column(Integer, default=0)
    isActive = Column(Boolean, default=True)
    notes = Column(String, default="")
    taskId = Column(UUID(as_uuid=True), ForeignKey(TASKS_ID_COLUMN), nullable=False)
    userId = Column(UUID(as_uuid=True), ForeignKey(USERS_ID_COLUMN), nullable=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    task = relationship("Task", back_populates="sessions")

class Memo(Base):
    __tablename__ = "Memos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, default="")
    content = Column(String, nullable=False)
    color = Column(Enum("yellow", "pink", "blue", "green", "purple", "orange", name="memo_color"), default="yellow")
    position = Column(JSONB, default={"x": 0, "y": 0})
    tags = Column(JSONB, default=[])
    isPinned = Column(Boolean, default=False)
    isArchived = Column(Boolean, default=False)
    rotation = Column(Float, default=0.0)
    userId = Column(UUID(as_uuid=True), ForeignKey(USERS_ID_COLUMN), nullable=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", back_populates="memos")

class YelpBusiness(Base):
    __tablename__ = "YelpBusinesses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    businessId = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    zipCode = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    website = Column(String, nullable=True)
    category = Column(String, nullable=True)
    rating = Column(Float, default=3.5)
    reviewCount = Column(Integer, default=0)
    imageUrl = Column(String, nullable=True)
    hours = Column(JSONB, default={"monday": "", "tuesday": "", "wednesday": "", "thursday": "", "friday": "", "saturday": "", "sunday": ""})
    isMock = Column(Boolean, default=True)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class YelpReview(Base):
    __tablename__ = "YelpReviews"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    userId = Column(UUID(as_uuid=True), ForeignKey(USERS_ID_COLUMN), nullable=False)
    businessId = Column(String, nullable=False)
    businessName = Column(String, nullable=False)
    businessAddress = Column(String, nullable=True)
    businessPhone = Column(String, nullable=True)
    emotionalTag = Column(Enum("happy", "sad", "mad", "neutral", "excited", "disappointed", "confused", name="emotional_tag"), nullable=False)
    voiceTranscription = Column(String, default="")
    voiceAudioUrl = Column(String, nullable=True)
    feeling = Column(Enum("Angry", "Confused", "Neutral", "Happy", "Satisfied", "Disappointed", name="review_feeling"), default="Neutral")
    standoutAspect = Column(Enum("Service", "Staff", "Price", "Env", name="standout_aspect"), default="Service")
    tone = Column(Enum("Neutral", "Balanced and factual", "Polite", "Gentle and constructive", name="review_tone"), default="Neutral")
    goal = Column(Enum("Praise", "Celebrate great service", "Awareness", "Share for others to know", name="review_goal"), default="Share for others to know")
    overallRating = Column(Integer, default=3)
    serviceRating = Column(Integer, default=3)
    environmentRating = Column(Integer, default=3)
    priceRating = Column(Integer, default=3)
    finalReviewText = Column(String, default="")
    postedOn = Column(Enum("yelp", "draft", name="posted_site"), default="draft")
    postedDate = Column(DateTime, nullable=True)
    chatHistory = Column(JSONB, default=[])
    status = Column(Enum("draft", "review_chat", "enhancing", "preview", "posted", name="review_status"), default="draft")
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", back_populates="yelpReviews")


class UserCredential(Base):
    __tablename__ = "user_credentials"
    credential_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id"), nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", back_populates="credential")
