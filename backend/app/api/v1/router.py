from fastapi import APIRouter

from app.api.v1 import admin, auth, budgets, dashboard, expense_reports, master_data, reviews, users

api_router = APIRouter()
for module in (auth, users, master_data, budgets, expense_reports, reviews, dashboard, admin):
    api_router.include_router(module.router)
