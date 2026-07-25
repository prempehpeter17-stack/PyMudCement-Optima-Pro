# seed.py
from database import SessionLocal, User
from auth import get_password_hash

def seed_initial_user():
    db = SessionLocal()
    # Check if user already exists
    exists = db.query(User).filter(User.username == "engineer_kofi").first()
    if not exists:
        new_user = User(
            username="engineer_kofi",
            hashed_password=get_password_hash("YourSecurePassword2026!"),
            role="Engineer",
            is_active=True
        )
        db.add(new_user)
        db.commit()
        print("Success: Initial engineer account provisioned.")
    else:
        print("User already exists.")
    db.close()

if __name__ == "__main__":
    seed_initial_user()