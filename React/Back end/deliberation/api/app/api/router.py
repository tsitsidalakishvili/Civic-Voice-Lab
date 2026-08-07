from fastapi import APIRouter

from ..core.auth import router as platform_router
from ..routes import router as deliberation_router
from ..routes_audience_discovery import router as audience_router
from ..routes_chat import router as chat_router
from ..routes_crm import router as crm_router
from ..routes_data_hub import router as data_hub_router
from ..routes_deliberation_extra import router as delib_extra_router
from ..routes_due_diligence import router as due_diligence_router
from ..investigation_ftm import router as investigation_ftm_router
from ..routes_translation import router as translation_router

router = APIRouter()

router.include_router(platform_router)
router.include_router(translation_router)
router.include_router(deliberation_router)
router.include_router(delib_extra_router, prefix="/deliberation", tags=["deliberation"])
router.include_router(crm_router, prefix="/crm", tags=["crm"])
router.include_router(due_diligence_router, prefix="/due-diligence", tags=["due-diligence"])
router.include_router(investigation_ftm_router, prefix="/due-diligence", tags=["due-diligence-investigation"])
router.include_router(
    audience_router, prefix="/audience-discovery", tags=["audience-discovery"]
)
router.include_router(data_hub_router, prefix="/data-hub", tags=["data-hub"])
router.include_router(chat_router, prefix="/data-chat", tags=["data-chat"])
