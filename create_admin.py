import os
import asyncio
import bcrypt
from dotenv import load_dotenv
from sqlalchemy.future import select

# 1. Force load environment variables
load_dotenv()

# 2. Import database logic and UserModel
import database

async def initialize_admin():
    print("Connecting to database...")
    async with database.AsyncSessionLocal() as db:
        # Check if the user already exists (using email as primary identifier)
        admin_email = "peter.prempeh@pymudcement.com"
        result = await db.execute(select(database.UserModel).where(database.UserModel.email == admin_email))
        existing_user = result.scalars().first()

        if existing_user:
            print(f"Admin user '{admin_email}' already exists in the database!")
            return

        print("Hashing password using native bcrypt...")
        password_bytes = "P3t@r175".encode('utf-8')
        salt = bcrypt.gensalt()
        hashed_password_bytes = bcrypt.hashpw(password_bytes, salt)
        hashed_password_str = hashed_password_bytes.decode('utf-8')

        print("Preparing admin account...")
        new_user = database.UserModel(
            email=admin_email,
            hashed_password=hashed_password_str,
            role="Admin"
        )

        db.add(new_user)
        await db.commit()
        print(f"Success! Admin user '{admin_email}' created successfully.")

if __name__ == "__main__":
    asyncio.run(initialize_admin())