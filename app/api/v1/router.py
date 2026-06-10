"""Version 1 API router — mounts every feature router under ``/api/v1``."""
from __future__ import annotations

from fastapi import APIRouter

from app.features.auth.router import router as auth_router
from app.features.dashboard.router import router as dashboard_router
from app.features.employees.router import router as employees_router
from app.features.invoicing.router import router as invoicing_router
from app.features.work_orders.router import router as work_orders_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(work_orders_router)
api_router.include_router(dashboard_router)
api_router.include_router(invoicing_router)
api_router.include_router(employees_router)

# Future phases register their routers here:
# api_router.include_router(organizations_router)
# api_router.include_router(employees_router)
# api_router.include_router(customers_router)
# api_router.include_router(work_orders_router)
# api_router.include_router(invoices_router)
# api_router.include_router(dashboard_router)
