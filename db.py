# -*- coding: utf-8 -*-
"""
数据层：SQLAlchemy 模型与初始化。
生产环境使用 DATABASE_URL（Postgres，如 Supabase/Neon 免费库）；
未配置时本地回退到 SQLite 文件 app.db，方便联调。
"""
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def make_db_uri():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
        return "sqlite:///" + path
    # Render / 部分平台给的 Postgres 连接串以 postgres:// 开头，SQLAlchemy 需 postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(50), nullable=True)
    role = db.Column(db.String(20), default="employee")  # admin | employee
    # 拓店试岗新增字段
    hire_date = db.Column(db.Date, nullable=True)        # 入职日期（总部代建时录入）
    position = db.Column(db.String(50), nullable=True)   # 岗位（如：拓店）
    exam_opened = db.Column(db.Boolean, default=False)   # 总部是否已为该员工开启考试
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)


class UsageLog(db.Model):
    __tablename__ = "usage_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    question = db.Column(db.Text, nullable=False)
    answer_preview = db.Column(db.Text, nullable=True)
    kb_count = db.Column(db.Integer, default=0)
    web_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.Text, nullable=True)


class ResetRequest(db.Model):
    __tablename__ = "reset_requests"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    status = db.Column(db.String(20), default="pending")  # pending | done
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Feedback(db.Model):
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    usage_log_id = db.Column(db.Integer, db.ForeignKey("usage_log.id"), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    rating = db.Column(db.String(10), nullable=False)  # up | down
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---- 新员工必读：各板块学习进度 ----
class LearningProgress(db.Model):
    __tablename__ = "learning_progress"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    module_id = db.Column(db.String(40), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint("user_id", "module_id", name="uq_user_module"),)


# ---- 考试：一次测验尝试 ----
class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    question_ids = db.Column(db.Text, nullable=False, default="[]")  # JSON 抽中的题 id 列表
    answers = db.Column(db.Text, default="{}")                       # JSON {qid: 选项字母或 ""}
    started_at = db.Column(db.DateTime, nullable=True)
    deadline = db.Column(db.DateTime, nullable=True)
    duration_min = db.Column(db.Integer, default=20)
    status = db.Column(db.String(20), default="in_progress")         # in_progress | submitted
    score = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
