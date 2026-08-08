# check_user.py
import asyncio
from sqlalchemy import select
from database import AsyncSessionLocal, UserModel

async def check():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.email == "peter.prempeh@pymudcement.com")
        )
        user = result.scalar_one_or_none()
        if user:
            print(f"✅ User found: {user.email}")
            print(f"   Username: {user.username}")
            print(f"   Hashed password: {user.hashed_password[:30]}...")  # first 30 chars
            print(f"   Role: {user.role}")
        else:
            print("❌ No user found with that email.")

if __name__ == "__main__":
    asyncio.run(check())