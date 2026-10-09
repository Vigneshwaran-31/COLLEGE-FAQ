"""
Audit logging service for DUM DUM Group of Institution.
Provides immutable, append-only security logs, filtering, and safe CSV export with formula injection defense.
"""
import io
import csv
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from database import get_db_connection


def log_event(
    action: str,
    actor_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    actor_role: Optional[str] = None,
    target_entity: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[str] = None,
    severity: str = "INFO",
    ip_address: Optional[str] = "127.0.0.1",
    db_path: Optional[Path] = None,
    conn: Optional[Any] = None,
) -> int:
    """
    Appends an immutable audit log record.
    Severity levels: 'INFO', 'WARNING', 'SECURITY', 'AUDIT'.
    Reuses existing db connection if provided to prevent nested transaction deadlocks.
    """
    valid_severities = {"INFO", "WARNING", "SECURITY", "AUDIT"}
    if severity not in valid_severities:
        severity = "INFO"

    insert_sql = """
        INSERT INTO audit_logs (actor_id, actor_username, actor_role, action, target_entity, target_id, details, severity, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        actor_id,
        actor_username or "System",
        actor_role or "system",
        action,
        target_entity,
        str(target_id) if target_id is not None else None,
        details,
        severity,
        ip_address
    )

    if conn is not None:
        cursor = conn.cursor()
        cursor.execute(insert_sql, params)
        return cursor.lastrowid

    with get_db_connection(db_path) as new_conn:
        cursor = new_conn.cursor()
        cursor.execute(insert_sql, params)
        return cursor.lastrowid


def get_audit_logs(
    actor_id: Optional[int] = None,
    filter_role: Optional[str] = None,
    filter_action: Optional[str] = None,
    filter_severity: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 500,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves filtered audit log records in descending chronological order.
    """
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params: List[Any] = []

    if actor_id is not None:
        query += " AND actor_id = ?"
        params.append(actor_id)

    if filter_role:
        query += " AND actor_role = ?"
        params.append(filter_role)

    if filter_action:
        query += " AND action LIKE ?"
        params.append(f"%{filter_action}%")

    if filter_severity and filter_severity != "ALL":
        query += " AND severity = ?"
        params.append(filter_severity)

    if date_from:
        query += " AND timestamp >= ?"
        params.append(f"{date_from} 00:00:00")

    if date_to:
        query += " AND timestamp <= ?"
        params.append(f"{date_to} 23:59:59")

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitizes values against CSV Formula Injection (CWE-1236).
    Prepends a single quote if string starts with dangerous formula triggers (=, +, -, @, tab, CR).
    """
    if value is None:
        return ""
    str_val = str(value)
    if str_val and str_val[0] in ("=", "+", "-", "@", "\t", "\r", "%"):
        return f"'{str_val}"
    return str_val


def export_audit_logs_csv(logs: List[Dict[str, Any]]) -> str:
    """
    Exports audit logs to safe CSV formatted string.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "Log ID", "Timestamp", "Actor ID", "Username", "Role",
        "Action", "Target Entity", "Target ID", "Details", "Severity", "IP Address"
    ]
    writer.writerow(headers)

    for log in logs:
        writer.writerow([
            sanitize_csv_cell(log.get("id")),
            sanitize_csv_cell(log.get("timestamp")),
            sanitize_csv_cell(log.get("actor_id")),
            sanitize_csv_cell(log.get("actor_username")),
            sanitize_csv_cell(log.get("actor_role")),
            sanitize_csv_cell(log.get("action")),
            sanitize_csv_cell(log.get("target_entity")),
            sanitize_csv_cell(log.get("target_id")),
            sanitize_csv_cell(log.get("details")),
            sanitize_csv_cell(log.get("severity")),
            sanitize_csv_cell(log.get("ip_address")),
        ])

    return output.getvalue()
