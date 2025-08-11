# app/scripts/check_pg.py
import os
from sqlalchemy import select, func
from app.db import session_scope, User, WeightLog, ChatMessage, MealAnalysis

def main():
    with session_scope() as db:
        users = db.execute(select(func.count(User.id))).scalar_one()
        logs = db.execute(select(func.count(WeightLog.id))).scalar_one()
        chats = db.execute(select(func.count(ChatMessage.id))).scalar_one()
        meals = db.execute(select(func.count(MealAnalysis.id))).scalar_one()

        admins = db.execute(
            select(User.username).where(User.is_admin == True).order_by(User.username.asc())
        ).scalars().all()

        print("=== PostgreSQL — NutriFlow ===")
        print(f"Users: {users}")
        print(f"Weight logs: {logs}")
        print(f"Chat messages: {chats}")
        print(f"Meal analyses: {meals}")
        print(f"Admins: {admins}")

if __name__ == "__main__":
    main()
