"""
Thin aggregator router.

All endpoint logic now lives in the sub-router modules:
  - routes_conversations  : conversation CRUD, queue, seeding, invite waves
  - routes_votes          : vote submission, bulk import, simulate
  - routes_comments       : comment creation, moderation, status updates
  - routes_themes         : theme CRUD and assignment
  - routes_analytics      : metrics, clustering, insights, stats
  - routes_reports        : report creation, sharing, public reports
  - routes_exports        : CSV/ZIP exports and async export jobs

This file keeps the `router` name that main.py imports, and re-exports
`create_conversation` and `seed_comments` for routes_crm.py which does:
    from .routes import create_conversation, seed_comments
"""

from fastapi import APIRouter

from .routes_conversations import router as _conversations_router
from .routes_votes import router as _votes_router
from .routes_comments import router as _comments_router
from .routes_themes import router as _themes_router
from .routes_analytics import router as _analytics_router
from .routes_reports import router as _reports_router
from .routes_exports import router as _exports_router

# Re-export functions imported by routes_crm.py
from .routes_conversations import create_conversation, seed_comments  # noqa: F401

router = APIRouter()

router.include_router(_conversations_router)
router.include_router(_votes_router)
router.include_router(_comments_router)
router.include_router(_themes_router)
router.include_router(_analytics_router)
router.include_router(_reports_router)
router.include_router(_exports_router)
