"""
Workflow Lifecycle & Asset Management Layer (Alteryx Parity).
Handles workflow schema validation, metadata persistence, viewport tracking,
automatic timestamped backups, asset packaging (.zip / .yxzp), dependency inspection,
and crash recovery autosaves.
"""
import os
import io
import json
import time
import zipfile
import shutil
import re
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from backend.engine.security import (
    sanitize_file_basename,
    is_safe_path,
    validate_safe_path,
    SecurityError
)


class WorkflowManager:
    def __init__(self, workflows_dir: str, data_dir: str, base_dir: str):
        self.workflows_dir = workflows_dir
        self.data_dir = data_dir
        self.base_dir = base_dir

        self.backups_dir = os.path.join(self.workflows_dir, ".backups")
        self.autosave_dir = os.path.join(self.workflows_dir, ".autosave")

        os.makedirs(self.workflows_dir, exist_ok=True)
        os.makedirs(self.backups_dir, exist_ok=True)
        os.makedirs(self.autosave_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Schema Validation & Normalization
    # ------------------------------------------------------------------
    def validate_and_normalize(self, wf_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Validates workflow data structure, normalizes types, prunes dangling connections,
        and stamps metadata.
        Returns (normalized_workflow, warnings).
        """
        if not isinstance(wf_data, dict):
            raise ValueError("Workflow data must be a dictionary object.")

        warnings = []
        normalized = dict(wf_data)

        # 1. Name & metadata
        name = str(normalized.get("name", "Untitled Workflow")).strip() or "Untitled Workflow"
        normalized["name"] = name
        
        metadata = normalized.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        
        now_iso = datetime.now().isoformat(timespec="seconds")
        metadata.setdefault("created_at", now_iso)
        metadata["updated_at"] = now_iso
        metadata.setdefault("version", "2.1.0")
        metadata.setdefault("author", os.environ.get("USERNAME", "Analyst"))
        metadata.setdefault("description", normalized.get("description", ""))
        normalized["metadata"] = metadata
        normalized["description"] = metadata.get("description", "")

        # 2. Viewport coordinates
        viewport = normalized.get("viewport", {})
        if not isinstance(viewport, dict):
            viewport = {}
        normalized["viewport"] = {
            "zoom": float(viewport.get("zoom", 1.0)),
            "panX": float(viewport.get("panX", 0.0)),
            "panY": float(viewport.get("panY", 0.0))
        }

        # 3. Nodes normalization & deduplication
        raw_nodes = normalized.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raw_nodes = []
        
        seen_node_ids = set()
        clean_nodes = []
        for n in raw_nodes:
            if not isinstance(n, dict) or "id" not in n or "type" not in n:
                warnings.append("Skipped malformed node entry missing 'id' or 'type'.")
                continue
            
            node_id = str(n["id"]).strip()
            if not node_id:
                continue
            
            # Deduplicate node IDs if collision occurs
            if node_id in seen_node_ids:
                orig_id = node_id
                node_id = f"{node_id}_{int(time.time() * 1000) % 10000}"
                warnings.append(f"Duplicate node ID '{orig_id}' resolved to '{node_id}'.")
            seen_node_ids.add(node_id)

            clean_node = {
                "id": node_id,
                "type": str(n["type"]).strip(),
                "name": str(n.get("name", n["type"])),
                "x": int(n.get("x", 100)),
                "y": int(n.get("y", 100)),
                "config": dict(n.get("config", {})),
                "container_id": n.get("container_id", None),
                "is_cached": bool(n.get("is_cached", False))
            }
            clean_nodes.append(clean_node)
        
        normalized["nodes"] = clean_nodes
        valid_node_ids = {n["id"] for n in clean_nodes}

        # 4. Connections & Dangling Wire Pruning
        raw_conns = normalized.get("connections", [])
        if not isinstance(raw_conns, list):
            raw_conns = []
        
        clean_conns = []
        for idx, c in enumerate(raw_conns):
            if not isinstance(c, dict):
                continue
            src = str(c.get("source") or c.get("from_node") or "").strip()
            tgt = str(c.get("target") or c.get("to_node") or "").strip()

            if not src or not tgt:
                continue
            
            if src not in valid_node_ids:
                warnings.append(f"Pruned dangling connection: source node '{src}' not found.")
                continue
            if tgt not in valid_node_ids:
                warnings.append(f"Pruned dangling connection: target node '{tgt}' not found.")
                continue

            clean_conns.append({
                "id": str(c.get("id") or f"conn_{src}_{tgt}_{idx}"),
                "source": src,
                "sourceHandle": str(c.get("sourceHandle") or c.get("from_port") or "O"),
                "target": tgt,
                "targetHandle": str(c.get("targetHandle") or c.get("to_port") or "I")
            })
        
        normalized["connections"] = clean_conns

        # 5. Containers & Comments
        normalized["containers"] = normalized.get("containers", [])
        normalized["comments"] = normalized.get("comments", [])

        return normalized, warnings

    # ------------------------------------------------------------------
    # 2. Save Workflow & Versioned Backups
    # ------------------------------------------------------------------
    def save_workflow(
        self, 
        wf_data: Dict[str, Any], 
        custom_filename: Optional[str] = None,
        target_filepath: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates workflow, creates a timestamped backup of any existing file,
        and saves in-place (either to workspace or user-selected target_filepath).
        """
        normalized, warnings = self.validate_and_normalize(wf_data)

        if target_filepath:
            target_path = os.path.abspath(target_filepath)
            if not (target_path.lower().endswith(".json") or target_path.lower().endswith(".yxmd")):
                target_path += ".json"
            target_filename = os.path.basename(target_path)
            target_dir = os.path.dirname(target_path)
            os.makedirs(target_dir, exist_ok=True)
            clean_stem = os.path.splitext(target_filename)[0]
        else:
            raw_name = custom_filename or normalized.get("name", "untitled_workflow")
            if raw_name.lower().endswith(".json"):
                raw_name = raw_name[:-5]
            elif raw_name.lower().endswith(".yxmd"):
                raw_name = raw_name[:-5]
            cleaned_raw = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_name.lower())
            cleaned_raw = re.sub(r'_+', '_', cleaned_raw).strip('_')
            clean_stem = sanitize_file_basename(
                cleaned_raw,
                fallback="untitled_workflow"
            )
            target_filename = f"{clean_stem}.json"
            target_path = os.path.join(self.workflows_dir, target_filename)
            validate_safe_path(target_path, [self.workflows_dir])

        # Create timestamped revision backup if target file already exists
        backup_created = None
        if os.path.isfile(target_path):
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_filename = f"{clean_stem}_{timestamp_str}.json"
            backup_path = os.path.join(self.backups_dir, backup_filename)
            try:
                shutil.copy2(target_path, backup_path)
                backup_created = backup_filename
                self._prune_old_backups(clean_stem, max_keep=10)
            except Exception as e:
                warnings.append(f"Could not create backup snapshot: {str(e)}")

        # Write workflow file atomically
        temp_path = f"{target_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)
        shutil.move(temp_path, target_path)

        # Synchronize into workspace workflows folder if saved externally
        workspace_copy_path = os.path.join(self.workflows_dir, target_filename)
        if os.path.abspath(workspace_copy_path) != os.path.abspath(target_path):
            try:
                shutil.copy2(target_path, workspace_copy_path)
            except Exception:
                pass

        return {
            "success": True,
            "file": target_filename,
            "filename": target_filename,
            "path": target_path.replace("\\", "/"),
            "name": normalized["name"],
            "node_count": len(normalized["nodes"]),
            "connection_count": len(normalized["connections"]),
            "backup_created": backup_created,
            "warnings": warnings,
            "workflow": normalized,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def load_from_path(self, filepath: str) -> Dict[str, Any]:
        """Loads and normalizes workflow JSON from an arbitrary disk path chosen in Windows Explorer."""
        clean_p = os.path.abspath(filepath)
        if not os.path.isfile(clean_p):
            raise FileNotFoundError(f"Workflow file does not exist: {clean_p}")

        with open(clean_p, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        normalized, warnings = self.validate_and_normalize(raw_data)
        filename = os.path.basename(clean_p)
        return {
            "success": True,
            "filename": filename,
            "path": clean_p.replace("\\", "/"),
            "name": normalized.get("name") or os.path.splitext(filename)[0],
            "workflow": normalized,
            "warnings": warnings
        }

    def _prune_old_backups(self, workflow_stem: str, max_keep: int = 10) -> None:
        """Keeps at most max_keep historical revisions for a workflow stem."""
        try:
            prefix = f"{workflow_stem}_"
            backups = []
            for fn in os.listdir(self.backups_dir):
                if fn.startswith(prefix) and fn.endswith(".json"):
                    full_p = os.path.join(self.backups_dir, fn)
                    if os.path.isfile(full_p):
                        backups.append((os.path.getmtime(full_p), full_p))
            
            backups.sort(key=lambda x: x[0], reverse=True)
            for _, old_path in backups[max_keep:]:
                try:
                    os.remove(old_path)
                except Exception:
                    pass
        except Exception:
            pass

    def get_revisions(self, filename: str) -> List[Dict[str, Any]]:
        """Returns list of timestamped backups for a workflow file."""
        raw_stem = sanitize_file_basename(filename).replace(".json", "")
        cleaned_stem = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_stem.lower())
        stem = re.sub(r'_+', '_', cleaned_stem).strip('_')
        prefix = f"{stem}_"
        revisions = []

        if os.path.exists(self.backups_dir):
            for fn in sorted(os.listdir(self.backups_dir), reverse=True):
                if fn.startswith(prefix) and fn.endswith(".json"):
                    full_p = os.path.join(self.backups_dir, fn)
                    try:
                        mtime = os.path.getmtime(full_p)
                        size_bytes = os.path.getsize(full_p)
                        with open(full_p, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        commit_meta = data.get("_commit_meta", {})
                        revisions.append({
                            "backup_file": fn,
                            "workflow_name": data.get("name", stem),
                            "timestamp": commit_meta.get("iso_time") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                            "mtime": mtime,
                            "size_bytes": size_bytes,
                            "size_kb": round(size_bytes / 1024, 1),
                            "node_count": len(data.get("nodes", [])),
                            "connection_count": len(data.get("connections", [])),
                            "commit_message": commit_meta.get("message") or "",
                            "author": commit_meta.get("author") or "",
                            "tag": commit_meta.get("tag") or ""
                        })
                    except Exception:
                        pass
        return revisions

    def commit_checkpoint(
        self,
        filename: str,
        wf_data: Dict[str, Any],
        message: str,
        author: str = "User",
        tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates an explicit named version checkpoint with commit metadata."""
        raw_stem = sanitize_file_basename(filename).replace(".json", "")
        cleaned_stem = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_stem.lower())
        clean_stem = re.sub(r'_+', '_', cleaned_stem).strip('_')

        normalized, warnings = self.validate_and_normalize(wf_data)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_filename = f"{clean_stem}_{timestamp_str}.json"
        backup_path = os.path.join(self.backups_dir, backup_filename)
        validate_safe_path(backup_path, [self.backups_dir])

        commit_meta = {
            "message": message.strip() if message else "Manual checkpoint",
            "author": author.strip() if author else "User",
            "tag": tag.strip() if tag else None,
            "timestamp": time.time(),
            "iso_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        normalized["_commit_meta"] = commit_meta

        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

        self._prune_old_backups(clean_stem, max_keep=25)

        return {
            "success": True,
            "backup_file": backup_filename,
            "filename": filename,
            "commit_meta": commit_meta,
            "workflow_name": normalized.get("name", clean_stem),
            "node_count": len(normalized.get("nodes", [])),
            "saved_at": commit_meta["iso_time"]
        }

    def get_revision_content(self, backup_filename: str) -> Dict[str, Any]:
        """Loads and returns the content of a specific backup revision."""
        safe_backup = sanitize_file_basename(backup_filename)
        backup_path = os.path.join(self.backups_dir, safe_backup)
        validate_safe_path(backup_path, [self.backups_dir])

        if not os.path.isfile(backup_path):
            raise FileNotFoundError(f"Revision backup '{safe_backup}' not found.")

        with open(backup_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        normalized, warnings = self.validate_and_normalize(data)
        return {
            "success": True,
            "backup_file": safe_backup,
            "workflow": normalized,
            "commit_meta": data.get("_commit_meta", {}),
            "warnings": warnings
        }

    def compute_diff(self, base_wf: Dict[str, Any], target_wf: Dict[str, Any]) -> Dict[str, Any]:
        """Computes structural DAG and configuration differences between two workflows."""
        base_nodes = {n.get("id"): n for n in base_wf.get("nodes", []) if isinstance(n, dict)}
        target_nodes = {n.get("id"): n for n in target_wf.get("nodes", []) if isinstance(n, dict)}

        added_node_ids = sorted(list(set(target_nodes.keys()) - set(base_nodes.keys())))
        removed_node_ids = sorted(list(set(base_nodes.keys()) - set(target_nodes.keys())))
        common_node_ids = sorted(list(set(base_nodes.keys()) & set(target_nodes.keys())))

        added_nodes = [
            {"id": nid, "name": target_nodes[nid].get("name", nid), "type": target_nodes[nid].get("type", "unknown")}
            for nid in added_node_ids
        ]
        removed_nodes = [
            {"id": nid, "name": base_nodes[nid].get("name", nid), "type": base_nodes[nid].get("type", "unknown")}
            for nid in removed_node_ids
        ]

        modified_nodes = []
        for nid in common_node_ids:
            bn = base_nodes[nid]
            tn = target_nodes[nid]
            changes = []
            if bn.get("name") != tn.get("name"):
                changes.append(f"Renamed: '{bn.get('name')}' → '{tn.get('name')}'")
            if bn.get("type") != tn.get("type"):
                changes.append(f"Type changed: '{bn.get('type')}' → '{tn.get('type')}'")
            b_cfg = bn.get("config", {}) or {}
            t_cfg = tn.get("config", {}) or {}
            if b_cfg != t_cfg:
                cfg_keys = sorted(list(set(b_cfg.keys()) | set(t_cfg.keys())))
                changed_keys = [k for k in cfg_keys if b_cfg.get(k) != t_cfg.get(k)]
                if changed_keys:
                    changes.append(f"Config edited ({len(changed_keys)} field{'s' if len(changed_keys) > 1 else ''}): {', '.join(changed_keys[:4])}{'...' if len(changed_keys) > 4 else ''}")
            if changes:
                modified_nodes.append({
                    "id": nid,
                    "name": tn.get("name") or bn.get("name") or nid,
                    "type": tn.get("type") or bn.get("type"),
                    "changes": changes
                })

        base_conns = {
            f"{c.get('source')}:{c.get('source_port', 'O')}->{c.get('target')}:{c.get('target_port', 'I')}"
            for c in base_wf.get("connections", []) if isinstance(c, dict)
        }
        target_conns = {
            f"{c.get('source')}:{c.get('source_port', 'O')}->{c.get('target')}:{c.get('target_port', 'I')}"
            for c in target_wf.get("connections", []) if isinstance(c, dict)
        }

        added_conns = sorted(list(target_conns - base_conns))
        removed_conns = sorted(list(base_conns - target_conns))

        return {
            "summary": {
                "added_nodes_count": len(added_nodes),
                "removed_nodes_count": len(removed_nodes),
                "modified_nodes_count": len(modified_nodes),
                "added_connections_count": len(added_conns),
                "removed_connections_count": len(removed_conns),
                "is_identical": not (added_nodes or removed_nodes or modified_nodes or added_conns or removed_conns)
            },
            "added_nodes": added_nodes,
            "removed_nodes": removed_nodes,
            "modified_nodes": modified_nodes,
            "added_connections": added_conns,
            "removed_connections": removed_conns
        }

    def revert_revision(self, filename: str, backup_filename: str) -> Dict[str, Any]:
        """Restores a previous revision snapshot into the primary workflow file."""
        raw_stem = sanitize_file_basename(filename).replace(".json", "")
        cleaned_stem = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_stem.lower())
        stem = re.sub(r'_+', '_', cleaned_stem).strip('_')
        safe_backup = sanitize_file_basename(backup_filename)
        backup_path = os.path.join(self.backups_dir, safe_backup)
        validate_safe_path(backup_path, [self.backups_dir])

        if not os.path.isfile(backup_path):
            raise FileNotFoundError(f"Revision backup '{safe_backup}' not found.")

        target_file = f"{stem}.json"
        target_path = os.path.join(self.workflows_dir, target_file)
        validate_safe_path(target_path, [self.workflows_dir])

        with open(backup_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Save and return
        return self.save_workflow(data, custom_filename=target_file)

    # ------------------------------------------------------------------
    # 3. Asset & Dependency Inspection (Alteryx Parity)
    # ------------------------------------------------------------------
    def inspect_dependencies(self, wf_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scans all nodes for external asset references (input files, output paths).
        Returns detailed asset status, file sizes, existence, and missing alerts.
        """
        nodes = wf_data.get("nodes", []) if isinstance(wf_data, dict) else []
        assets = []
        missing_count = 0

        for n in nodes:
            node_id = n.get("id", "")
            node_type = n.get("type", "")
            node_name = n.get("name", node_type)
            cfg = n.get("config", {})

            if node_type == "input_data":
                raw_path = cfg.get("file_path", "").strip()
                if raw_path:
                    status, full_path, size_bytes = self._check_asset_path(raw_path)
                    if not status:
                        missing_count += 1
                    assets.append({
                        "node_id": node_id,
                        "node_name": node_name,
                        "node_type": node_type,
                        "role": "input",
                        "role_label": "Input Dataset",
                        "path": raw_path,
                        "configured_path": raw_path,
                        "resolved_path": full_path.replace("\\", "/") if full_path else None,
                        "exists": status,
                        "size_bytes": size_bytes if status else 0,
                        "size_kb": round(size_bytes / 1024, 1) if size_bytes else 0,
                        "sheet_name": cfg.get("sheet_name", None),
                        "file_type": cfg.get("file_type", "csv")
                    })

            elif node_type == "output_data":
                filename = cfg.get("filename", "").strip()
                fmt = cfg.get("format", "csv")
                if filename:
                    ext = f".{fmt}" if not filename.endswith(f".{fmt}") else ""
                    expected_file = f"{filename}{ext}"
                    out_path = os.path.join(self.data_dir, "outputs", expected_file)
                    exists = os.path.isfile(out_path)
                    size = os.path.getsize(out_path) if exists else 0
                    assets.append({
                        "node_id": node_id,
                        "node_name": node_name,
                        "node_type": node_type,
                        "role": "output",
                        "role_label": "Output Destination",
                        "path": expected_file,
                        "configured_path": expected_file,
                        "resolved_path": out_path.replace("\\", "/"),
                        "exists": exists,
                        "size_bytes": size if exists else 0,
                        "size_kb": round(size / 1024, 1) if exists else 0,
                        "format": fmt
                    })

        return {
            "workflow_name": wf_data.get("name", "Workflow"),
            "total_assets": len(assets),
            "total_dependencies": len(assets),
            "missing_assets": missing_count,
            "missing_count": missing_count,
            "has_missing": missing_count > 0,
            "assets": assets,
            "dependencies": assets
        }

    def _check_asset_path(self, raw_path: str) -> Tuple[bool, Optional[str], int]:
        """Resolves file path against DATA_DIR and BASE_DIR. Returns (exists, resolved_path, size)."""
        candidates = []
        if os.path.isabs(raw_path):
            candidates.append(raw_path)
        else:
            candidates.append(os.path.join(self.data_dir, raw_path))
            if raw_path.startswith(("data/", "data\\")):
                candidates.append(os.path.join(self.data_dir, raw_path[5:]))
            candidates.append(os.path.join(self.data_dir, os.path.basename(raw_path)))
            candidates.append(os.path.join(self.base_dir, raw_path))

        for cand in candidates:
            if cand and os.path.isfile(cand):
                try:
                    size = os.path.getsize(cand)
                    return True, cand, size
                except Exception:
                    return True, cand, 0
        return False, None, 0

    # ------------------------------------------------------------------
    # 4. Workflow Package (.zip / .yxzp Bundler)
    # ------------------------------------------------------------------
    def export_package(self, wf_data: Dict[str, Any]) -> io.BytesIO:
        """
        Packages workflow JSON and all its referenced input datasets into a single
        zip archive with normalized relative paths for 100% portable sharing.
        """
        normalized, _ = self.validate_and_normalize(wf_data)
        zip_buffer = io.BytesIO()

        packaged_files = set()
        data_manifest = []

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Collect and add referenced input data files
            for node in normalized.get("nodes", []):
                if node.get("type") == "input_data":
                    raw_path = node.get("config", {}).get("file_path", "")
                    if not raw_path or "*" in raw_path or "?" in raw_path:
                        continue
                    
                    exists, resolved_p, size = self._check_asset_path(raw_path)
                    if exists and resolved_p:
                        base_fn = os.path.basename(resolved_p)
                        arc_path = f"data/{base_fn}"
                        if arc_path not in packaged_files:
                            zf.write(resolved_p, arcname=arc_path)
                            packaged_files.add(arc_path)
                            data_manifest.append({
                                "original_path": raw_path,
                                "package_path": arc_path,
                                "size_bytes": size
                            })
                        # Rewrite node file_path to relative packaged path
                        node["config"]["file_path"] = arc_path

            # 2. Add workflow.json
            wf_json_bytes = json.dumps(normalized, indent=2).encode("utf-8")
            zf.writestr("workflow.json", wf_json_bytes)

            # 3. Add manifest.json
            manifest = {
                "package_format": "DataFlow-Package-1.0",
                "exported_at": datetime.now().isoformat(),
                "workflow_name": normalized["name"],
                "node_count": len(normalized["nodes"]),
                "assets": data_manifest
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

        zip_buffer.seek(0)
        return zip_buffer

    def import_package(self, zip_file_obj: Any) -> Dict[str, Any]:
        """
        Extracts a workflow package (.zip / .yxzp), verifies paths against zip-slip,
        copies datasets to DATA_DIR, saves the workflow to WORKFLOWS_DIR, and returns
        the loaded workflow object.
        """
        with zipfile.ZipFile(zip_file_obj, "r") as zf:
            namelist = zf.namelist()
            if "workflow.json" not in namelist:
                raise ValueError("Invalid package: 'workflow.json' missing from root of archive.")

            extracted_data_files = []

            # Extract data assets safely
            for member in namelist:
                # Zip-slip prevention
                clean_target = os.path.normpath(member).replace("\\", "/")
                if clean_target.startswith("../") or clean_target.startswith("/") or ".." in clean_target:
                    raise SecurityError(f"Forbidden: Malicious zip entry path '{member}'")

                if clean_target.startswith("data/") and not clean_target.endswith("/"):
                    filename = os.path.basename(clean_target)
                    safe_filename = sanitize_file_basename(filename)
                    dest_path = os.path.join(self.data_dir, safe_filename)
                    validate_safe_path(dest_path, [self.data_dir])

                    with zf.open(member) as src_f, open(dest_path, "wb") as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
                    extracted_data_files.append(safe_filename)

            # Read workflow definition
            with zf.open("workflow.json") as wf_file:
                wf_content = wf_file.read().decode("utf-8")
                wf_data = json.loads(wf_content)

            # Re-map relative paths to extracted data files in DATA_DIR
            for node in wf_data.get("nodes", []):
                if node.get("type") == "input_data":
                    fp = node.get("config", {}).get("file_path", "")
                    if fp:
                        base_name = os.path.basename(fp)
                        node["config"]["file_path"] = f"data/{base_name}"

            # Save extracted workflow
            save_result = self.save_workflow(wf_data)

            return {
                "success": True,
                "workflow": wf_data,
                "workflow_file": save_result["file"],
                "extracted_assets": extracted_data_files,
                "extracted_files": extracted_data_files,
                "message": f"Successfully imported package '{wf_data.get('name')}' with {len(extracted_data_files)} dataset(s)."
            }

    # ------------------------------------------------------------------
    # 5. Auto-Save & Crash Recovery
    # ------------------------------------------------------------------
    def save_autosave(self, session_id: str, wf_data: Dict[str, Any]) -> Dict[str, Any]:
        """Saves a temporary recovery snapshot for an active user session."""
        safe_sid = sanitize_file_basename(session_id or "default_session")
        target_path = os.path.join(self.autosave_dir, f"autosave_{safe_sid}.json")
        validate_safe_path(target_path, [self.autosave_dir])

        normalized, _ = self.validate_and_normalize(wf_data)
        normalized["_autosave_meta"] = {
            "session_id": safe_sid,
            "timestamp": time.time(),
            "iso_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

        return {
            "success": True,
            "session_id": safe_sid,
            "saved_at": normalized["_autosave_meta"]["iso_time"]
        }

    def get_autosave(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves active autosave for session if present and valid."""
        safe_sid = sanitize_file_basename(session_id or "default_session")
        target_path = os.path.join(self.autosave_dir, f"autosave_{safe_sid}.json")
        if not os.path.isfile(target_path):
            return None

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def clear_autosave(self, session_id: str) -> bool:
        """Cleans up temporary recovery snapshot on clean save or explicit discard."""
        safe_sid = sanitize_file_basename(session_id or "default_session")
        target_path = os.path.join(self.autosave_dir, f"autosave_{safe_sid}.json")
        if os.path.isfile(target_path):
            try:
                os.remove(target_path)
                return True
            except Exception:
                pass
        return False

    def get_available_recoveries(self) -> List[Dict[str, Any]]:
        """Scans autosave directory for all orphaned or recoverable sessions."""
        recoveries = []
        if not os.path.isdir(self.autosave_dir):
            return recoveries

        for fn in os.listdir(self.autosave_dir):
            if fn.startswith("autosave_") and fn.endswith(".json"):
                full_p = os.path.join(self.autosave_dir, fn)
                if not os.path.isfile(full_p):
                    continue
                try:
                    mtime = os.path.getmtime(full_p)
                    size = os.path.getsize(full_p)
                    with open(full_p, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    meta = data.get("_autosave_meta", {})
                    sid = meta.get("session_id") or fn.replace("autosave_", "").replace(".json", "")
                    iso_time = meta.get("iso_time") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))

                    recoveries.append({
                        "session_id": sid,
                        "filename": fn,
                        "workflow_name": data.get("name", "Untitled Workflow"),
                        "node_count": len(data.get("nodes", [])),
                        "connection_count": len(data.get("connections", [])),
                        "size_bytes": size,
                        "saved_at": iso_time,
                        "mtime": mtime,
                        "workflow": data
                    })
                except Exception:
                    pass

        recoveries.sort(key=lambda x: x.get("mtime", 0), reverse=True)
        return recoveries

    def clear_all_autosaves(self) -> int:
        """Removes all autosave files on clean exit or explicit user discard."""
        count = 0
        if os.path.isdir(self.autosave_dir):
            for fn in os.listdir(self.autosave_dir):
                if fn.startswith("autosave_") and fn.endswith(".json"):
                    try:
                        os.remove(os.path.join(self.autosave_dir, fn))
                        count += 1
                    except Exception:
                        pass
        return count

