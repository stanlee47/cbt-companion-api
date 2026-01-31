"""
Database Module - Turso (libSQL) Connection
Handles all database operations for the CBT Companion app
"""

import os
import libsql_experimental as libsql
from datetime import datetime, date
import uuid
import json


class Database:
    """
    Database handler for Turso (libSQL).
    
    Required environment variables:
    - TURSO_DATABASE_URL: Your Turso database URL
    - TURSO_AUTH_TOKEN: Your Turso auth token
    """
    
    def __init__(self):
        url = os.environ.get("TURSO_DATABASE_URL")
        token = os.environ.get("TURSO_AUTH_TOKEN")
        
        if not url or not token:
            raise ValueError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are required")
        
        self.conn = libsql.connect(database=url, auth_token=token)
        self._init_tables()
        print("✅ Database connected to Turso")
    
    def _init_tables(self):
        """Create tables if they don't exist."""
        
        # Users table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                context TEXT DEFAULT 'person',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Sessions table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                mood_start INTEGER,
                mood_end INTEGER,
                locked_group TEXT,
                stages_reached INTEGER DEFAULT 1,
                completed INTEGER DEFAULT 0,
                messages_in_current_stage INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Messages table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Exercises completed
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises_completed (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT,
                exercise_id TEXT NOT NULL,
                exercise_name TEXT,
                group_type TEXT,
                completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Crisis flags
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS crisis_flags (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                user_email TEXT NOT NULL,
                session_id TEXT NOT NULL,
                message_content TEXT NOT NULL,
                trigger_word TEXT NOT NULL,
                flagged_at TEXT DEFAULT CURRENT_TIMESTAMP,
                reviewed INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        # User stats
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id TEXT PRIMARY KEY,
                total_sessions INTEGER DEFAULT 0,
                total_exercises INTEGER DEFAULT 0,
                current_streak INTEGER DEFAULT 0,
                last_session_date TEXT,
                distortion_counts TEXT DEFAULT '{}',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        self.conn.commit()
    
    # ==================== USER OPERATIONS ====================
    
    def create_user(self, email: str, password_hash: str, name: str, context: str = "person") -> dict:
        """Create a new user."""
        user_id = str(uuid.uuid4())
        
        try:
            self.conn.execute(
                "INSERT INTO users (id, email, password_hash, name, context) VALUES (?, ?, ?, ?, ?)",
                (user_id, email.lower(), password_hash, name, context)
            )
            
            # Initialize user stats
            self.conn.execute(
                "INSERT INTO user_stats (user_id) VALUES (?)",
                (user_id,)
            )
            
            self.conn.commit()
            
            return {"id": user_id, "email": email, "name": name, "context": context}
        
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise ValueError("Email already exists")
            raise e
    
    def get_user_by_email(self, email: str) -> dict:
        """Get user by email."""
        result = self.conn.execute(
            "SELECT id, email, password_hash, name, context FROM users WHERE email = ?",
            (email.lower(),)
        ).fetchone()
        
        if result:
            return {
                "id": result[0],
                "email": result[1],
                "password_hash": result[2],
                "name": result[3],
                "context": result[4]
            }
        return None
    
    def get_user_by_id(self, user_id: str) -> dict:
        """Get user by ID."""
        result = self.conn.execute(
            "SELECT id, email, name, context FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        
        if result:
            return {
                "id": result[0],
                "email": result[1],
                "name": result[2],
                "context": result[3]
            }
        return None
    
    # ==================== SESSION OPERATIONS ====================
    
    def create_session(self, user_id: str) -> str:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        
        self.conn.execute(
            "INSERT INTO sessions (id, user_id) VALUES (?, ?)",
            (session_id, user_id)
        )
        self.conn.commit()
        
        return session_id
    
    def get_session(self, session_id: str) -> dict:
        """Get session by ID."""
        result = self.conn.execute(
            """SELECT id, user_id, started_at, ended_at, mood_start, mood_end, 
                      locked_group, stages_reached, completed, messages_in_current_stage
               FROM sessions WHERE id = ?""",
            (session_id,)
        ).fetchone()
        
        if result:
            return {
                "id": result[0],
                "user_id": result[1],
                "started_at": result[2],
                "ended_at": result[3],
                "mood_start": result[4],
                "mood_end": result[5],
                "locked_group": result[6],
                "current_stage": result[7],
                "completed": bool(result[8]),
                "messages_in_current_stage": result[9] or 0,
                "state": "COMPLETED" if result[8] else ("IN_PROGRESS" if result[6] else "WAITING_FOR_PROBLEM")
            }
        return None
    
    def update_session(self, session_id: str, **kwargs):
        """Update session fields."""
        allowed_fields = {
            "mood_start", "mood_end", "locked_group", "stages_reached", 
            "completed", "ended_at", "messages_in_current_stage"
        }
        
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return
        
        # Map stages_reached to the column
        if "current_stage" in kwargs:
            updates["stages_reached"] = kwargs["current_stage"]
        
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = tuple(list(updates.values()) + [session_id])

        self.conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ?",
            values
        )
        self.conn.commit()
    
    def increment_stage_messages(self, session_id: str) -> int:
        """Increment message counter for current stage."""
        self.conn.execute(
            "UPDATE sessions SET messages_in_current_stage = messages_in_current_stage + 1 WHERE id = ?",
            (session_id,)
        )
        self.conn.commit()
        
        result = self.conn.execute(
            "SELECT messages_in_current_stage FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()
        
        return result[0] if result else 0
    
    def reset_stage_messages(self, session_id: str):
        """Reset message counter (called when advancing stage)."""
        self.conn.execute(
            "UPDATE sessions SET messages_in_current_stage = 0 WHERE id = ?",
            (session_id,)
        )
        self.conn.commit()
    
    def get_user_sessions(self, user_id: str, limit: int = 20) -> list:
        """Get user's past sessions."""
        results = self.conn.execute(
            """SELECT id, started_at, ended_at, mood_start, mood_end, 
                      locked_group, stages_reached, completed
               FROM sessions WHERE user_id = ? 
               ORDER BY started_at DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
        
        return [
            {
                "id": r[0],
                "started_at": r[1],
                "ended_at": r[2],
                "mood_start": r[3],
                "mood_end": r[4],
                "locked_group": r[5],
                "stages_reached": r[6],
                "completed": bool(r[7])
            }
            for r in results
        ]
    
    # ==================== MESSAGE OPERATIONS ====================
    
    def add_message(self, session_id: str, user_id: str, role: str, content: str):
        """Add a message to conversation history."""
        message_id = str(uuid.uuid4())
        
        self.conn.execute(
            "INSERT INTO messages (id, session_id, user_id, role, content) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, user_id, role, content)
        )
        self.conn.commit()
    
    def get_session_messages(self, session_id: str, limit: int = None) -> list:
        """Get messages for a session."""
        query = """SELECT role, content, timestamp FROM messages 
                   WHERE session_id = ? ORDER BY timestamp ASC"""
        
        if limit:
            query += f" LIMIT {limit}"
        
        results = self.conn.execute(query, (session_id,)).fetchall()
        
        return [
            {"role": r[0], "content": r[1], "timestamp": r[2]}
            for r in results
        ]
    
    def get_recent_messages(self, session_id: str, n: int = 6) -> list:
        """Get last n messages for context window."""
        results = self.conn.execute(
            """SELECT role, content FROM messages 
               WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?""",
            (session_id, n)
        ).fetchall()
        
        # Reverse to get chronological order
        return [{"role": r[0], "content": r[1]} for r in reversed(results)]
    
    # ==================== EXERCISE OPERATIONS ====================
    
    def log_exercise_completed(self, user_id: str, session_id: str, exercise_id: str, 
                                exercise_name: str, group_type: str):
        """Log a completed exercise."""
        entry_id = str(uuid.uuid4())
        
        self.conn.execute(
            """INSERT INTO exercises_completed 
               (id, user_id, session_id, exercise_id, exercise_name, group_type) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entry_id, user_id, session_id, exercise_id, exercise_name, group_type)
        )
        
        # Update user stats
        self.conn.execute(
            "UPDATE user_stats SET total_exercises = total_exercises + 1 WHERE user_id = ?",
            (user_id,)
        )
        
        self.conn.commit()
    
    # ==================== CRISIS FLAG OPERATIONS ====================
    
    def flag_crisis(self, user_id: str, user_name: str, user_email: str,
                    session_id: str, message_content: str, trigger_word: str):
        """Flag a crisis message."""
        flag_id = str(uuid.uuid4())
        
        self.conn.execute(
            """INSERT INTO crisis_flags 
               (id, user_id, user_name, user_email, session_id, message_content, trigger_word) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (flag_id, user_id, user_name, user_email, session_id, message_content, trigger_word)
        )
        self.conn.commit()
        
        print(f"🚨 CRISIS FLAGGED: User {user_name} ({user_email}) - Trigger: {trigger_word}")
    
    # ==================== STATS OPERATIONS ====================
    
    def get_user_stats(self, user_id: str) -> dict:
        """Get user statistics."""
        result = self.conn.execute(
            """SELECT total_sessions, total_exercises, current_streak, 
                      last_session_date, distortion_counts
               FROM user_stats WHERE user_id = ?""",
            (user_id,)
        ).fetchone()
        
        if result:
            return {
                "total_sessions": result[0],
                "total_exercises": result[1],
                "current_streak": result[2],
                "last_session_date": result[3],
                "distortion_counts": json.loads(result[4] or "{}")
            }
        
        return {
            "total_sessions": 0,
            "total_exercises": 0,
            "current_streak": 0,
            "last_session_date": None,
            "distortion_counts": {}
        }
    
    def update_user_stats_on_session_end(self, user_id: str, locked_group: str):
        """Update user stats when a session ends."""
        today = date.today().isoformat()
        
        # Get current stats
        stats = self.get_user_stats(user_id)
        
        # Update distortion counts
        distortion_counts = stats["distortion_counts"]
        if locked_group and locked_group != "G0":
            distortion_counts[locked_group] = distortion_counts.get(locked_group, 0) + 1
        
        # Calculate streak
        last_date = stats["last_session_date"]
        if last_date == today:
            new_streak = stats["current_streak"]
        elif last_date == (date.today().replace(day=date.today().day - 1)).isoformat():
            new_streak = stats["current_streak"] + 1
        else:
            new_streak = 1
        
        # Update stats
        self.conn.execute(
            """UPDATE user_stats SET 
               total_sessions = total_sessions + 1,
               current_streak = ?,
               last_session_date = ?,
               distortion_counts = ?
               WHERE user_id = ?""",
            (new_streak, today, json.dumps(distortion_counts), user_id)
        )
        self.conn.commit()


# Singleton instance
_db_instance = None

def get_db() -> Database:
    """Get database singleton instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
