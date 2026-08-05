import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class MeetingReport(Base):
    """SQLAlchemy model representing a saved meeting report's metadata."""
    __tablename__ = 'meeting_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sentiment_score = Column(Float, nullable=False)
    keywords = Column(String, nullable=False)  # Stored as JSON string representation
    file_path = Column(String, nullable=False)

def get_db_path():
    """Resolves and returns the absolute path to the SQLite database file.

    The module lives at src/backend/services/db_manager.py, so we need
    4 dirname() calls to climb back up to the project root directory.
    """
    # __file__ -> services -> backend -> src -> project_root
    root_dir = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
    )
    reports_dir = os.path.join(root_dir, "reports")
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)
    return os.path.join(reports_dir, "rrdocs_archive.db")

def save_report_entry(data):
    """Connects to the SQLite database and logs the document metadata.

    Args:
        data (dict): Dictionary containing sentiment_score, keywords, file_path, and optional timestamp.
    """
    db_path = get_db_path()
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Ensure database table is automatically created if it doesn't exist
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Normalize keywords to JSON string
        kw_data = data.get("keywords", [])
        if isinstance(kw_data, (list, dict)):
            keywords_json = json.dumps(kw_data, ensure_ascii=False)
        else:
            keywords_json = str(kw_data)

        # Parse timestamp if provided, else use current UTC time
        ts_val = data.get("timestamp")
        if not ts_val:
            ts_val = datetime.utcnow()
        elif isinstance(ts_val, str):
            try:
                # Support ISO format string parsing
                ts_val = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            except ValueError:
                ts_val = datetime.utcnow()

        report_entry = MeetingReport(
            timestamp=ts_val,
            sentiment_score=float(data.get("sentiment_score", 0.0)),
            keywords=keywords_json,
            file_path=data.get("file_path", "")
        )
        
        session.add(report_entry)
        session.commit()
        print(f"[DBManager] Logged report metadata to DB at: {db_path}")
    except Exception as e:
        session.rollback()
        print(f"[DBManager] Database logging transaction failed: {e}")
        raise e
    finally:
        session.close()
