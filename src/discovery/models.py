from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChannelResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: int
    title: str
    username: Optional[str] = None
    description: Optional[str] = None
    member_count: Optional[int] = None
    last_source: Optional[str] = None


class MessageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: int
    message_id: int
    posted_at: Optional[str] = None
    text: str = ""
    url: Optional[str] = None


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    limit: Optional[int] = Field(default=None, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query must not be empty")
        return cleaned


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    query: str
    channels: List[ChannelResult]


class ExpandSimilarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depth: Optional[int] = Field(default=None, ge=1, le=4)
    per_node: Optional[int] = Field(default=None, ge=1, le=50)
    max_nodes: Optional[int] = Field(default=None, ge=1, le=500)


class SimilarEdgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_chat_id: int
    child_chat_id: int
    depth: int


class ExpandSimilarResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    root_chat_id: int
    depth: int
    channels: List[ChannelResult]
    edges: List[SimilarEdgeResult]
    node_count: int


class WatchlistCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: int
    trust_weight: float = Field(ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    notes: str = ""


class WatchlistPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class WatchlistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: int
    title: Optional[str] = None
    username: Optional[str] = None
    description: Optional[str] = None
    member_count: Optional[int] = None
    trust_weight: float
    tags: List[str]
    notes: str
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    auth_state: str
    read_only_mode: bool
    session_marker_exists: bool
    tdlib_started: bool
    db_path: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
    docs_hint: str
