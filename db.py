import os
import sqlite3
from contextlib import contextmanager

import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector import IntegrityError as MySQLIntegrityError


DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "sistema_academico"),
}

SQLITE_PATH = os.getenv("SQLITE_PATH", "sistema_academico.sqlite3")
MYSQL_REQUIRED = os.getenv("MYSQL_REQUIRED", "").lower() in {"1", "true", "yes"}

IntegrityError = (MySQLIntegrityError, sqlite3.IntegrityError)
_engine = None


def _connect_mysql():
    return mysql.connector.connect(**DB_CONFIG)


def _connect_sqlite():
    connection = sqlite3.connect(SQLITE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _ensure_sqlite_schema(connection)
    return connection


def _ensure_engine():
    global _engine

    if _engine:
        return _engine

    try:
        connection = _connect_mysql()
    except MySQLError:
        if MYSQL_REQUIRED:
            raise
        _engine = "sqlite"
        return _engine

    connection.close()
    _engine = "mysql"
    return _engine


def is_sqlite():
    return _ensure_engine() == "sqlite"


def database_label():
    if is_sqlite():
        return f"SQLite local ({SQLITE_PATH})"
    return "MySQL"


def _ensure_sqlite_schema(connection):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS alunos (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nome TEXT NOT NULL,
          cpf TEXT NOT NULL UNIQUE,
          matricula TEXT NOT NULL UNIQUE,
          curso TEXT NOT NULL,
          criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS professores (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nome TEXT NOT NULL,
          cpf TEXT NOT NULL UNIQUE,
          registro TEXT NOT NULL UNIQUE,
          area TEXT NOT NULL,
          criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS disciplinas (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nome TEXT NOT NULL,
          codigo TEXT NOT NULL UNIQUE,
          carga_horaria INTEGER NOT NULL,
          professor_id INTEGER NULL,
          criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (professor_id) REFERENCES professores(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS matriculas (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          aluno_id INTEGER NOT NULL,
          disciplina_id INTEGER NOT NULL,
          ativo INTEGER NOT NULL DEFAULT 1,
          removido_em TEXT NULL,
          criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (aluno_id, disciplina_id),
          FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE CASCADE,
          FOREIGN KEY (disciplina_id) REFERENCES disciplinas(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS usuarios (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          email TEXT NOT NULL UNIQUE,
          senha_hash TEXT NOT NULL,
          tipo TEXT NOT NULL,
          professor_id INTEGER NULL,
          aluno_id INTEGER NULL,
          ativo INTEGER NOT NULL DEFAULT 1,
          criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (professor_id) REFERENCES professores(id) ON DELETE SET NULL,
          FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS notas (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          aluno_id INTEGER NOT NULL,
          disciplina_id INTEGER NOT NULL,
          nota REAL NOT NULL,
          professor_id INTEGER NOT NULL,
          criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
          atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (aluno_id, disciplina_id),
          FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE CASCADE,
          FOREIGN KEY (disciplina_id) REFERENCES disciplinas(id) ON DELETE CASCADE,
          FOREIGN KEY (professor_id) REFERENCES professores(id) ON DELETE CASCADE
        );
        """
    )
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(matriculas)").fetchall()
    }
    if "ativo" not in columns:
        connection.execute(
            "ALTER TABLE matriculas ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1"
        )
    if "removido_em" not in columns:
        connection.execute("ALTER TABLE matriculas ADD COLUMN removido_em TEXT NULL")

    connection.execute(
        """
        INSERT OR IGNORE INTO professores (nome, cpf, registro, area)
        VALUES (?, ?, ?, ?)
        """,
        ("Mariana Souza", "111.222.333-44", "PROF001", "Programacao"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO alunos (nome, cpf, matricula, curso)
        VALUES (?, ?, ?, ?), (?, ?, ?, ?)
        """,
        (
            "Felipe Santos",
            "555.666.777-88",
            "2026001",
            "Sistemas de Informacao",
            "Ana Lima",
            "999.888.777-66",
            "2026002",
            "Ciencia da Computacao",
        ),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO disciplinas (nome, codigo, carga_horaria, professor_id)
        SELECT ?, ?, ?, id FROM professores WHERE registro = ?
        """,
        ("Programacao Orientada a Objetos", "POO101", 80, "PROF001"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO matriculas (aluno_id, disciplina_id)
        SELECT a.id, d.id
          FROM alunos a
          JOIN disciplinas d ON d.codigo = ?
         WHERE a.matricula IN (?, ?)
        """,
        ("POO101", "2026001", "2026002"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO usuarios (username, email, senha_hash, tipo, professor_id, aluno_id)
        SELECT ?, ?, ?, ?, id, NULL FROM professores WHERE registro = ?
        """,
        (
            "professor1",
            "professor1@example.com",
            "scrypt:32768:8:1$HShHuMGCGm8luLRm$2460c9de80d8f2eecd7603ff8ebf31df1c1c39e6f859581248ca1eefa1e53b60133c4334bb434b843bf12c4d0fe2d4db67116239f94e3c6e6de3b8399a395537",
            "professor",
            "PROF001",
        ),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO usuarios (username, email, senha_hash, tipo, professor_id, aluno_id)
        SELECT ?, ?, ?, ?, NULL, id FROM alunos WHERE matricula = ?
        """,
        (
            "aluno1",
            "aluno1@example.com",
            "scrypt:32768:8:1$HShHuMGCGm8luLRm$2460c9de80d8f2eecd7603ff8ebf31df1c1c39e6f859581248ca1eefa1e53b60133c4334bb434b843bf12c4d0fe2d4db67116239f94e3c6e6de3b8399a395537",
            "aluno",
            "2026001",
        ),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO usuarios (username, email, senha_hash, tipo, professor_id, aluno_id)
        VALUES (?, ?, ?, ?, NULL, NULL)
        """,
        (
            "secretaria",
            "secretaria@example.com",
            "scrypt:32768:8:1$HShHuMGCGm8luLRm$2460c9de80d8f2eecd7603ff8ebf31df1c1c39e6f859581248ca1eefa1e53b60133c4334bb434b843bf12c4d0fe2d4db67116239f94e3c6e6de3b8399a395537",
            "secretaria",
        ),
    )
    connection.commit()


@contextmanager
def get_connection():
    engine = _ensure_engine()
    connection = _connect_sqlite() if engine == "sqlite" else _connect_mysql()

    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def _prepare_query(query):
    if is_sqlite():
        return query.replace("%s", "?")
    return query


def fetch_all(query, params=None):
    with get_connection() as connection:
        cursor = (
            connection.cursor()
            if is_sqlite()
            else connection.cursor(dictionary=True)
        )
        cursor.execute(_prepare_query(query), params or ())
        rows = cursor.fetchall()
        cursor.close()
        return [dict(row) for row in rows] if is_sqlite() else rows


def fetch_one(query, params=None):
    with get_connection() as connection:
        cursor = (
            connection.cursor()
            if is_sqlite()
            else connection.cursor(dictionary=True)
        )
        cursor.execute(_prepare_query(query), params or ())
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        return dict(row) if is_sqlite() else row


def execute(query, params=None):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(_prepare_query(query), params or ())
        last_id = cursor.lastrowid
        cursor.close()
        return last_id
