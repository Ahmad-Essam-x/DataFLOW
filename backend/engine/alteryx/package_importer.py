"""
Alteryx Packaged Workflow (.yxzp) Importer.
Unpacks .yxzp zip archives, extracts bundled data files into the workspace data directory,
locates and parses the enclosed .yxmd workflow, and remaps relative dataset references.
"""
import os
import shutil
import zipfile
import logging
from typing import Dict, Any, List, Optional

from backend.engine.security import sanitize_file_basename, validate_safe_path, SecurityError
from .yxmd_parser import parse_yxmd_content

logger = logging.getLogger(__name__)


def import_yxzp_package(zip_file_obj: Any, data_dir: str, workflows_dir: str) -> Dict[str, Any]:
    """
    Extracts an Alteryx packaged workflow (.yxzp), unpacks datasets into data_dir,
    parses the embedded .yxmd file, remaps input_data paths, and returns the result.
    """
    with zipfile.ZipFile(zip_file_obj, "r") as zf:
        namelist = zf.namelist()
        
        # 1. Find the main .yxmd workflow in the archive
        yxmd_candidates = [m for m in namelist if m.lower().endswith(".yxmd") and not m.startswith("__MACOSX")]
        if not yxmd_candidates:
            raise ValueError("Invalid Alteryx package: no .yxmd workflow found inside archive.")

        # Sort so root-level or shortest path candidate comes first
        yxmd_candidates.sort(key=lambda x: (x.count("/"), len(x)))
        main_yxmd_member = yxmd_candidates[0]

        extracted_data_files: List[str] = []
        data_file_map: Dict[str, str] = {}  # original basename -> new local filename

        # 2. Extract referenced data assets safely
        data_extensions = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".parquet", ".pq", ".json", ".yxdb"}
        
        for member in namelist:
            if member == main_yxmd_member or member.endswith("/"):
                continue

            # Zip-slip prevention
            clean_target = os.path.normpath(member).replace("\\", "/")
            if clean_target.startswith("../") or clean_target.startswith("/") or ".." in clean_target:
                raise SecurityError(f"Forbidden: Malicious zip entry path '{member}'")

            ext = os.path.splitext(member)[1].lower()
            if ext in data_extensions:
                base_name = os.path.basename(member)
                safe_name = sanitize_file_basename(base_name)
                dest_path = os.path.join(data_dir, safe_name)
                validate_safe_path(dest_path, [data_dir])

                with zf.open(member) as src_f, open(dest_path, "wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)
                
                extracted_data_files.append(safe_name)
                data_file_map[base_name.lower()] = safe_name

        # 3. Read and parse the .yxmd workflow
        with zf.open(main_yxmd_member) as yxmd_f:
            xml_content = yxmd_f.read().decode("utf-8-sig", errors="replace")

        workflow_filename = os.path.basename(main_yxmd_member)
        parse_result = parse_yxmd_content(xml_content, source_name=workflow_filename)
        wf_dict = parse_result.workflow

        # 4. Remap input_data node paths to extracted files
        for node in wf_dict.get("nodes", []):
            if node.get("type") == "input_data":
                cfg = node.get("config", {})
                fp = cfg.get("file_path", "")
                if fp:
                    fp_base = os.path.basename(fp).lower()
                    if fp_base in data_file_map:
                        matched_name = data_file_map[fp_base]
                        cfg["file_path"] = f"data/{matched_name}"
                        cfg["resolved_path"] = os.path.join(data_dir, matched_name).replace("\\", "/")

        return {
            "success": True,
            "is_package": True,
            "workflow": wf_dict,
            "warnings": [w.to_dict() for w in parse_result.warnings],
            "stats": parse_result.to_dict()["stats"],
            "extracted_files": extracted_data_files,
            "main_workflow_file": main_yxmd_member,
            "message": f"Successfully unpacked Alteryx package '{workflow_filename}' with {len(extracted_data_files)} data asset(s)."
        }
