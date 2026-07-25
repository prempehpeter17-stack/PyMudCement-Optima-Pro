# create_admin.py
import os
import bcrypt
from dotenv import load_dotenv

# 1. Force load the environment variables
load_dotenv()

# 2. Import database logic (Skip importing from auth to avoid passlib crash)
import database

def initialize_admin():
    print("Connecting to database...")
    db = next(database.get_db())
   
    # Check if the user already exists to prevent duplicates
    existing_user = db.query(database.User).filter(database.User.username == "Peter Kofi Prempeh").first()
    if existing_user:
        print("Admin user 'Peter Kofi Prempeh' already exists in the database!")
        return

    print("Hashing password using native bcrypt...")
    # Safely hash the password manually to match bcrypt specifications
    password_bytes = "P3t@r175".encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password_bytes = bcrypt.hashpw(password_bytes, salt)
   
    # passlib stores hashes as strings, so we decode it to a string format
    hashed_password_str = hashed_password_bytes.decode('utf-8')

    print("Preparing admin account...")
    new_user = database.User(
        username="Peter Kofi Prempeh",
        hashed_password=hashed_password_str,
        role="Admin"
    )
   
    if hasattr(new_user, 'is_active'):
        new_user.is_active = True

    db.add(new_user)
    db.commit()
    print("Success! Admin user 'Peter Kofi Prempeh' created successfully.")

if __name__ == "__main__":
    initialize_admin()