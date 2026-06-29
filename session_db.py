#!/usr/bin/env python3
"""
Session Database Module for Chrome Session Manager
Fixed: Thread-safe, WAL mode, retry logic, session restart counts
"""

import sqlite3
import json
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import os
import threading

DB_PATH = os.path.expanduser("~/chrome-sessions.db")

class DatabaseError(Exception):
    """Custom database error"""
    pass

class SessionDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _get_connection(self, retries: int = 3, delay: float = 0.1):
        """Get a database connection with retry logic for locked databases"""
        last_error = None
        for attempt in range(retries):
            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                # Enable WAL mode for better concurrency
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.row_factory = sqlite3.Row
                yield conn
                return
            except sqlite3.OperationalError as e:
                if conn:
                    conn.close()
                last_error = e
                if attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                continue
            except Exception as e:
                if conn:
                    conn.close()
                last_error = e
                break
            finally:
                if conn:
                    conn.close()
        
        raise DatabaseError(f"Database connection failed after {retries} attempts: {last_error}")

    def _init_db(self):
        """Initialize database schema"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Sessions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        url TEXT NOT NULL,
                        port INTEGER UNIQUE NOT NULL,
                        profile_dir TEXT NOT NULL,
                        pid INTEGER,
                        status TEXT DEFAULT 'stopped',
                        restart_count INTEGER DEFAULT 0,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP
                    )
                ''')

                # History table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        action TEXT NOT NULL,
                        details TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                ''')

                # Ports table to track which ports are in use
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS used_ports (
                        port INTEGER PRIMARY KEY,
                        session_id INTEGER,
                        acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                ''')

                # Indexes for performance
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_port ON sessions(port)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_session ON session_history(session_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_timestamp ON session_history(timestamp)')

                conn.commit()
        except Exception as e:
            print(f"Warning: Database initialization error: {e}")

    def _execute_with_retry(self, query: str, params: tuple = (), retries: int = 3) -> Any:
        """Execute a query with retry logic"""
        with self._lock:
            with self._get_connection(retries=retries) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor

    def create_session(self, name: str, url: str, port: int, profile_dir: str) -> int:
        """Create a new session with port allocation"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if port is already in use (with lock)
                cursor.execute('SELECT 1 FROM used_ports WHERE port = ?', (port,))
                if cursor.fetchone():
                    raise DatabaseError(f"Port {port} is already in use")
                
                cursor.execute('''
                    INSERT INTO sessions (name, url, port, profile_dir, status)
                    VALUES (?, ?, ?, ?, 'stopped')
                ''', (name, url, port, profile_dir))
                
                session_id = cursor.lastrowid
                
                # Mark port as used
                cursor.execute('''
                    INSERT OR REPLACE INTO used_ports (port, session_id)
                    VALUES (?, ?)
                ''', (port, session_id))
                
                conn.commit()
                
                self._add_history(session_id, 'created', f'Created session: {name}')
                return session_id

    def get_session(self, session_id: int) -> Optional[Dict]:
        """Get a session by ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_session_by_name(self, name: str) -> Optional[Dict]:
        """Get a session by name"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE name = ?', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_session_by_port(self, port: int) -> Optional[Dict]:
        """Get a session by port"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE port = ?', (port,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_sessions(self) -> List[Dict]:
        """List all sessions"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM sessions
                ORDER BY last_used DESC NULLS LAST, created_at DESC
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def start_session(self, session_id: int, pid: int):
        """Mark a session as started"""
        now = datetime.now().isoformat()
        self._execute_with_retry('''
            UPDATE sessions
            SET status = 'running', pid = ?, last_used = ?, updated_at = ?
            WHERE id = ?
        ''', (pid, now, now, session_id))
        
        self._add_history(session_id, 'started', f'Started with PID {pid}')

    def stop_session(self, session_id: int):
        """Mark a session as stopped"""
        now = datetime.now().isoformat()
        self._execute_with_retry('''
            UPDATE sessions
            SET status = 'stopped', pid = NULL, updated_at = ?
            WHERE id = ?
        ''', (now, session_id))
        
        self._add_history(session_id, 'stopped', 'Session stopped')

    def release_port(self, port: int):
        """Release a port from the used_ports table"""
        self._execute_with_retry('DELETE FROM used_ports WHERE port = ?', (port,))

    def get_available_ports(self, start_port: int = 9222, end_port: int = 9299) -> List[int]:
        """Get list of available ports"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT port FROM used_ports')
            used_ports = set(row[0] for row in cursor.fetchall())
            
            all_ports = set(range(start_port, end_port + 1))
            available = sorted(all_ports - used_ports)
            return available

    def get_all_ports(self) -> List[int]:
        """Get all ports currently used by sessions"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT port FROM sessions')
            rows = cursor.fetchall()
            return [row[0] for row in rows]

    def update_session_port(self, session_id: int, new_port: int) -> bool:
        """Update a session's port"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Get the old port first
                cursor.execute('SELECT port FROM sessions WHERE id = ?', (session_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                
                old_port = row[0]
                
                # Check if new port is already in use
                cursor.execute('SELECT 1 FROM used_ports WHERE port = ? AND session_id != ?', 
                             (new_port, session_id))
                if cursor.fetchone():
                    raise DatabaseError(f"Port {new_port} is already in use")
                
                # Update the session with new port
                now = datetime.now().isoformat()
                cursor.execute('''
                    UPDATE sessions
                    SET port = ?, updated_at = ?
                    WHERE id = ?
                ''', (new_port, now, session_id))
                
                # Update used_ports table
                cursor.execute('DELETE FROM used_ports WHERE port = ?', (old_port,))
                cursor.execute('''
                    INSERT OR REPLACE INTO used_ports (port, session_id)
                    VALUES (?, ?)
                ''', (new_port, session_id))
                
                conn.commit()
                
                self._add_history(session_id, 'port_changed', 
                                f'Port changed from {old_port} to {new_port}')
                return True

    def delete_session(self, session_id: int):
        """Delete a session"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Get port before deleting
                cursor.execute('SELECT port FROM sessions WHERE id = ?', (session_id,))
                row = cursor.fetchone()
                if row:
                    cursor.execute('DELETE FROM used_ports WHERE port = ?', (row[0],))
                
                cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
                
                conn.commit()

    def get_session_restart_count(self, session_id: int) -> int:
        """Get the restart count for a session"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT restart_count FROM sessions WHERE id = ?', (session_id,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def increment_session_restart_count(self, session_id: int) -> int:
        """Increment the restart count and return the new value"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute('''
                    UPDATE sessions 
                    SET restart_count = restart_count + 1, updated_at = ?
                    WHERE id = ?
                    RETURNING restart_count
                ''', (now, session_id))
                row = cursor.fetchone()
                conn.commit()
                return row[0] if row else 0

    def reset_session_restart_count(self, session_id: int):
        """Reset the restart count to 0"""
        self._execute_with_retry('''
            UPDATE sessions 
            SET restart_count = 0, updated_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), session_id))

    def _add_history(self, session_id: int, action: str, details: str = None):
        """Add a history entry"""
        self._execute_with_retry('''
            INSERT INTO session_history (session_id, action, details)
            VALUES (?, ?, ?)
        ''', (session_id, action, details))

    def get_history(self, session_id: int, limit: int = 50) -> List[Dict]:
        """Get session history"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM session_history
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (session_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def cleanup_zombie_ports(self):
        """Remove port associations for sessions that don't exist"""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM used_ports
                    WHERE session_id NOT IN (SELECT id FROM sessions)
                ''')
                conn.commit()

    def vacuum(self):
        """Vacuum the database to reclaim space"""
        with self._get_connection() as conn:
            conn.execute("VACUUM")

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Count by status
            cursor.execute('''
                SELECT status, COUNT(*) as count
                FROM sessions
                GROUP BY status
            ''')
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Total sessions
            cursor.execute('SELECT COUNT(*) FROM sessions')
            total = cursor.fetchone()[0]
            
            # Last activity
            cursor.execute('SELECT MAX(last_used) FROM sessions')
            last_activity = cursor.fetchone()[0]
            
            return {
                'total_sessions': total,
                'status_counts': status_counts,
                'last_activity': last_activity,
                'used_ports': len(self.get_all_ports()),
                'available_ports': len(self.get_available_ports())
            }

# ============================================================================
# Database Migrations
# ============================================================================

def migrate_database(db_path: str = DB_PATH):
    """Run any necessary database migrations"""
    print("Running database migrations...")
    
    # First, verify the database schema
    try:
        # Check if the sessions table exists
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if restart_count column exists
            cursor.execute("PRAGMA table_info(sessions)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add restart_count if missing
            if 'restart_count' not in columns:
                try:
                    cursor.execute("ALTER TABLE sessions ADD COLUMN restart_count INTEGER DEFAULT 0")
                    conn.commit()
                    print("Added restart_count column")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e):
                        raise
                    print("restart_count column already exists")
            else:
                print("restart_count column already exists")
            
            # Add indexes if missing
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_port ON sessions(port)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_session ON session_history(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON session_history(timestamp)")
            conn.commit()
            print("Indexes created/verified")
            
            # Clean up zombie ports
            cursor.execute('''
                DELETE FROM used_ports
                WHERE session_id NOT IN (SELECT id FROM sessions)
            ''')
            conn.commit()
            print("Zombie ports cleaned up")
            
        print("Database migration complete")
        
    except Exception as e:
        print(f"Migration error: {e}")
        raise

# ============================================================================
# Main - Run migrations if executed directly
# ============================================================================

if __name__ == "__main__":
    migrate_database()
