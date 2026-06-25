from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import sqlite3
from datetime import date, datetime

app = FastAPI(title="Mini Task Tracker")

# --- DATABASE SETUP ---
DB_FILE = "tasks.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT NOT NULL,
                deadline TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
init_db()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# --- PYDANTIC MODELS ---
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: str = Field(..., pattern="^(Low|Medium|High)$")
    deadline: date

    @field_validator('title')
    def title_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("Название задачи не может состоять только из пробелов")
        return v.strip()

class TaskUpdateStatus(BaseModel):
    status: str = Field(..., pattern="^(active|done)$")

class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    priority: str
    deadline: date
    status: str          # 'active' или 'done' из БД
    dynamic_status: str  # 'active', 'done' или 'overdue' (вычисляется на лету)

# --- SORTING LOGIC ---
def enrich_and_sort_tasks(tasks: List[dict]) -> List[dict]:
    today = date.today()
    enriched = []
    
    for t in tasks:
        task = dict(t)
        task_date = date.fromisoformat(task['deadline'])
        
        # 1. Высчитываем динамический статус
        if task['status'] == 'active' and task_date < today:
            task['dynamic_status'] = 'overdue'
        else:
            task['dynamic_status'] = task['status']
            
        enriched.append(task)
        
    def sort_key(t):
        # Вес группы (просроченные -> активные -> выполненные)
        status_weight = {"overdue": 1, "active": 2, "done": 3}[t['dynamic_status']]
        
        # Буст: Высокий приоритет + дедлайн сегодня (0 - наверх, 1 - обычные)
        task_date = date.fromisoformat(t['deadline'])
        is_today_boost = 0 if task_date == today and t['priority'] == 'High' else 1
        
        # Вес приоритета внутри группы
        priority_weight = {"High": 1, "Medium": 2, "Low": 3}[t['priority']]
        
        return (status_weight, is_today_boost, priority_weight, task_date)

    return sorted(enriched, key=sort_key)

# --- API ENDPOINTS ---

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

@app.get("/api/tasks", response_model=List[TaskResponse])
def get_tasks():
    with get_db() as conn:
        tasks = conn.execute("SELECT * FROM tasks").fetchall()
        return enrich_and_sort_tasks(tasks)

@app.post("/api/tasks")
def create_task(task: TaskCreate):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (title, description, priority, deadline, status) VALUES (?, ?, ?, ?, 'active')",
            (task.title, task.description, task.priority, task.deadline.isoformat())
        )
        return {"id": cursor.lastrowid}

@app.put("/api/tasks/{task_id}/status")
def update_task_status(task_id: int, data: TaskUpdateStatus):
    with get_db() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (data.status, task_id))
        return {"success": True}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return {"success": True}

# Бонус: обновление задачи целиком
@app.put("/api/tasks/{task_id}")
def update_task_full(task_id: int, task: TaskCreate):
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET title=?, description=?, priority=?, deadline=? WHERE id=?",
            (task.title, task.description, task.priority, task.deadline.isoformat(), task_id)
        )
        return {"success": True}