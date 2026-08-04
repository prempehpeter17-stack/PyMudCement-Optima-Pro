import os
import asyncio
import bcrypt
from dotenv import load_dotenv
from sqlalchemy.future import select

# Load environment variables
load_dotenv()

# Import database logic and UserModel
import database


async def initialize_admin():
    print("Connecting to database...")

    async with database.AsyncSessionLocal() as db:

        admin_email = os.getenv(
            "ADMIN_EMAIL",
            "peter.prempeh@pymudcement.com"
        )

        admin_password = os.getenv(
            "ADMIN_PASSWORD",
            "P3t@r175"
        )

        # Check if admin already exists
        result = await db.execute(
            select(database.UserModel)
            .where(database.UserModel.email == admin_email)
        )

        existing_user = result.scalars().first()

        if existing_user:
            print(f"Admin user '{admin_email}' already exists.")
            return

        print("Hashing password using bcrypt...")

        password_bytes = admin_password.encode("utf-8")

        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(
            password_bytes,
            salt
        ).decode("utf-8")

        print("Creating admin account...")

        new_user = database.UserModel(
            email=admin_email,
            hashed_password=hashed_password,
            role="Admin"
        )

        db.add(new_user)

        await db.commit()

        print(
            f"Success! Admin user '{admin_email}' created successfully."
        )


if __name__ == "__main__":
    asyncio.run(initialize_admin())