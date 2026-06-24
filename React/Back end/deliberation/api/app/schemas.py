from typing import List, Optional, Union
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    topic: str = Field(..., min_length=3)
    description: Optional[str] = None
    initial_statements: List[str] = Field(default_factory=list)
    is_open: bool = True
    allow_comment_submission: bool = True
    allow_viz: bool = True
    moderation_required: bool = False
    allow_voting: bool = True
    moderation_profile: str = Field(default="lazy", pattern="^(strict|lazy)$")
    min_votes_for_inclusion: int = Field(default=3, ge=0, le=1000)
    profanity_filter_enabled: bool = False
    rate_limit_per_minute: int = Field(default=0, ge=0, le=120)
    identity_mode: str = Field(default="anonymous", pattern="^(anonymous|xid_optional|xid_required)$")
    invite_only: bool = False


class ConversationUpdate(BaseModel):
    topic: Optional[str] = None
    description: Optional[str] = None
    is_open: Optional[bool] = None
    allow_comment_submission: Optional[bool] = None
    allow_viz: Optional[bool] = None
    moderation_required: Optional[bool] = None
    allow_voting: Optional[bool] = None
    moderation_profile: Optional[str] = Field(default=None, pattern="^(strict|lazy)$")
    min_votes_for_inclusion: Optional[int] = Field(default=None, ge=0, le=1000)
    profanity_filter_enabled: Optional[bool] = None
    rate_limit_per_minute: Optional[int] = Field(default=None, ge=0, le=120)
    identity_mode: Optional[str] = Field(default=None, pattern="^(anonymous|xid_optional|xid_required)$")
    invite_only: Optional[bool] = None


class ConversationOut(BaseModel):
    id: str
    topic: str
    description: Optional[str] = None
    is_open: bool
    allow_comment_submission: bool
    allow_viz: bool
    moderation_required: bool
    allow_voting: bool
    moderation_profile: str
    min_votes_for_inclusion: int
    profanity_filter_enabled: bool
    rate_limit_per_minute: int
    identity_mode: str
    invite_only: bool
    created_at: Optional[str] = None
    comments: Optional[int] = None
    participants: Optional[int] = None


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=2)
    author_id: Optional[str] = None


class CommentOut(BaseModel):
    id: str
    text: str
    status: str
    is_seed: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    author_hash: Optional[str] = None
    agree_count: int = 0
    disagree_count: int = 0
    pass_count: int = 0
    important_count: int = 0


class CommentStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|approved|rejected)$")
    rejection_reason: Optional[str] = None
    copy_to_seed: Optional[bool] = False


class CommentUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=2)
    is_seed: Optional[bool] = None


class StatementDiscussionCommentCreate(BaseModel):
    text: str = Field(..., min_length=1)
    author_id: Optional[str] = None


class StatementDiscussionReactionCreate(BaseModel):
    reaction: str = Field(..., pattern="^(agree|disagree|insightful)$")
    author_id: Optional[str] = None


class StatementDiscussionCommentOut(BaseModel):
    id: str
    statement_id: str
    conversation_id: str
    text: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    author_hash: Optional[str] = None
    like_count: int = 0
    agree_count: int = 0
    disagree_count: int = 0
    insightful_count: int = 0
    sentiment_score: float = 0.0
    sentiment_label: str = "neutral"
    sentiment_confidence: float = 0.0
    sentiment_provider: str = "unavailable"
    consensus_impact: float = 0.0
    my_reaction: Optional[str] = None


class SeedCommentsRequest(BaseModel):
    comments: List[str]


class VoteCreate(BaseModel):
    conversation_id: str
    comment_id: str
    choice: int = Field(..., ge=-1, le=1)
    participant_id: Optional[str] = None
    important: Optional[bool] = False


class SimulateVotesRequest(BaseModel):
    participants: int = Field(default=120, ge=1, le=1000)
    votes_per_participant: int = Field(default=20, ge=1, le=200)
    seed: Optional[int] = None


class VoteImportRow(BaseModel):
    participant_id: str
    comment_id: str
    vote: Union[int, str]
    important: Optional[Union[bool, int, str]] = None


class VotesImportRequest(BaseModel):
    votes: List[VoteImportRow]


class ConversationDatasetImportRow(BaseModel):
    conversation_id: Optional[str] = None
    participant_id: Optional[str] = None
    participant_cluster: Optional[str] = None
    comment_id: str
    comment_text: Optional[str] = None
    is_seed: Optional[Union[bool, int, str]] = None
    comment_created_at: Optional[str] = None
    vote: Optional[Union[int, str]] = None
    important: Optional[Union[bool, int, str]] = None
    reaction_created_at: Optional[str] = None


class ConversationDatasetImportRequest(BaseModel):
    rows: List[ConversationDatasetImportRow]


class QueueRequest(BaseModel):
    seen_ids: List[str] = Field(default_factory=list)
    voted_ids: List[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=200)


class ThemeCreate(BaseModel):
    name: str = Field(..., min_length=2)
    description: Optional[str] = None


class ThemeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2)
    description: Optional[str] = None


class ThemeAssignRequest(BaseModel):
    theme_ids: List[str]


class ReportCreate(BaseModel):
    name: str = Field(..., min_length=2)
    theme_ids: List[str] = Field(default_factory=list)
    include_unassigned: bool = True


class IngestRequest(BaseModel):
    text: str = Field(..., min_length=5)
    strategy: str = Field(default="auto", pattern="^(auto|lines|sentences)$")
    max_items: int = Field(default=200, ge=1, le=1000)


class InviteWaveCreate(BaseModel):
    name: str = Field(..., min_length=2)
    count: int = Field(default=50, ge=1, le=1000)
    parent_code: Optional[str] = None


class CommentMetric(BaseModel):
    id: str
    text: str
    participation: int
    agreement_ratio: float
    consensus_score: float
    polarity_score: float
    agree_count: int
    disagree_count: int
    pass_count: int
    important_count: int = 0
    discussion_sentiment_score: float = 0.0
    negative_comment_weight: float = 0.0
    adjusted_support_score: float = 0.0
    status: str


class MetricsOut(BaseModel):
    total_comments: int
    total_participants: int
    total_votes: int
    consensus: List[CommentMetric]
    polarizing: List[CommentMetric]


class ClusterPoint(BaseModel):
    participant_id: str
    x: float
    y: float
    cluster_id: str


class ClusterSummary(BaseModel):
    cluster_id: str
    size: int
    top_agree: List[str]
    top_disagree: List[str]


class ClusterSimilarity(BaseModel):
    cluster_a: str
    cluster_b: str
    similarity: float


class ReportOut(BaseModel):
    metrics: MetricsOut
    clusters: List[str]
    points: List[ClusterPoint]
    cluster_summaries: List[ClusterSummary]
    cluster_similarity: List[ClusterSimilarity]
    potential_agreements: List[str]
