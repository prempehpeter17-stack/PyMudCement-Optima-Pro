import asyncio
from sqlalchemy.future import select
import database
from auth import get_password_hash   # now from security

async def initialize_admin():
    async with database.AsyncSessionLocal() as db:
        admin_email = "peter.prempeh@pymudcement.com"
        result = await db.execute(select(database.UserModel).where(database.UserModel.email == admin_email))
        existing_user = result.scalars().first()
        if existing_user:
            print(f"Admin user already exists.")
            return

        hashed_password = get_password_hash("P3t@r175")
        new_user = database.UserModel(
            username=admin_email,
            email=admin_email,
            hashed_password=hashed_password,
            role="Admin"
        )
        db.add(new_user)
        await db.commit()
        print(f"Admin user '{admin_email}' created successfully.")

if __name__ == "__main__":
    asyncio.run(initialize_admin())