"""
Auto-Aff FastAPI Modular Routers
================================
"""

from api.deals_router import router as deals_router
from api.groups_router import router as groups_router
from api.workflow_router import router as workflow_router
from api.outreach_router import router as outreach_router
from api.analytics_router import router as analytics_router
from api.settings_router import router as settings_router
from api.portal_router import router as portal_router

__all__ = [
    "deals_router",
    "groups_router",
    "workflow_router",
    "outreach_router",
    "analytics_router",
    "settings_router",
    "portal_router",
]
