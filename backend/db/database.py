# db/database.py — Database connection and session
# Java equivalent: DataSource + EntityManager / JpaRepository setup

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables on startup (dev only — use Alembic migrations in prod)."""
    # Import all models here so Base.metadata knows about them
    import models.user     # noqa: F401
    import models.session  # noqa: F401
    import models.message  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """
    Dependency injected into routers to get a DB session.
    Java equivalent: @Autowired EntityManager / JPA repository injection.
    """
    async with AsyncSessionLocal() as session:
        yield session
