"""
Thin CRM aggregator router.

Domain routes now live in focused modules:
  - routes_crm_people     : people, dashboard, segments, furry registry
  - routes_crm_tasks      : task CRUD and bulk task creation
  - routes_crm_events     : events and registration flows
  - routes_crm_campaigns  : campaigns, contributions, transparency, admin campaign tools
  - routes_crm_support    : shared platform/admin/support endpoints still specific to CRM
"""

from fastapi import APIRouter

from .routes_crm_campaigns import router as _campaigns_router
from .routes_crm_events import router as _events_router
from .routes_crm_people import router as _people_router
from .routes_crm_support import router as _support_router
from .routes_crm_tasks import router as _tasks_router

router = APIRouter()

router.include_router(_people_router)
router.include_router(_tasks_router)
router.include_router(_events_router)
router.include_router(_campaigns_router)
router.include_router(_support_router)
