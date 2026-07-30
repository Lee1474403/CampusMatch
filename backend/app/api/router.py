from fastapi import APIRouter

from backend.app.api import auth, chat, matches, notifications, profile, questionnaire, websocket


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(questionnaire.router)
api_router.include_router(matches.router)
api_router.include_router(chat.router)
api_router.include_router(notifications.router)
api_router.include_router(websocket.router)
