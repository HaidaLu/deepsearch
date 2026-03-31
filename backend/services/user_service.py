# services/user_service.py — User business logic
# Java equivalent: @Service UserService

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.auth import AuthError
from models.user import User
from services.auth import create_token, hash_password, verify_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(self, username: str, password: str) -> dict:
        """
        1. Query user by username
        2. Verify password against stored hash
        3. Return JWT token with user_id + username + salting

        Java equivalent:
            User user = userRepository.findByUsername(username)
            if (!passwordEncoder.matches(password, user.getPasswordHash())) throw ...
            return jwtUtil.generateToken(user)
        """
        logger.info(f"Login attempt for user: {username}")
        try:
            result = await self.db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()

            if not user or not verify_password(password, user.hashed_password):
                raise AuthError("Invalid username or password")

            token = create_token(user.id, user.username)
            logger.info(f"Login successful for user: {username}")
            return {"access_token": token, "token_type": "bearer"}

        except SQLAlchemyError as e:
            logger.error(f"Database error during login: {e}")
            raise AuthError("Authentication failed")

    async def register(self, username: str, password: str) -> dict:
        """
        1. Check username is not already taken
        2. Hash the password
        3. Insert new user into DB

        Java equivalent:
            if (userRepository.existsByUsername(username)) throw ...
            user.setPassword(passwordEncoder.encode(password))
            userRepository.save(user)
        """
        logger.info(f"Registering user: {username}")
        try:
            result = await self.db.execute(select(User).where(User.username == username))
            if result.scalar_one_or_none():
                logger.warning(f"Username already exists: {username}")
                raise AuthError("Username already exists")

            logger.info("Hashing password...")
            new_user = User(username=username, hashed_password=hash_password(password))
            self.db.add(new_user)

            logger.info("Committing to database...")
            await self.db.commit()
            logger.info(f"User registered successfully: {username}")
            return {"status": "success"}

        except SQLAlchemyError as e:
            logger.error(f"Database error during registration: {e}")
            await self.db.rollback()
            raise AuthError(f"Registration failed: {str(e)}")
        except AuthError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during registration: {e}")
            await self.db.rollback()
            raise AuthError("Registration failed")
