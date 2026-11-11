
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text, URL

# Load environment variables
load_dotenv()

# Read database configuration
database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME")
)

# Create SQLAlchemy engine
engine = create_engine(
    database_url,
    pool_pre_ping=True
)


def test_connection():
    try:
        with engine.connect() as connection:

            result = connection.execute(
                text("""
                    SELECT
                        current_database(),
                        current_user,
                        version()
                """)
            )

            database, user, version = result.fetchone()

            print("Database connection successful!")
            print("Database:", database)
            print("User:", user)
            print("PostgreSQL:", version.split(",")[0])

            table_count = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'insureguard'
                    AND table_type = 'BASE TABLE'
                """)
            ).scalar_one()

            print("InsureGuard tables:", table_count)

    except Exception as error:
        print("Database connection failed:", error)


if __name__ == "__main__":
    test_connection()
