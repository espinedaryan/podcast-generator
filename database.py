import sqlite3
import os
from datetime import datetime
import json
import pytz

def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    
    # Create podcasts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create podcast_segments table
    c.execute('''
        CREATE TABLE IF NOT EXISTS podcast_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            podcast_id INTEGER,
            segment_type TEXT NOT NULL,
            audio_data BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (podcast_id) REFERENCES podcasts (id)
        )
    ''')
    
    # Create progress table
    c.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            script TEXT NOT NULL,
            config TEXT NOT NULL,
            audio_segments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_podcast(title, intro_audio=None, hosts_audio=None, outro_audio=None):
    """Save a podcast and its segments to the database."""
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    
    try:
        # Insert podcast
        c.execute('INSERT INTO podcasts (title) VALUES (?)', (title,))
        podcast_id = c.lastrowid
        
        # Save segments if provided
        if intro_audio:
            c.execute('''
                INSERT INTO podcast_segments (podcast_id, segment_type, audio_data)
                VALUES (?, ?, ?)
            ''', (podcast_id, 'intro', intro_audio))
        
        if hosts_audio:
            c.execute('''
                INSERT INTO podcast_segments (podcast_id, segment_type, audio_data)
                VALUES (?, ?, ?)
            ''', (podcast_id, 'hosts_discussion', hosts_audio))
        
        if outro_audio:
            c.execute('''
                INSERT INTO podcast_segments (podcast_id, segment_type, audio_data)
                VALUES (?, ?, ?)
            ''', (podcast_id, 'outro', outro_audio))
        
        conn.commit()
        return podcast_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_all_podcasts():
    """Get all podcasts with their basic information."""
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT id, title, created_at, updated_at
        FROM podcasts
        ORDER BY created_at DESC
    ''')
    
    podcasts = c.fetchall()
    conn.close()
    
    return [{
        'id': p[0],
        'title': p[1],
        'created_at': p[2],
        'updated_at': p[3]
    } for p in podcasts]

def get_podcast_segments(podcast_id):
    """Get all segments for a specific podcast."""
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT segment_type, audio_data
        FROM podcast_segments
        WHERE podcast_id = ?
    ''', (podcast_id,))
    
    segments = c.fetchall()
    conn.close()
    
    return {segment[0]: segment[1] for segment in segments}

def delete_podcast(podcast_id):
    """Delete a podcast and all its segments."""
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    
    try:
        # Delete segments first (due to foreign key constraint)
        c.execute('DELETE FROM podcast_segments WHERE podcast_id = ?', (podcast_id,))
        # Delete podcast
        c.execute('DELETE FROM podcasts WHERE id = ?', (podcast_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_all_progress():
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    c.execute('''
        SELECT id, name, created_at FROM progress ORDER BY created_at DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return [{'id': row[0], 'name': row[1], 'created_at': row[2]} for row in rows]

def save_progress(name, script, config, audio_segments=None):
    tz = pytz.timezone('Asia/Manila')
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO progress (name, script, config, audio_segments, created_at) VALUES (?, ?, ?, ?, ?)
    ''', (name, json.dumps(script), json.dumps(config), json.dumps(audio_segments) if audio_segments else None, now))
    conn.commit()
    conn.close()

def load_progress_by_id(progress_id):
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    c.execute('SELECT script, config, audio_segments FROM progress WHERE id = ?', (progress_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'script': json.loads(row[0]),
            'config': json.loads(row[1]),
            'audio_segments': json.loads(row[2]) if row[2] else None
        }
    return None

def delete_progress(progress_id):
    conn = sqlite3.connect('podcast.db')
    c = conn.cursor()
    c.execute('DELETE FROM progress WHERE id = ?', (progress_id,))
    conn.commit()
    conn.close()

# Initialize database when module is imported
init_db() 