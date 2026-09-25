"""
Workflow Execution Engine.
Executes the workflow graph in topological order, caches intermediate DataFrames,
collects execution telemetry, and provides profiling and pagination utilities.
"""
import os
import re
import uuid
import time
import threading
import math
import concurrent.futures
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Set

from backend.engine.dag import DAG, WorkflowValidationError
from backend.engine.node_registry import (
    NODE_REGISTRY, NodeExecutionError, sanitize_dataframe,
    infer_alteryx_type, map_alteryx_to_category
)
from backend.engine.error_diagnostics import diagnose_error, ErrorDiagnostic
from backend.engine.cache_manager import SessionRunCacheManager, RunCacheEntry, SpillableRunDataCache, compute_column_metadata


class ExecutionResult:
    def __init__(self, run_id: str = "", session_id: Optional[str] = None):
        self.run_id: str = run_id
        self.session_id: Optional[str] = session_id
        self.success: bool = True
        self.total_duration_ms: float = 0.0
        self.node_results: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.error: Optional[str] = None
        self.diagnostic: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "success": self.success,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "node_results": self.node_results,
            "logs": self.logs,
            "error": self.error,
            "diagnostic": self.diagnostic
        }


class WorkflowExecutor:
    def __init__(self, context: Optional[Dict[str, Any]] = None, cache_manager: Optional[SessionRunCacheManager] = None):
        self.context = dict(context or {})
        if "data_dir" not in self.context:
            default_data = os.path.join(os.getcwd(), "data")
            if os.path.exists(default_data):
                self.context["data_dir"] = default_data
        self.cache_manager: SessionRunCacheManager = cache_manager or SessionRunCacheManager()
        self._local_data_cache = SpillableRunDataCache(run_id="local_exec", cache_root_dir=self.cache_manager.cache_root_dir)
        self.last_result: Optional[ExecutionResult] = None
        self._active_cancellations: Dict[str, threading.Event] = {}
        self.frozen_node_cache = SpillableRunDataCache(run_id="frozen_cache", cache_root_dir=self.cache_manager.cache_root_dir)
        self.persistent_cache_dir = os.path.join(self.context.get("data_dir", os.path.join(os.getcwd(), "data")), ".cache")
        try:
            os.makedirs(self.persistent_cache_dir, exist_ok=True)
        except Exception:
            pass

    def persist_locked_node(self, node_id: str, outputs: Dict[str, pd.DataFrame]):
        """Serializes locked outputs to persistent disk storage (data/.cache/) using Feather or Parquet."""
        if not outputs:
            return
        try:
            safe_nid = re.sub(r"[^\w\-_\.]", "_", node_id)
            for port, val in outputs.items():
                if isinstance(val, pd.DataFrame):
                    safe_port = re.sub(r"[^\w\-_\.]", "_", port)
                    file_path = os.path.join(self.persistent_cache_dir, f"{safe_nid}_{safe_port}.feather")
                    try:
                        import pyarrow.feather as feather
                        feather.write_feather(val, file_path, compression="lz4")
                    except Exception:
                        try:
                            val.to_parquet(file_path.replace(".feather", ".parquet"))
                        except Exception:
                            pass
        except Exception:
            pass

    def load_persisted_locked_node(self, node_id: str) -> Optional[Dict[str, pd.DataFrame]]:
        """Loads locked outputs from persistent disk storage into memory if available."""
        try:
            safe_nid = re.sub(r"[^\w\-_\.]", "_", node_id)
            prefix = f"{safe_nid}_"
            if not os.path.exists(self.persistent_cache_dir):
                return None

            loaded_ports: Dict[str, pd.DataFrame] = {}
            for fname in os.listdir(self.persistent_cache_dir):
                if fname.startswith(prefix) and (fname.endswith(".feather") or fname.endswith(".parquet")):
                    port_part = fname[len(prefix):].rsplit(".", 1)[0]
                    fpath = os.path.join(self.persistent_cache_dir, fname)
                    try:
                        if fname.endswith(".feather"):
                            import pyarrow.feather as feather
                            loaded_ports[port_part] = feather.read_feather(fpath)
                        else:
                            loaded_ports[port_part] = pd.read_parquet(fpath)
                    except Exception:
                        pass
            if loaded_ports:
                self.frozen_node_cache[node_id] = loaded_ports
                return loaded_ports
        except Exception:
            pass
        return None

    def remove_persisted_locked_node(self, node_id: str) -> bool:
        """Removes persistent locked cache files for node_id."""
        removed_any = False
        try:
            safe_nid = re.sub(r"[^\w\-_\.]", "_", node_id)
            prefix = f"{safe_nid}_"
            if os.path.exists(self.persistent_cache_dir):
                for fname in os.listdir(self.persistent_cache_dir):
                    if fname.startswith(prefix):
                        try:
                            os.remove(os.path.join(self.persistent_cache_dir, fname))
                            removed_any = True
                        except Exception:
                            pass
        except Exception:
            pass
        return removed_any

    @property
    def data_cache(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        latest = self.cache_manager.get_latest_run()
        if latest is not None:
            return latest.data_cache
        return self._local_data_cache

    @data_cache.setter
    def data_cache(self, val: Dict[str, Dict[str, pd.DataFrame]]):
        self._local_data_cache = val
        latest = self.cache_manager.get_latest_run()
        if latest is not None:
            latest.data_cache = val

    def cancel_run(self, run_id: Optional[str] = None) -> bool:
        """Signals an in-flight execution to abort immediately."""
        cancelled = False
        if run_id and run_id in self._active_cancellations:
            self._active_cancellations[run_id].set()
            cancelled = True
        else:
            for event in list(self._active_cancellations.values()):
                event.set()
                cancelled = True
        return cancelled

    def clear_frozen_cache(self, node_id: Optional[str] = None) -> bool:
        """Clears cached tables for a frozen node or all frozen nodes."""
        if node_id:
            removed_persisted = self.remove_persisted_locked_node(node_id)
            if node_id in self.frozen_node_cache:
                del self.frozen_node_cache[node_id]
                return True
            return removed_persisted
        if os.path.exists(self.persistent_cache_dir):
            for f in os.listdir(self.persistent_cache_dir):
                try:
                    os.remove(os.path.join(self.persistent_cache_dir, f))
                except Exception:
                    pass
        self.frozen_node_cache.clear()
        return True

    def get_frozen_node_ids(self) -> List[str]:
        """Returns list of currently cached node IDs in frozen memory cache."""
        return list(self.frozen_node_cache.keys())

    def run(
        self,
        workflow: Dict[str, Any],
        observer_cb: Optional[Any] = None,
        use_cache: bool = True,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> ExecutionResult:
        actual_session_id = session_id or workflow.get("session_id")
        actual_run_id = run_id or workflow.get("run_id")
        run_entry = self.cache_manager.create_run(
            session_id=actual_session_id,
            workflow_name=workflow.get("name", ""),
            run_id=actual_run_id
        )

        result = ExecutionResult(run_id=run_entry.run_id, session_id=run_entry.session_id)
        start_time = time.time()
        current_run_cache = run_entry.data_cache

        nodes = workflow.get("nodes", [])
        connections = workflow.get("connections", [])

        if not nodes:
            result.success = True
            result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "INFO", "message": "Workflow is empty."})
            self.last_result = result
            return result

        # Map node_id -> node_dict
        node_map = {n["id"]: n for n in nodes}

        # Identify disabled containers and enclosed nodes
        containers = workflow.get("containers", [])
        disabled_container_ids = {c["id"] for c in containers if c.get("disabled")}
        disabled_node_ids = set()

        for c in containers:
            if c.get("disabled"):
                disabled_node_ids.update(c.get("node_ids") or c.get("nodeIds") or [])

        for n in nodes:
            if n.get("disabled") or n.get("container_id") in disabled_container_ids or n.get("containerId") in disabled_container_ids:
                disabled_node_ids.add(n["id"])

        # Also filter out documentation/annotation nodes if present in nodes list
        doc_node_ids = {n["id"] for n in nodes if n.get("type") in ["tool_container", "comment"]}
        skipped_node_ids = disabled_node_ids.union(doc_node_ids)

        for sid in skipped_node_ids:
            if sid in node_map:
                n_info = node_map[sid]
                is_doc = n_info.get("type") in ["tool_container", "comment"]
                status_label = "info" if is_doc else "disabled"
                result.node_results[sid] = {
                    "id": sid,
                    "type": n_info.get("type"),
                    "name": n_info.get("name") or n_info.get("type"),
                    "status": status_label,
                    "duration_ms": 0.0,
                    "record_counts": {},
                    "columns": {},
                    "error": None
                }
                if not is_doc:
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "INFO",
                        "message": f"Tool '{n_info.get('name') or sid}' ({sid}) bypassed (container disabled)."
                    })

        active_nodes = [n for n in nodes if n["id"] not in skipped_node_ids]
        active_connections = [
            c for c in connections
            if (c.get("source") or c.get("from_node")) not in skipped_node_ids
            and (c.get("target") or c.get("to_node")) not in skipped_node_ids
        ]

        if not active_nodes:
            result.success = True
            result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "INFO", "message": "All tools bypassed or workflow has no active tools."})
            self.last_result = result
            return result

        # 1. Build and validate DAG
        try:
            dag = DAG(active_nodes, active_connections)
            execution_order = dag.topological_sort()
        except WorkflowValidationError as e:
            diag = diagnose_error(e, workflow={"nodes": active_nodes, "connections": active_connections})
            result.success = False
            result.error = diag.message
            result.diagnostic = diag.to_dict()
            result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "ERROR", "message": f"Validation error: {diag.title} - {diag.message}"})
            self.last_result = result
            return result

        # Determine execution engine: AMP (multi-threaded parallel, default) vs Classic (sequential)
        use_amp = workflow.get("use_amp_engine")
        if use_amp is None:
            use_amp = workflow.get("use_amp", True)

        max_workers_cfg = workflow.get("max_threads") or workflow.get("max_workers")
        if not max_workers_cfg or str(max_workers_cfg).lower() == "auto":
            max_workers = min(16, max(4, (os.cpu_count() or 4) * 2))
        else:
            try:
                max_workers = max(1, int(max_workers_cfg))
            except Exception:
                max_workers = min(16, max(4, (os.cpu_count() or 4) * 2))

        engine_label = f"AMP Parallel Engine ({max_workers} worker threads)" if use_amp else "Classic Engine (Sequential)"
        result.logs.append({
            "time": time.strftime("%H:%M:%S"),
            "level": "INFO",
            "message": f"Starting workflow execution with {engine_label} ({len(execution_order)} tools in pipeline)..."
        })

        # Clear prior cache
        self.data_cache.clear()

        # Identify frozen/cached/locked nodes
        cached_node_ids = set(workflow.get("cached_node_ids") or [])
        for n in active_nodes:
            if n.get("is_cached") or n.get("cached") or n.get("locked"):
                cached_node_ids.add(n["id"])

        # Auto-cache upstream nodes if enabled in workflow settings
        if workflow.get("auto_cache_upstream"):
            for c in active_connections:
                src = c.get("source") or c.get("from_node")
                if src:
                    cached_node_ids.add(src)

        # Load persisted cache for any marked nodes
        for nid in cached_node_ids:
            if nid not in self.frozen_node_cache:
                self.load_persisted_locked_node(nid)

        ready_cached_ids = {nid for nid in cached_node_ids if nid in self.frozen_node_cache}

        # Calculate skippable upstream nodes whose outputs exclusively feed ready_cached_ids
        skippable_upstream_ids = set()
        if ready_cached_ids:
            downstream_adj = {n["id"]: [] for n in active_nodes}
            for c in active_connections:
                src = c.get("source") or c.get("from_node")
                tgt = c.get("target") or c.get("to_node")
                if src in downstream_adj and tgt:
                    downstream_adj[src].append(tgt)

            for candidate in active_nodes:
                c_id = candidate["id"]
                if c_id in ready_cached_ids:
                    continue

                visited = set()
                can_escape = False

                def dfs(u: str):
                    nonlocal can_escape
                    if can_escape:
                        return
                    if u in ready_cached_ids:
                        return
                    children = downstream_adj.get(u, [])
                    if not children:
                        can_escape = True
                        return
                    for nxt in children:
                        if nxt not in visited:
                            visited.add(nxt)
                            dfs(nxt)
                            visited.remove(nxt)

                dfs(c_id)
                if not can_escape and downstream_adj.get(c_id):
                    skippable_upstream_ids.add(c_id)

        timeout = float(workflow.get("timeout") or workflow.get("execution_timeout") or 60.0)
        cancellation_token = threading.Event()
        self._active_cancellations[result.run_id] = cancellation_token

        # 2. Execute via selected engine
        if use_amp:
            self._run_amp(
                active_nodes=active_nodes,
                dag=dag,
                node_map=node_map,
                current_run_cache=current_run_cache,
                cached_node_ids=cached_node_ids,
                ready_cached_ids=ready_cached_ids,
                skippable_upstream_ids=skippable_upstream_ids,
                timeout=timeout,
                start_time=start_time,
                cancellation_token=cancellation_token,
                result=result,
                observer_cb=observer_cb,
                workflow=workflow,
                max_workers=max_workers
            )
        else:
            self._run_sequential(
                execution_order=execution_order,
                active_nodes=active_nodes,
                dag=dag,
                node_map=node_map,
                current_run_cache=current_run_cache,
                cached_node_ids=cached_node_ids,
                ready_cached_ids=ready_cached_ids,
                skippable_upstream_ids=skippable_upstream_ids,
                timeout=timeout,
                start_time=start_time,
                cancellation_token=cancellation_token,
                result=result,
                observer_cb=observer_cb,
                workflow=workflow
            )

        self._active_cancellations.pop(result.run_id, None)
        result.total_duration_ms = (time.time() - start_time) * 1000.0
        if result.success:
            result.logs.append({
                "time": time.strftime("%H:%M:%S"),
                "level": "INFO",
                "message": f"Workflow execution finished successfully in {result.total_duration_ms:.1f}ms."
            })
        else:
            result.logs.append({
                "time": time.strftime("%H:%M:%S"),
                "level": "ERROR",
                "message": f"Workflow finished with errors in {result.total_duration_ms:.1f}ms."
            })

        if observer_cb:
            try:
                observer_cb({
                    "event": "workflow_completed",
                    "run_id": result.run_id,
                    "session_id": result.session_id,
                    "success": result.success,
                    "total_duration_ms": round(result.total_duration_ms, 2),
                    "node_results": result.node_results,
                    "logs": result.logs,
                    "error": result.error,
                    "diagnostic": result.diagnostic
                })
            except Exception:
                pass

        self.cache_manager.store_run_data(result.run_id, current_run_cache, result)
        self.last_result = result
        return result

    def run_node(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        force_rerun: bool = True,
        observer_cb: Optional[Any] = None
    ) -> ExecutionResult:
        """
        Executes a single target node and any necessary uncached upstream dependencies.
        Downstream nodes are skipped.
        If the target node is marked locked/cached, its frozen cache and persistent storage
        are updated with the fresh output.
        """
        nodes = workflow.get("nodes", [])
        connections = workflow.get("connections", [])
        node_map = {n["id"]: n for n in nodes}

        actual_session_id = session_id or workflow.get("session_id")
        actual_run_id = run_id or workflow.get("run_id") or f"run_node_{uuid.uuid4().hex[:8]}"
        run_entry = self.cache_manager.create_run(
            session_id=actual_session_id,
            workflow_name=workflow.get("name", ""),
            run_id=actual_run_id
        )
        current_run_cache = run_entry.data_cache
        result = ExecutionResult(run_id=run_entry.run_id, session_id=run_entry.session_id)
        start_time = time.time()

        if node_id not in node_map:
            result.success = False
            result.error = f"Node '{node_id}' does not exist in workflow."
            result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "ERROR", "message": result.error})
            self.last_result = result
            return result

        # Build DAG for lineage
        try:
            dag = DAG(nodes, connections)
            subgraph_order = dag.get_subgraph_order(node_id)
        except Exception as e:
            result.success = False
            result.error = f"Lineage validation error: {str(e)}"
            result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "ERROR", "message": result.error})
            self.last_result = result
            return result

        target_name = node_map[node_id].get("name") or node_map[node_id].get("type") or node_id
        result.logs.append({
            "time": time.strftime("%H:%M:%S"),
            "level": "INFO",
            "message": f"Executing tool '{target_name}' standalone ({len(subgraph_order)} tools in lineage)..."
        })

        for nid in subgraph_order:
            node_data = node_map[nid]
            node_type = node_data.get("type")
            node_name = node_data.get("name") or node_type
            node_config = node_data.get("config", {})

            # For upstream ancestors (nid != node_id):
            if nid != node_id:
                # 1. Check if already cached in current run / local cache / frozen cache / persistent disk
                if nid in current_run_cache:
                    continue
                if nid in self._local_data_cache:
                    current_run_cache[nid] = self._local_data_cache[nid]
                    continue
                if nid in self.frozen_node_cache:
                    current_run_cache[nid] = self.frozen_node_cache[nid]
                    self._local_data_cache[nid] = self.frozen_node_cache[nid]
                    continue
                persisted = self.load_persisted_locked_node(nid)
                if persisted:
                    current_run_cache[nid] = persisted
                    self._local_data_cache[nid] = persisted
                    continue

            # Need to execute node `nid` (either ancestor that isn't cached, or target `node_id`):
            if node_type not in NODE_REGISTRY:
                result.success = False
                result.error = f"Unknown node type: '{node_type}'"
                result.node_results[nid] = {
                    "id": nid, "type": node_type, "name": node_name,
                    "status": "error", "error": result.error, "duration_ms": 0.0,
                    "record_counts": {}, "columns": {}
                }
                result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "ERROR", "message": f"Tool '{node_name}' ({nid}): {result.error}"})
                break

            # Gather incoming inputs
            incoming_edges = dag.get_input_edges(nid)
            inputs: Dict[str, Any] = {}
            missing_upstream = False
            for edge in incoming_edges:
                src_id = edge.get("source") or edge.get("from_node")
                src_port = edge.get("sourceHandle") or edge.get("from_port") or "O"
                tgt_port = edge.get("targetHandle") or edge.get("to_port") or "I"

                src_cache = current_run_cache.get(src_id) if current_run_cache else self.data_cache.get(src_id)
                if src_cache is None or src_port not in src_cache:
                    missing_upstream = True
                    break

                source_df = src_cache[src_port]
                if node_type in ("union", "join_multiple", "multi_join"):
                    if tgt_port not in inputs:
                        inputs[tgt_port] = []
                    inputs[tgt_port].append(source_df)
                else:
                    inputs[tgt_port] = source_df

            if missing_upstream and incoming_edges:
                result.success = False
                result.error = f"Upstream dependency for '{node_name}' missing output."
                result.node_results[nid] = {
                    "id": nid, "type": node_type, "name": node_name,
                    "status": "skipped", "error": result.error, "duration_ms": 0.0,
                    "record_counts": {}, "columns": {}
                }
                result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "WARNING", "message": result.error})
                break

            # Execute node
            node_cls = NODE_REGISTRY[node_type]
            node_instance = node_cls(nid, node_config)
            node_start = time.time()
            try:
                outputs = node_instance.execute(inputs, self.context)
                duration = (time.time() - node_start) * 1000.0

                sanitized_outputs = {}
                record_counts = {}
                columns = {}
                column_meta = {}

                for port, df in outputs.items():
                    if isinstance(df, pd.DataFrame):
                        clean_df = sanitize_dataframe(df)
                        sanitized_outputs[port] = clean_df
                        record_counts[port] = len(clean_df)
                        columns[port] = list(clean_df.columns)
                        col_sources = getattr(clean_df, "attrs", {}).get("column_sources", {})
                        meta_list = []
                        for col in clean_df.columns:
                            s = clean_df[col]
                            alteryx_t = infer_alteryx_type(s)
                            ctype = map_alteryx_to_category(alteryx_t)
                            item = {"name": str(col), "type": ctype, "alteryx_type": alteryx_t, "dtype": alteryx_t}
                            if col in col_sources:
                                item["source"] = col_sources[col]
                            meta_list.append(item)
                        column_meta[port] = meta_list
                    else:
                        sanitized_outputs[port] = df
                        record_counts[port] = 0
                        columns[port] = []
                        column_meta[port] = []

                current_run_cache[nid] = sanitized_outputs
                self._local_data_cache[nid] = sanitized_outputs

                # If this is the target node, or if it is marked cached/locked, update frozen cache & persist
                is_node_locked = (
                    node_data.get("is_cached")
                    or node_data.get("locked")
                    or node_data.get("cached")
                    or nid in set(workflow.get("cached_node_ids") or [])
                )
                if is_node_locked:
                    self.frozen_node_cache[nid] = sanitized_outputs
                    self.persist_locked_node(nid, sanitized_outputs)
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "INFO",
                        "message": f"Tool '{node_name}' ({nid}) output saved to locked cache."
                    })

                node_res = {
                    "id": nid,
                    "type": node_type,
                    "name": node_name,
                    "status": "success",
                    "duration_ms": round(duration, 2),
                    "record_counts": record_counts,
                    "columns": columns,
                    "column_meta": column_meta,
                    "error": None
                }

                if hasattr(node_instance, "messages") and node_instance.messages:
                    node_res["messages"] = node_instance.messages
                    for msg in node_instance.messages:
                        result.logs.append({
                            "time": time.strftime("%H:%M:%S"),
                            "level": "INFO",
                            "message": f"Tool '{node_name}': {msg}"
                        })

                result.node_results[nid] = node_res

                if observer_cb:
                    try:
                        observer_cb({
                            "event": "node_completed",
                            "run_id": result.run_id,
                            "node_id": nid,
                            "node_name": node_name,
                            "name": node_name,
                            "node_type": node_type,
                            "type": node_type,
                            "status": "success",
                            "duration_ms": round(duration, 2),
                            "record_counts": record_counts,
                            "columns": columns,
                            "column_meta": column_meta
                        })
                    except Exception:
                        pass

            except Exception as e:
                duration = (time.time() - node_start) * 1000.0
                result.success = False
                result.error = str(e)
                diag = diagnose_error(e, node={"id": nid, "name": node_name, "type": node_type, "config": node_config})
                result.diagnostic = diag.to_dict()
                result.node_results[nid] = {
                    "id": nid,
                    "type": node_type,
                    "name": node_name,
                    "status": "error",
                    "duration_ms": round(duration, 2),
                    "record_counts": {},
                    "columns": {},
                    "error": str(e),
                    "diagnostic": diag.to_dict()
                }
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "ERROR",
                    "message": f"Tool '{node_name}' ({nid}) failed: {str(e)}"
                })
                break

        result.total_duration_ms = (time.time() - start_time) * 1000.0
        if result.success:
            result.logs.append({
                "time": time.strftime("%H:%M:%S"),
                "level": "INFO",
                "message": f"Tool standalone execution finished successfully in {result.total_duration_ms:.1f}ms."
            })
        self.cache_manager.store_run_data(result.run_id, current_run_cache, result)
        self.last_result = result
        return result

    def _run_amp(
        self,
        active_nodes: List[Dict[str, Any]],
        dag: DAG,
        node_map: Dict[str, Any],
        current_run_cache: Dict[str, Dict[str, pd.DataFrame]],
        cached_node_ids: Set[str],
        ready_cached_ids: Set[str],
        skippable_upstream_ids: Set[str],
        timeout: float,
        start_time: float,
        cancellation_token: threading.Event,
        result: ExecutionResult,
        observer_cb: Optional[Any],
        workflow: Dict[str, Any],
        max_workers: int
    ):
        """
        AMP (Alteryx Multi-threaded Processing) Parallel Engine.
        Executes independent tools and multiple input sources concurrently on worker threads.
        Nodes are dynamically scheduled as soon as all upstream dependencies are satisfied.
        """
        lock = threading.Lock()
        cv = threading.Condition(lock)

        active_ids = {n["id"] for n in active_nodes}
        pending_deps = {nid: set(dag.predecessors.get(nid, set())) for nid in active_ids}
        remaining_consumers: Dict[str, int] = {nid: len(dag.successors.get(nid, set())) for nid in active_ids}
        completed_nodes: Set[str] = set()
        failed_nodes: Set[str] = set()
        running_nodes: Set[str] = set()
        has_error = threading.Event()
        timed_out = threading.Event()

        def _on_node_success(node_id: str):
            # Must be called with lock held
            running_nodes.discard(node_id)
            completed_nodes.add(node_id)

            # Check all downstream successors
            for child in dag.successors.get(node_id, set()):
                if child in pending_deps:
                    pending_deps[child].discard(node_id)
                    if len(pending_deps[child]) == 0 and child not in running_nodes and child not in completed_nodes and child not in failed_nodes:
                        if not has_error.is_set() and not cancellation_token.is_set() and not timed_out.is_set():
                            running_nodes.add(child)
                            pool.submit(worker, child)

            cv.notify_all()

        def _on_node_failure(node_id: str, err_msg: str, diag_dict: Optional[dict]):
            # Must be called with lock held
            running_nodes.discard(node_id)
            failed_nodes.add(node_id)
            has_error.set()
            cv.notify_all()

        def worker(node_id: str):
            if cancellation_token.is_set() or has_error.is_set() or timed_out.is_set():
                with lock:
                    running_nodes.discard(node_id)
                    cv.notify_all()
                return

            if time.time() - start_time > timeout:
                with lock:
                    timed_out.set()
                    running_nodes.discard(node_id)
                    cv.notify_all()
                return

            node_data = node_map[node_id]
            node_type = node_data.get("type")
            node_name = node_data.get("name") or node_type
            node_config = node_data.get("config", {})

            # 1. Skippable upstream
            if node_id in skippable_upstream_ids:
                with lock:
                    node_res = {
                        "id": node_id,
                        "type": node_type,
                        "name": node_name,
                        "status": "success",
                        "duration_ms": 0.0,
                        "record_counts": {},
                        "columns": {},
                        "error": None
                    }
                    result.node_results[node_id] = node_res
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "INFO",
                        "message": f"Tool '{node_name}' ({node_id}) skipped (upstream of frozen node)."
                    })
                    if observer_cb:
                        try:
                            observer_cb({
                                "event": "node_completed",
                                "run_id": result.run_id,
                                "node_id": node_id,
                                "node_name": node_name,
                                "name": node_name,
                                "node_type": node_type,
                                "type": node_type,
                                "status": "success",
                                "duration_ms": 0.0,
                                "record_counts": {},
                                "columns": {}
                            })
                        except Exception:
                            pass
                    _on_node_success(node_id)
                return

            # 2. Ready in frozen cache
            if node_id in ready_cached_ids:
                with lock:
                    cached_outs = self.frozen_node_cache[node_id]
                    current_run_cache[node_id] = cached_outs
                    self._local_data_cache[node_id] = cached_outs
                    node_res = {
                        "id": node_id,
                        "type": node_type,
                        "name": node_name,
                        "status": "success",
                        "duration_ms": 0.0,
                        "record_counts": {p: len(df) for p, df in cached_outs.items()},
                        "columns": {p: [str(c) for c in df.columns] for p, df in cached_outs.items()},
                        "error": None
                    }
                    result.node_results[node_id] = node_res
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "INFO",
                        "message": f"Tool '{node_name}' ({node_id}) loaded from frozen cache (0ms)."
                    })
                    if observer_cb:
                        try:
                            observer_cb({
                                "event": "node_completed",
                                "run_id": result.run_id,
                                "node_id": node_id,
                                "node_name": node_name,
                                "name": node_name,
                                "node_type": node_type,
                                "type": node_type,
                                "status": "success",
                                "duration_ms": 0.0,
                                "record_counts": node_res["record_counts"],
                                "columns": node_res["columns"]
                            })
                        except Exception:
                            pass
                    _on_node_success(node_id)
                return

            # 3. Unknown node type check
            if node_type not in NODE_REGISTRY:
                with lock:
                    node_res = {
                        "id": node_id,
                        "type": node_type,
                        "name": node_name,
                        "status": "error",
                        "duration_ms": 0.0,
                        "record_counts": {},
                        "columns": {},
                        "error": f"Unknown node type: '{node_type}'"
                    }
                    result.success = False
                    result.node_results[node_id] = node_res
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "ERROR",
                        "message": f"Tool '{node_name}' ({node_id}): Unknown node type."
                    })
                    _on_node_failure(node_id, f"Unknown node type: '{node_type}'", None)
                return

            # 4. Gather incoming inputs safely
            with lock:
                incoming_edges = dag.get_input_edges(node_id)
                inputs: Dict[str, Any] = {}
                missing_upstream = False
                for edge in incoming_edges:
                    src_id = edge.get("source") or edge.get("from_node")
                    src_port = edge.get("sourceHandle") or edge.get("from_port") or "O"
                    tgt_port = edge.get("targetHandle") or edge.get("to_port") or "I"
                    src_cache = current_run_cache.get(src_id) if current_run_cache else self.data_cache.get(src_id)
                    if src_cache is None or src_port not in src_cache:
                        missing_upstream = True
                        break
                    source_df = src_cache[src_port]
                    if node_type in ("union", "join_multiple", "multi_join"):
                        if tgt_port not in inputs:
                            inputs[tgt_port] = []
                        inputs[tgt_port].append(source_df)
                    else:
                        inputs[tgt_port] = source_df

                if not missing_upstream:
                    for edge in incoming_edges:
                        src_id = edge.get("source") or edge.get("from_node")
                        if src_id in remaining_consumers:
                            remaining_consumers[src_id] -= 1
                            if remaining_consumers[src_id] <= 0:
                                if hasattr(current_run_cache, "evict_from_memory"):
                                    current_run_cache.evict_from_memory(src_id)
                                if hasattr(self._local_data_cache, "evict_from_memory"):
                                    self._local_data_cache.evict_from_memory(src_id)

                if missing_upstream:
                    # An upstream dependency failed or was cancelled
                    with lock:
                        node_res = {
                            "id": node_id,
                            "type": node_type,
                            "name": node_name,
                            "status": "skipped",
                            "duration_ms": 0.0,
                            "record_counts": {},
                            "columns": {},
                            "error": "Upstream dependency failed or cancelled."
                        }
                        result.node_results[node_id] = node_res
                        _on_node_failure(node_id, "Upstream dependency failed or cancelled.", None)
                    return

                if observer_cb:
                    try:
                        observer_cb({
                            "event": "node_started",
                            "run_id": result.run_id,
                            "node_id": node_id,
                            "node_name": node_name,
                            "name": node_name,
                            "node_type": node_type,
                            "type": node_type
                        })
                    except Exception:
                        pass

            # 5. Execute node OUTSIDE lock (Parallel Execution Across Threads)
            node_cls = NODE_REGISTRY[node_type]
            node_instance = node_cls(node_id, node_config)
            node_start = time.time()
            try:
                outputs = node_instance.execute(inputs, self.context)
                duration = (time.time() - node_start) * 1000.0

                sanitized_outputs = {}
                record_counts = {}
                columns = {}
                column_meta = {}

                for port, df in outputs.items():
                    if isinstance(df, pd.DataFrame):
                        clean_df = sanitize_dataframe(df)
                        sanitized_outputs[port] = clean_df
                        record_counts[port] = len(clean_df)
                        columns[port] = list(clean_df.columns)
                        col_sources = getattr(clean_df, "attrs", {}).get("column_sources", {})
                        meta_list = []
                        for col in clean_df.columns:
                            s = clean_df[col]
                            alteryx_t = infer_alteryx_type(s)
                            ctype = map_alteryx_to_category(alteryx_t)
                            item = {
                                "name": str(col),
                                "type": ctype,
                                "alteryx_type": alteryx_t,
                                "dtype": alteryx_t
                            }
                            if col in col_sources:
                                item["source"] = col_sources[col]
                            meta_list.append(item)
                        column_meta[port] = meta_list
                    else:
                        sanitized_outputs[port] = df
                        record_counts[port] = 0
                        columns[port] = []
                        column_meta[port] = []

                node_res = {
                    "id": node_id,
                    "type": node_type,
                    "name": node_name,
                    "status": "success",
                    "duration_ms": round(duration, 2),
                    "record_counts": record_counts,
                    "columns": columns,
                    "column_meta": column_meta,
                    "error": None
                }

                # 6. Store outputs & notify successors under lock
                with lock:
                    current_run_cache[node_id] = sanitized_outputs
                    self._local_data_cache[node_id] = sanitized_outputs
                    if node_id in cached_node_ids:
                        self.frozen_node_cache[node_id] = sanitized_outputs
                        self.persist_locked_node(node_id, sanitized_outputs)
                        result.logs.append({
                            "time": time.strftime("%H:%M:%S"),
                            "level": "INFO",
                            "message": f"Tool '{node_name}' ({node_id}) outputs saved to frozen cache."
                        })
                    result.node_results[node_id] = node_res

                    if observer_cb:
                        try:
                            observer_cb({
                                "event": "node_completed",
                                "run_id": result.run_id,
                                "node_id": node_id,
                                "node_name": node_name,
                                "name": node_name,
                                "node_type": node_type,
                                "type": node_type,
                                "status": "success",
                                "duration_ms": round(duration, 2),
                                "record_counts": record_counts,
                                "columns": columns,
                                "column_meta": column_meta
                            })
                        except Exception:
                            pass

                    if hasattr(node_instance, "written_files") and node_instance.written_files:
                        node_res["written_files"] = node_instance.written_files
                        files_str = ", ".join([f"{f['filename']} ({f.get('records', 0):,} records)" for f in node_instance.written_files])
                        result.logs.append({
                            "time": time.strftime("%H:%M:%S"),
                            "level": "SUCCESS",
                            "message": f"Tool '{node_name}' wrote file(s): {files_str}"
                        })

                    if hasattr(node_instance, "messages") and node_instance.messages:
                        node_res["messages"] = node_instance.messages
                        for msg in node_instance.messages:
                            result.logs.append({
                                "time": time.strftime("%H:%M:%S"),
                                "level": "INFO",
                                "message": f"Tool '{node_name}': {msg}"
                            })

                    count_summary = ", ".join([f"[{port}]: {cnt:,} records" for port, cnt in record_counts.items()])
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "SUCCESS",
                        "message": f"Tool '{node_name}' completed in {duration:.1f}ms ({count_summary})"
                    })

                    _on_node_success(node_id)

            except Exception as e:
                duration = (time.time() - node_start) * 1000.0
                incoming_cols = []
                for p_name, in_df in inputs.items():
                    if isinstance(in_df, pd.DataFrame):
                        incoming_cols.extend(list(in_df.columns))
                    elif isinstance(in_df, list):
                        for sub_df in in_df:
                            if isinstance(sub_df, pd.DataFrame):
                                incoming_cols.extend(list(sub_df.columns))
                incoming_cols = list(dict.fromkeys(incoming_cols))

                diag = diagnose_error(e, node=node_data, incoming_columns=incoming_cols, workflow=workflow)

                node_res = {
                    "id": node_id,
                    "type": node_type,
                    "name": node_name,
                    "status": "error",
                    "duration_ms": round(duration, 2),
                    "record_counts": {},
                    "columns": {},
                    "error": diag.message,
                    "diagnostic": diag.to_dict()
                }

                with lock:
                    result.node_results[node_id] = node_res
                    result.success = False
                    result.error = f"{diag.title}: {diag.message}"
                    result.diagnostic = diag.to_dict()

                    if observer_cb:
                        try:
                            observer_cb({
                                "event": "node_error",
                                "run_id": result.run_id,
                                "node_id": node_id,
                                "node_name": node_name,
                                "name": node_name,
                                "node_type": node_type,
                                "type": node_type,
                                "status": "error",
                                "error": diag.message,
                                "diagnostic": diag.to_dict()
                            })
                        except Exception:
                            pass
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "ERROR",
                        "message": f"[{diag.error_code}] {diag.title} - {diag.message}"
                    })

                    _on_node_failure(node_id, diag.message, diag.to_dict())

        # Start thread pool and submit initial ready nodes (e.g. multiple input tools)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        try:
            with lock:
                for nid in active_ids:
                    if len(pending_deps[nid]) == 0:
                        running_nodes.add(nid)
                        pool.submit(worker, nid)

            # Master coordination loop
            while True:
                with lock:
                    if cancellation_token.is_set():
                        result.success = False
                        result.error = "Workflow execution cancelled by user."
                        result.logs.append({
                            "time": time.strftime("%H:%M:%S"),
                            "level": "WARNING",
                            "message": "Workflow execution cancelled by user."
                        })
                        if observer_cb:
                            try:
                                observer_cb({
                                    "event": "workflow_cancelled",
                                    "run_id": result.run_id,
                                    "session_id": result.session_id,
                                    "message": "Workflow execution cancelled by user."
                                })
                            except Exception:
                                pass
                        break

                    if timed_out.is_set() or (time.time() - start_time > timeout):
                        result.success = False
                        timeout_msg = f"Workflow execution timed out after {int(timeout)}s limit."
                        result.error = timeout_msg
                        result.logs.append({
                            "time": time.strftime("%H:%M:%S"),
                            "level": "ERROR",
                            "message": timeout_msg
                        })
                        if observer_cb:
                            try:
                                observer_cb({
                                    "event": "workflow_cancelled",
                                    "run_id": result.run_id,
                                    "session_id": result.session_id,
                                    "message": timeout_msg
                                })
                            except Exception:
                                pass
                        break

                    if has_error.is_set():
                        break

                    if len(completed_nodes) + len(failed_nodes) >= len(active_ids):
                        break

                    cv.wait(timeout=0.2)

        finally:
            pool.shutdown(wait=True, cancel_futures=True)

        # Mark un-run nodes as skipped if run aborted
        with lock:
            if not result.success:
                for nid in active_ids:
                    if nid not in result.node_results:
                        n_info = node_map.get(nid, {})
                        result.node_results[nid] = {
                            "id": nid,
                            "type": n_info.get("type"),
                            "name": n_info.get("name") or n_info.get("type"),
                            "status": "skipped",
                            "duration_ms": 0.0,
                            "record_counts": {},
                            "columns": {},
                            "error": "Execution stopped before tool could run."
                        }

    def _run_sequential(
        self,
        execution_order: List[str],
        active_nodes: List[Dict[str, Any]],
        dag: DAG,
        node_map: Dict[str, Any],
        current_run_cache: Dict[str, Dict[str, pd.DataFrame]],
        cached_node_ids: Set[str],
        ready_cached_ids: Set[str],
        skippable_upstream_ids: Set[str],
        timeout: float,
        start_time: float,
        cancellation_token: threading.Event,
        result: ExecutionResult,
        observer_cb: Optional[Any],
        workflow: Dict[str, Any]
    ):
        """
        Original Engine (Classic Single-Threaded Sequential).
        Executes tools one-by-one in topological order for deterministic legacy compatibility.
        """
        active_ids = {n["id"] for n in active_nodes}
        remaining_consumers: Dict[str, int] = {nid: len(dag.successors.get(nid, set())) for nid in active_ids}
        for node_id in execution_order:
            if cancellation_token.is_set():
                result.success = False
                result.error = "Workflow execution cancelled by user."
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "WARNING",
                    "message": "Workflow execution cancelled by user."
                })
                if observer_cb:
                    try:
                        observer_cb({
                            "event": "workflow_cancelled",
                            "run_id": result.run_id,
                            "session_id": result.session_id,
                            "message": "Workflow execution cancelled by user."
                        })
                    except Exception:
                        pass
                break

            # Execution timeout safety limit check
            if time.time() - start_time > timeout:
                result.success = False
                timeout_msg = f"Workflow execution timed out after {int(timeout)}s limit."
                result.error = timeout_msg
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "ERROR",
                    "message": timeout_msg
                })
                if observer_cb:
                    try:
                        observer_cb({
                            "event": "workflow_cancelled",
                            "run_id": result.run_id,
                            "session_id": result.session_id,
                            "message": timeout_msg
                        })
                    except Exception:
                        pass
                break

            node_data = node_map[node_id]
            node_type = node_data.get("type")
            node_name = node_data.get("name") or node_type
            node_config = node_data.get("config", {})

            node_res = {
                "id": node_id,
                "type": node_type,
                "name": node_name,
                "status": "pending",
                "duration_ms": 0.0,
                "record_counts": {},
                "columns": {},
                "error": None
            }

            if node_id in skippable_upstream_ids:
                node_res["status"] = "success"
                node_res["duration_ms"] = 0.0
                result.node_results[node_id] = node_res
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "INFO",
                    "message": f"Tool '{node_name}' ({node_id}) skipped (upstream of frozen node)."
                })
                if observer_cb:
                    try:
                        observer_cb({
                            "event": "node_completed",
                            "run_id": result.run_id,
                            "node_id": node_id,
                            "node_name": node_name,
                            "name": node_name,
                            "node_type": node_type,
                            "type": node_type,
                            "status": "success",
                            "duration_ms": 0.0,
                            "record_counts": {},
                            "columns": {}
                        })
                    except Exception:
                        pass
                continue

            if node_id in ready_cached_ids:
                cached_outs = self.frozen_node_cache[node_id]
                current_run_cache[node_id] = cached_outs
                self._local_data_cache[node_id] = cached_outs
                node_res["status"] = "success"
                node_res["duration_ms"] = 0.0
                for p, df in cached_outs.items():
                    node_res["record_counts"][p] = len(df)
                    node_res["columns"][p] = [str(col) for col in df.columns]
                result.node_results[node_id] = node_res
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "INFO",
                    "message": f"Tool '{node_name}' ({node_id}) loaded from frozen cache (0ms)."
                })
                if observer_cb:
                    try:
                        observer_cb({
                            "event": "node_completed",
                            "run_id": result.run_id,
                            "node_id": node_id,
                            "node_name": node_name,
                            "name": node_name,
                            "node_type": node_type,
                            "type": node_type,
                            "status": "success",
                            "duration_ms": 0.0,
                            "record_counts": node_res["record_counts"],
                            "columns": node_res["columns"]
                        })
                    except Exception:
                        pass
                continue

            if node_type not in NODE_REGISTRY:
                node_res["status"] = "error"
                node_res["error"] = f"Unknown node type: '{node_type}'"
                result.success = False
                result.node_results[node_id] = node_res
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "ERROR",
                    "message": f"Tool '{node_name}' ({node_id}): Unknown node type."
                })
                break

            # Gather incoming inputs
            incoming_edges = dag.get_input_edges(node_id)
            inputs: Dict[str, Any] = {}

            missing_upstream = False
            for edge in incoming_edges:
                src_id = edge.get("source") or edge.get("from_node")
                src_port = edge.get("sourceHandle") or edge.get("from_port") or "O"
                tgt_port = edge.get("targetHandle") or edge.get("to_port") or "I"

                src_cache = current_run_cache.get(src_id) if current_run_cache else self.data_cache.get(src_id)
                if src_cache is None or src_port not in src_cache:
                    missing_upstream = True
                    break

                source_df = src_cache[src_port]
                if node_type in ("union", "join_multiple", "multi_join"):
                    if tgt_port not in inputs:
                        inputs[tgt_port] = []
                    inputs[tgt_port].append(source_df)
                else:
                    inputs[tgt_port] = source_df

            if not missing_upstream:
                for edge in incoming_edges:
                    src_id = edge.get("source") or edge.get("from_node")
                    if src_id in remaining_consumers:
                        remaining_consumers[src_id] -= 1
                        if remaining_consumers[src_id] <= 0:
                            if hasattr(current_run_cache, "evict_from_memory"):
                                current_run_cache.evict_from_memory(src_id)
                            if hasattr(self._local_data_cache, "evict_from_memory"):
                                self._local_data_cache.evict_from_memory(src_id)

            if missing_upstream:
                node_res["status"] = "skipped"
                node_res["error"] = "Upstream dependency failed or did not provide output."
                result.node_results[node_id] = node_res
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "WARNING",
                    "message": f"Tool '{node_name}' skipped due to upstream failure."
                })
                continue

            if observer_cb:
                try:
                    observer_cb({
                        "event": "node_started",
                        "run_id": result.run_id,
                        "node_id": node_id,
                        "node_name": node_name,
                        "name": node_name,
                        "node_type": node_type,
                        "type": node_type
                    })
                except Exception:
                    pass

            # Execute node
            node_cls = NODE_REGISTRY[node_type]
            node_instance = node_cls(node_id, node_config)

            node_start = time.time()
            try:
                outputs = node_instance.execute(inputs, self.context)
                duration = (time.time() - node_start) * 1000.0

                # Cache sanitized outputs and collect metadata
                sanitized_outputs = {}
                for port, df in outputs.items():
                    if isinstance(df, pd.DataFrame):
                        clean_df = sanitize_dataframe(df)
                        sanitized_outputs[port] = clean_df
                        node_res["record_counts"][port] = len(clean_df)
                        node_res["columns"][port] = list(clean_df.columns)
                        if "column_meta" not in node_res:
                            node_res["column_meta"] = {}
                        col_sources = getattr(clean_df, "attrs", {}).get("column_sources", {})
                        meta_list = []
                        for col in clean_df.columns:
                            s = clean_df[col]
                            alteryx_t = infer_alteryx_type(s)
                            ctype = map_alteryx_to_category(alteryx_t)
                            item = {
                                "name": str(col),
                                "type": ctype,
                                "alteryx_type": alteryx_t,
                                "dtype": alteryx_t
                            }
                            if col in col_sources:
                                item["source"] = col_sources[col]
                            meta_list.append(item)
                        node_res["column_meta"][port] = meta_list
                    else:
                        sanitized_outputs[port] = df
                        node_res["record_counts"][port] = 0
                        node_res["columns"][port] = []
                        if "column_meta" not in node_res:
                            node_res["column_meta"] = {}
                        node_res["column_meta"][port] = []

                current_run_cache[node_id] = sanitized_outputs
                self._local_data_cache[node_id] = sanitized_outputs
                if node_id in cached_node_ids:
                    self.frozen_node_cache[node_id] = sanitized_outputs
                    self.persist_locked_node(node_id, sanitized_outputs)
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "INFO",
                        "message": f"Tool '{node_name}' ({node_id}) outputs saved to frozen cache."
                    })
                node_res["status"] = "success"
                node_res["duration_ms"] = round(duration, 2)

                result.node_results[node_id] = node_res

                if observer_cb:
                    try:
                        observer_cb({
                            "event": "node_completed",
                            "run_id": result.run_id,
                            "node_id": node_id,
                            "node_name": node_name,
                            "name": node_name,
                            "node_type": node_type,
                            "type": node_type,
                            "status": "success",
                            "duration_ms": round(duration, 2),
                            "record_counts": node_res["record_counts"],
                            "columns": node_res["columns"],
                            "column_meta": node_res.get("column_meta", {})
                        })
                    except Exception:
                        pass

                if hasattr(node_instance, "written_files") and node_instance.written_files:
                    node_res["written_files"] = node_instance.written_files
                    files_str = ", ".join([f"{f['filename']} ({f.get('records', 0):,} records)" for f in node_instance.written_files])
                    result.logs.append({
                        "time": time.strftime("%H:%M:%S"),
                        "level": "SUCCESS",
                        "message": f"Tool '{node_name}' wrote file(s): {files_str}"
                    })

                if hasattr(node_instance, "messages") and node_instance.messages:
                    node_res["messages"] = node_instance.messages
                    for msg in node_instance.messages:
                        result.logs.append({
                            "time": time.strftime("%H:%M:%S"),
                            "level": "INFO",
                            "message": f"Tool '{node_name}': {msg}"
                        })

                count_summary = ", ".join([f"[{port}]: {cnt:,} records" for port, cnt in node_res["record_counts"].items()])
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "SUCCESS",
                    "message": f"Tool '{node_name}' completed in {duration:.1f}ms ({count_summary})"
                })

            except Exception as e:
                duration = (time.time() - node_start) * 1000.0

                # Extract available incoming column names
                incoming_cols = []
                for p_name, in_df in inputs.items():
                    if isinstance(in_df, pd.DataFrame):
                        incoming_cols.extend(list(in_df.columns))
                    elif isinstance(in_df, list):
                        for sub_df in in_df:
                            if isinstance(sub_df, pd.DataFrame):
                                incoming_cols.extend(list(sub_df.columns))
                incoming_cols = list(dict.fromkeys(incoming_cols))

                diag = diagnose_error(e, node=node_data, incoming_columns=incoming_cols, workflow=workflow)

                node_res["status"] = "error"
                node_res["duration_ms"] = round(duration, 2)
                node_res["error"] = diag.message
                node_res["diagnostic"] = diag.to_dict()
                result.node_results[node_id] = node_res
                result.success = False
                result.error = f"{diag.title}: {diag.message}"
                result.diagnostic = diag.to_dict()

                if observer_cb:
                    try:
                        observer_cb({
                            "event": "node_error",
                            "run_id": result.run_id,
                            "node_id": node_id,
                            "node_name": node_name,
                            "name": node_name,
                            "node_type": node_type,
                            "type": node_type,
                            "status": "error",
                            "error": diag.message,
                            "diagnostic": diag.to_dict()
                        })
                    except Exception:
                        pass
                result.logs.append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "ERROR",
                    "message": f"[{diag.error_code}] {diag.title} - {diag.message}"
                })
                break


    def get_node_data(
        self,
        node_id: str,
        port: str = "O",
        page: int = 1,
        page_size: int = 100,
        search: str = "",
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        sample_mode: str = "page"
    ) -> Dict[str, Any]:
        """
        Returns paginated or sampled records and metadata for a specific node and output port.
        Supports sample_mode: 'page' (default), 'random', or 'head'.
        """
        run_entry = self.cache_manager.get_run(run_id=run_id, session_id=session_id)
        effective_cache = run_entry.data_cache if run_entry else self.data_cache
        node_cache = effective_cache.get(node_id)
        if not node_cache or port not in node_cache:
            if node_id in self.frozen_node_cache:
                node_cache = self.frozen_node_cache.get(node_id)
            else:
                persisted = self.load_persisted_locked_node(node_id)
                if persisted:
                    node_cache = persisted

        if not node_cache or port not in node_cache:
            return {
                "available": False,
                "message": f"No data cached for node '{node_id}' output port '{port}'."
            }

        df = node_cache[port]
        if not isinstance(df, pd.DataFrame):
            return {"available": False, "message": "Result is not tabular data."}

        # Ensure columns are unique strings before processing
        df = sanitize_dataframe(df)

        # Cap page_size to a safe maximum to protect browser and worker memory
        page_size = min(max(1, page_size), 1000)

        # Memory footprint
        from backend.engine.profiler import format_bytes
        try:
            mem_bytes = int(df.memory_usage(deep=True).sum()) if len(df) > 0 else 0
        except Exception:
            mem_bytes = 0
        mem_formatted = format_bytes(mem_bytes)

        # Optional search filtering (Vectorized column search)
        filtered_df = df
        if search.strip():
            s = search.strip().lower()
            masks = []
            for c in df.columns:
                series = df[c]
                try:
                    if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                        masks.append(series.astype(str).str.lower().str.contains(s, regex=False, na=False))
                    elif pd.api.types.is_numeric_dtype(series):
                        masks.append(series.astype(str).str.contains(s, regex=False, na=False))
                except Exception:
                    pass
            if masks:
                mask = np.logical_or.reduce(masks)
                filtered_df = df[mask]
            else:
                filtered_df = df.iloc[0:0]

        total_records = len(filtered_df)
        total_pages = max(1, math.ceil(total_records / page_size)) if page_size > 0 else 1
        page = max(1, min(page, total_pages))

        # Apply sample_mode
        normalized_mode = sample_mode.lower().strip() if isinstance(sample_mode, str) else "page"
        if normalized_mode == "random" and total_records > page_size:
            page_df = filtered_df.sample(n=min(page_size, total_records), random_state=42)
            actual_sample_mode = "random"
        elif normalized_mode == "head" or normalized_mode == "first":
            page_df = filtered_df.head(page_size)
            actual_sample_mode = "head"
        else:
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_df = filtered_df.iloc[start_idx:end_idx]
            actual_sample_mode = "page"

        # Convert NaN, Inf to None / JSON compliant primitives
        records = []
        for row in page_df.to_dict(orient="records"):
            clean_row = {}
            for k, v in row.items():
                if pd.isna(v) or v is np.nan or (isinstance(v, float) and (np.isinf(v) or math.isnan(v))):
                    clean_row[k] = None
                elif isinstance(v, (pd.Timestamp, np.datetime64)):
                    clean_row[k] = str(v)
                elif isinstance(v, (np.integer, int)):
                    clean_row[k] = int(v)
                elif isinstance(v, (np.floating, float)):
                    if np.isnan(v) or np.isinf(v):
                        clean_row[k] = None
                    else:
                        clean_row[k] = float(v)
                else:
                    clean_row[k] = v
            records.append(clean_row)

        cached_meta = None
        if hasattr(effective_cache, "get_column_metadata") and not search.strip():
            cached_meta = effective_cache.get_column_metadata(node_id, port)

        if cached_meta:
            columns_meta = cached_meta
        else:
            columns_meta = compute_column_metadata(filtered_df if search.strip() else df)

        col_sources = getattr(df, "attrs", {}).get("column_sources", {})
        if col_sources:
            for col_entry in columns_meta:
                c_name = col_entry.get("name")
                if c_name in col_sources:
                    col_entry["source"] = col_sources[c_name]

        is_partial = total_records > len(records)
        is_wide_table = len(df.columns) > 30

        return {
            "available": True,
            "node_id": node_id,
            "port": port,
            "columns": columns_meta,
            "column_sources": col_sources,
            "records": records,
            "is_partial": is_partial,
            "is_wide_table": is_wide_table,
            "sample_mode": actual_sample_mode,
            "memory_bytes": mem_bytes,
            "memory_formatted": mem_formatted,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_records": total_records,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
                "rendered_records": len(records)
            }
        }

    def get_node_profiling(
        self,
        node_id: str,
        port: str = "O",
        run_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates comprehensive column statistics, health scores, and data profiling diagnostics.
        Delegates calculation to backend.engine.profiler.compute_dataset_profile.
        """
        run_entry = self.cache_manager.get_run(run_id=run_id, session_id=session_id)
        effective_cache = run_entry.data_cache if run_entry else self.data_cache
        node_cache = effective_cache.get(node_id)
        if hasattr(effective_cache, "get_profiling"):
            cached_prof = effective_cache.get_profiling(node_id, port)
            if cached_prof is not None:
                return cached_prof

        if not node_cache or port not in node_cache:
            return {"available": False, "message": "No data available to profile."}

        df = node_cache[port]
        if not isinstance(df, pd.DataFrame):
            return {"available": False, "message": "Cached data is not a tabular DataFrame."}

        from backend.engine.profiler import compute_dataset_profile
        res = compute_dataset_profile(df)

        if hasattr(effective_cache, "set_profiling"):
            effective_cache.set_profiling(node_id, port, res)

        return res

    def get_node_chart_data(
        self,
        node_id: str,
        port: str = "O",
        chart_type: str = "bar",
        x_col: Optional[str] = None,
        y_col: Optional[str] = None,
        agg_func: str = "count",
        num_bins: int = 15,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Computes aggregated or binned series for interactive frontend charting.
        Supports Bar, Line, Scatter, Histogram, and Donut charts.
        """
        run_entry = self.cache_manager.get_run(run_id=run_id, session_id=session_id)
        effective_cache = run_entry.data_cache if run_entry else self.data_cache
        node_cache = effective_cache.get(node_id)
        if not node_cache or port not in node_cache:
            return {"available": False, "message": "No data available for charting."}

        df = node_cache[port]
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {"available": False, "message": "Dataset is empty."}

        df = sanitize_dataframe(df)
        total_rows = len(df)

        if not x_col or x_col not in df.columns:
            # Pick first column by default
            x_col = str(df.columns[0])

        chart_type = (chart_type or "bar").lower()
        agg_func = (agg_func or "count").lower()
        if agg_func not in ["count", "sum", "mean", "min", "max"]:
            agg_func = "count"

        result = {
            "available": True,
            "node_id": node_id,
            "port": port,
            "chart_type": chart_type,
            "x_col": x_col,
            "y_col": y_col,
            "agg_func": agg_func,
            "total_rows": total_rows
        }

        # --------------------------------------------------------------
        # 1. Histogram (Single Continuous Variable)
        # --------------------------------------------------------------
        if chart_type == "histogram":
            target_col = x_col
            series = pd.to_numeric(df[target_col].dropna(), errors="coerce").dropna()
            if series.empty:
                return {"available": False, "message": f"Column '{target_col}' has no numeric values to plot."}

            bins = max(5, min(50, num_bins or 15))
            counts, bin_edges = np.histogram(series, bins=bins)
            items = []
            for b in range(len(counts)):
                st = round(float(bin_edges[b]), 3)
                en = round(float(bin_edges[b + 1]), 3)
                cnt = int(counts[b])
                items.append({
                    "bin_start": st,
                    "bin_end": en,
                    "count": cnt,
                    "label": f"[{st}, {en})",
                    "percent": round((cnt / len(series)) * 100.0, 1)
                })

            result.update({
                "series": items,
                "min": round(float(series.min()), 3),
                "max": round(float(series.max()), 3),
                "mean": round(float(series.mean()), 3),
                "median": round(float(series.median()), 3),
                "count": len(series),
                "x_label": target_col,
                "y_label": "Frequency (Count)"
            })
            return result

        # --------------------------------------------------------------
        # 2. Scatter Plot (Two Continuous Variables)
        # --------------------------------------------------------------
        if chart_type == "scatter":
            if not y_col or y_col not in df.columns:
                return {"available": False, "message": "Scatter plot requires both X and Y columns."}

            sub_df = df[[x_col, y_col]].dropna()
            sub_df[x_col] = pd.to_numeric(sub_df[x_col], errors="coerce")
            sub_df[y_col] = pd.to_numeric(sub_df[y_col], errors="coerce")
            sub_df = sub_df.dropna()

            if sub_df.empty:
                return {"available": False, "message": "Selected columns do not contain valid numeric pairs."}

            # Downsample if exceeding 3,000 points to keep SVG rendering ultra-fast (60 FPS)
            sampled = False
            if len(sub_df) > 3000:
                sub_df = sub_df.sample(n=3000, random_state=42)
                sampled = True

            corr = None
            try:
                if len(sub_df) > 2:
                    corr = round(float(sub_df[x_col].corr(sub_df[y_col])), 4)
            except Exception:
                pass

            points = [{"x": round(float(r[x_col]), 4), "y": round(float(r[y_col]), 4)} for _, r in sub_df.iterrows()]
            result.update({
                "points": points,
                "sampled": sampled,
                "total_points": len(points),
                "correlation": corr,
                "x_min": round(float(sub_df[x_col].min()), 4),
                "x_max": round(float(sub_df[x_col].max()), 4),
                "y_min": round(float(sub_df[y_col].min()), 4),
                "y_max": round(float(sub_df[y_col].max()), 4),
                "x_label": x_col,
                "y_label": y_col
            })
            return result

        # --------------------------------------------------------------
        # 3. Bar Chart & Donut Chart (Categorical X, Optional Numeric Y)
        # --------------------------------------------------------------
        if chart_type in ["bar", "donut"]:
            sub_df = df.dropna(subset=[x_col]).copy()
            sub_df[x_col] = sub_df[x_col].astype(str)

            if agg_func == "count" or not y_col or y_col not in df.columns:
                grouped = sub_df.groupby(x_col).size().rename("val")
                y_label = "Count of Records"
            else:
                sub_df[y_col] = pd.to_numeric(sub_df[y_col], errors="coerce")
                sub_df = sub_df.dropna(subset=[y_col])
                grouped = sub_df.groupby(x_col)[y_col].agg(agg_func).rename("val")
                y_label = f"{agg_func.capitalize()} of {y_col}"

            # Sort descending and limit to top 20 categories + "Other"
            sorted_series = grouped.sort_values(ascending=False)
            items = []
            if len(sorted_series) > 20:
                top_items = sorted_series.head(20)
                other_val = sorted_series.iloc[20:].sum()
                for k, v in top_items.items():
                    items.append({"label": str(k), "value": round(float(v), 2)})
                items.append({"label": "(Other)", "value": round(float(other_val), 2)})
            else:
                for k, v in sorted_series.items():
                    items.append({"label": str(k), "value": round(float(v), 2)})

            result.update({
                "items": items,
                "x_label": x_col,
                "y_label": y_label
            })
            return result

        # --------------------------------------------------------------
        # 4. Line Chart (Sequential / Temporal X, Numeric Y)
        # --------------------------------------------------------------
        if chart_type == "line":
            sub_df = df.dropna(subset=[x_col]).copy()
            if agg_func == "count" or not y_col or y_col not in df.columns:
                grouped = sub_df.groupby(x_col).size().rename("val")
                y_label = "Count of Records"
            else:
                sub_df[y_col] = pd.to_numeric(sub_df[y_col], errors="coerce")
                sub_df = sub_df.dropna(subset=[y_col])
                grouped = sub_df.groupby(x_col)[y_col].agg(agg_func).rename("val")
                y_label = f"{agg_func.capitalize()} of {y_col}"

            # Sort by X index
            try:
                # Try sorting as dates
                sorted_series = grouped.sort_index(key=lambda s: pd.to_datetime(s, errors="coerce"))
            except Exception:
                try:
                    # Try sorting as numbers
                    sorted_series = grouped.sort_index(key=lambda s: pd.to_numeric(s, errors="coerce"))
                except Exception:
                    sorted_series = grouped.sort_index()

            # Limit to 50 points max for clear line display
            if len(sorted_series) > 60:
                step = math.ceil(len(sorted_series) / 60)
                sorted_series = sorted_series.iloc[::step]

            items = [{"x": str(k), "y": round(float(v), 2)} for k, v in sorted_series.items()]
            result.update({
                "points": items,
                "x_label": x_col,
                "y_label": y_label
            })
            return result

        return {"available": False, "message": f"Unsupported chart type '{chart_type}'."}
