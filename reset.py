from datetime import datetime
from pathlib import Path
import shutil
import json

CONFIRMATION = "StarFur Factory Reset"
ASSISTANT_TABLES = ("assistant_memory_proposal_evidence", "assistant_memory_proposals", "assistant_memories")

def factory_reset(db_path, *, scope="assistant-and-semantic", confirmation=None, allow_production=False, chroma_client=None, collection_name="starfur_canon", backup_dir=None, backup=True):
    from pipeline import db
    path=Path(db_path).resolve()
    if confirmation != CONFIRMATION: raise ValueError("Factory reset requires the exact confirmation phrase.")
    production=Path(db.DB_PATH).resolve() == path
    if production and not allow_production: raise PermissionError("Production reset requires --allow-production-reset.")
    if scope not in {"assistant-only","semantic-only","assistant-and-semantic"}: raise ValueError("Invalid reset scope")
    if scope in {"semantic-only","assistant-and-semantic"} and chroma_client is None: raise RuntimeError("Semantic reset requires an explicitly supplied Chroma client.")
    backup_path=None; counts={}
    backup_root = Path(backup_dir) if backup_dir else Path.home() / "StarFur-Forge" / "backup"
    backup_dir_path = None
    if backup:
        backup_dir_path = backup_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir_path.mkdir(parents=True, exist_ok=False)
    if scope in {"assistant-only","assistant-and-semantic"}:
        if backup:
            backup_path = backup_dir_path / "starfur.db"
            shutil.copy2(path, backup_path)
        with db.connect() as connection:
            for table in ASSISTANT_TABLES: counts[table]=connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            connection.execute("BEGIN")
            for table in ASSISTANT_TABLES: connection.execute(f"DELETE FROM {table}")
            connection.commit()
    if scope in {"semantic-only","assistant-and-semantic"}:
        if backup:
            try:
                snapshot = chroma_client.get_collection(name=collection_name).get(include=["documents", "metadatas", "embeddings"])
                (backup_dir_path / "chroma.json").write_text(json.dumps(snapshot, default=lambda value: value.tolist() if hasattr(value, "tolist") else value), encoding="utf-8")
            except Exception as error:
                raise RuntimeError(f"Chroma backup failed; reset aborted: {error}") from error
        try: chroma_client.delete_collection(name=collection_name)
        except Exception as error:
            if "not found" not in str(error).lower(): raise
    return {"scope":scope,"backup":str(backup_dir_path) if backup_dir_path else None,"deleted":counts}


def list_backups(backup_root=None):
    root=Path(backup_root) if backup_root else Path.home()/"StarFur-Forge"/"backup"
    if not root.exists(): return []
    return sorted((item for item in root.iterdir() if item.is_dir() and (item/"starfur.db").exists()), key=lambda item:item.name, reverse=True)

def factory_restore(db_path, backup_dir, *, confirmation=None, allow_production=False, backup_root=None, chroma_client=None, collection_name="starfur_canon"):
    from pipeline import db
    path=Path(db_path).resolve(); source=Path(backup_dir).resolve()
    if confirmation != "StarFur Factory Restore": raise ValueError("Factory restore requires the exact confirmation phrase.")
    if Path(db.DB_PATH).resolve()==path and not allow_production: raise PermissionError("Production restore requires --allow-production-reset.")
    if not source.is_dir() or not (source/"starfur.db").exists(): raise ValueError("Invalid backup directory.")
    chroma_snapshot = source / "chroma.json"
    if chroma_snapshot.exists() and chroma_client is None: raise RuntimeError("Backup contains Chroma data but no Chroma client was supplied.")
    safety_root=Path(backup_root) if backup_root else Path.home()/"StarFur-Forge"/"backup"
    safety=safety_root/("pre-restore-"+datetime.now().strftime("%Y%m%d-%H%M%S")); safety.mkdir(parents=True,exist_ok=False)
    shutil.copy2(path,safety/"starfur.db")
    replacement=path.with_suffix(path.suffix+".restore-tmp"); shutil.copy2(source/"starfur.db",replacement); replacement.replace(path)
    if chroma_snapshot.exists():
        snapshot=json.loads(chroma_snapshot.read_text(encoding="utf-8"))
        try: chroma_client.delete_collection(name=collection_name)
        except Exception: pass
        collection=chroma_client.get_or_create_collection(collection_name)
        payload={key:snapshot[key] for key in ("ids","documents","metadatas","embeddings") if key in snapshot and snapshot[key]}
        if payload.get("ids"): collection.add(**payload)
    return {"restored":str(source),"safety_backup":str(safety)}
