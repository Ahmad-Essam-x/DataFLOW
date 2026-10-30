"""
Run & Session Cache Manager.
Provides thread-safe, isolated intermediate DataFrame caching per execution run and client session.
Implements an Alteryx-style spill-to-disk architecture using Apache Arrow / Feather (pyarrow),
bounded in-memory LRU caching, precomputed column profiling, and automatic disk cleanup.
"""
import os
import re
import time
import uuid
import shutil
import atexit
import tempfile
import threading
import collections
from typing import Dict, Any, Optional, List, Iterator, Tuple
import numpy as np
import pandas as pd

try:
    import pyarrow.feather as feather
    HAS_PYARROW = True
except Exception:
    HAS_PYARROW = False

# Default temporary cache root directory on system fast temp drive
GLOBAL_CACHE_ROOT = os.path.join(tempfile.gettempdir(), "antigravity_dataflow_cache")
os.makedirs(GLOBAL_CACHE_ROOT, exist_ok=True)


def _cleanup_global_cache():
    """Removes temporary cache directory upon Python process termination."""
    try:
        if os.path.exists(GLOBAL_CACHE_ROOT):
            shutil.rmtree(GLOBAL_CACHE_ROOT, ignore_errors=True)
    except Exception:
        pass


atexit.register(_cleanup_global_cache)


def compute_column_metadata(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Computes column types, data quality metrics (ok, null, blank),
    and 8-bin distribution histograms. Uses a fast uniform sample for
    sparkline distributions on tables exceeding 10,000 rows.
    """
    if not isinstance(df, pd.DataFrame):
        return []

    from backend.engine.node_registry import infer_alteryx_type

    total_rows = len(df)
    columns_meta = []

    # If df is large, sample rows for fast sparkline distribution and value counts
    sample_df = df.sample(n=min(10000, total_rows), random_state=42) if total_rows > 10000 else df

    for i, col in enumerate(df.columns):
        series = df.iloc[:, i]
        dtype_str = infer_alteryx_type(series)
        null_count = int(series.isna().sum())

        # Fast vectorized blank check for string/object series
        if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
            try:
                blank_count = int(series.isin(["", " ", "  ", "\t", "   "]).sum())
                if blank_count == 0 and total_rows <= 10000:
                    s_valid = series.dropna()
                    blank_count = int(s_valid.astype(str).str.strip().eq("").sum())
            except Exception:
                blank_count = 0
        else:
            blank_count = 0

        ok_count = max(0, total_rows - null_count - blank_count)
        ok_pct = round((ok_count / total_rows * 100.0), 1) if total_rows > 0 else 100.0
        null_pct = round((null_count / total_rows * 100.0), 1) if total_rows > 0 else 0.0
        blank_pct = round((blank_count / total_rows * 100.0), 1) if total_rows > 0 else 0.0

        mini_hist = []
        try:
            sample_series = sample_df.iloc[:, i]
            s_drop = sample_series.dropna()
            if not s_drop.empty:
                if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
                    non_nulls = pd.to_numeric(s_drop, errors="coerce").dropna()
                    if not non_nulls.empty:
                        bin_cnt = min(8, max(1, len(non_nulls.unique())))
                        counts, bin_edges = np.histogram(non_nulls, bins=bin_cnt)
                        s_cnt = len(non_nulls)
                        for b in range(len(counts)):
                            pct = round((int(counts[b]) / s_cnt) * 100.0, 1) if s_cnt > 0 else 0
                            mini_hist.append({
                                "start": round(float(bin_edges[b]), 2),
                                "end": round(float(bin_edges[b + 1]), 2),
                                "count": int(counts[b]),
                                "percent": pct,
                                "label": f"{round(float(bin_edges[b]), 1)} - {round(float(bin_edges[b+1]), 1)}"
                            })
                else:
                    vc = s_drop.astype(str).value_counts().head(8)
                    s_cnt = len(s_drop)
                    for k, v in vc.items():
                        pct = round((int(v) / s_cnt) * 100.0, 1) if s_cnt > 0 else 0
                        mini_hist.append({
                            "value": str(k),
                            "count": int(v),
                            "percent": pct,
                            "label": str(k)[:12]
                        })
        except Exception:
            pass

        columns_meta.append({
            "name": str(col),
            "dtype": dtype_str,
            "null_count": null_count,
            "blank_count": blank_count,
            "ok_count": ok_count,
            "histogram": mini_hist,
            "quality": {
                "ok_pct": ok_pct,
                "null_pct": null_pct,
                "blank_pct": blank_pct,
                "ok_count": ok_count,
                "null_count": null_count,
                "blank_count": blank_count
            }
        })

    return columns_meta


class SpillableRunDataCache(collections.abc.MutableMapping):
    """
    High-performance, disk-spilling dictionary mapping node_id -> { port: pd.DataFrame }.
    Persists DataFrames to disk using pyarrow Feather (Arrow IPC with LZ4 compression) lazily on eviction,
    bounds resident memory using an LRU eviction pool (default 4 active nodes),
    and caches lazily computed column quality metadata.
    """
    def __init__(self, run_id: str, cache_root_dir: Optional[str] = None, max_in_memory_nodes: int = 4):
        self.run_id = run_id
        safe_run_name = re.sub(r"[^\w\-_\.]", "_", run_id)
        self.cache_dir = os.path.join(cache_root_dir or GLOBAL_CACHE_ROOT, safe_run_name)
        os.makedirs(self.cache_dir, exist_ok=True)

        self.max_in_memory_nodes = max_in_memory_nodes
        self._memory_lru: collections.OrderedDict = collections.OrderedDict()
        # node_id -> { port: { "file_path": ..., "row_count": ..., "columns": [...], "column_meta": [...], "in_memory_val": ... } }
        self._meta: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._profiling_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def __getitem__(self, node_id: str) -> Dict[str, Any]:
        with self._lock:
            if node_id in self._memory_lru:
                self._memory_lru.move_to_end(node_id)
                return self._memory_lru[node_id]

            if node_id in self._meta:
                ports_dict = {}
                for port, p_meta in self._meta[node_id].items():
                    fp = p_meta.get("file_path")
                    if fp and os.path.exists(fp) and HAS_PYARROW:
                        try:
                            df = feather.read_feather(fp)
                            ports_dict[port] = df
                            continue
                        except Exception:
                            pass
                    if "in_memory_val" in p_meta:
                        ports_dict[port] = p_meta["in_memory_val"]
                    else:
                        ports_dict[port] = pd.DataFrame()

                self._memory_lru[node_id] = ports_dict
                self._memory_lru.move_to_end(node_id)
                self._evict_excess_memory_locked()
                return ports_dict

            raise KeyError(f"Node '{node_id}' not found in cache.")

    def __setitem__(self, node_id: str, outputs: Dict[str, Any]):
        with self._lock:
            if not isinstance(outputs, dict):
                outputs = {"O": outputs}

            node_meta: Dict[str, Dict[str, Any]] = {}
            for port, val in outputs.items():
                if isinstance(val, pd.DataFrame):
                    # Ensure column names are unique clean strings
                    val.columns = [str(c) for c in val.columns]
                    row_cnt = len(val)
                    cols_list = list(val.columns)

                    node_meta[port] = {
                        "row_count": row_cnt,
                        "columns": cols_list,
                        "column_meta": None,
                        "file_path": None
                    }
                else:
                    node_meta[port] = {
                        "row_count": 0,
                        "columns": [],
                        "column_meta": [],
                        "file_path": None,
                        "in_memory_val": val
                    }

            self._meta[node_id] = node_meta
            self._memory_lru[node_id] = outputs
            self._memory_lru.move_to_end(node_id)
            self._evict_excess_memory_locked()

    def _spill_node_locked(self, node_id: str, outputs: Dict[str, Any]):
        """Serializes node DataFrames to Feather on disk when evicted from memory."""
        if not outputs:
            return
        node_meta = self._meta.get(node_id)
        if not node_meta:
            return

        safe_nid = re.sub(r"[^\w\-_\.]", "_", node_id)
        for port, val in outputs.items():
            if isinstance(val, pd.DataFrame):
                p_meta = node_meta.setdefault(port, {})
                fp = p_meta.get("file_path")
                if fp and os.path.exists(fp):
                    continue
                if HAS_PYARROW:
                    safe_port = re.sub(r"[^\w\-_\.]", "_", port)
                    file_path = os.path.join(self.cache_dir, f"{safe_nid}_{safe_port}.feather")
                    try:
                        feather.write_feather(val, file_path, compression="lz4")
                        p_meta["file_path"] = file_path
                        p_meta.pop("in_memory_val", None)
                    except Exception:
                        try:
                            feather.write_feather(val, file_path)
                            p_meta["file_path"] = file_path
                            p_meta.pop("in_memory_val", None)
                        except Exception:
                            # Disk full / unwritable: keep the data in memory rather than lose it,
                            # and remove any truncated file left behind by the failed write.
                            p_meta["in_memory_val"] = val
                            try:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                            except OSError:
                                pass
                else:
                    p_meta["in_memory_val"] = val
            else:
                p_meta = node_meta.setdefault(port, {})
                p_meta["in_memory_val"] = val

    def _evict_excess_memory_locked(self):
        while len(self._memory_lru) > self.max_in_memory_nodes:
            oldest_id, oldest_outputs = self._memory_lru.popitem(last=False)
            self._spill_node_locked(oldest_id, oldest_outputs)

    def evict_from_memory(self, node_id: str):
        """
        Spills and releases the in-memory DataFrame for an upstream node whose consumers
        have completed execution. The data remains accessible from the Feather disk file.
        """
        with self._lock:
            outputs = self._memory_lru.pop(node_id, None)
            if outputs is not None:
                self._spill_node_locked(node_id, outputs)

    def __delitem__(self, node_id: str):
        with self._lock:
            self._memory_lru.pop(node_id, None)
            node_meta = self._meta.pop(node_id, None)
            if node_meta:
                for p_meta in node_meta.values():
                    fp = p_meta.get("file_path")
                    if fp and os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            return iter(list(self._meta.keys()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._meta)

    def __contains__(self, node_id: object) -> bool:
        with self._lock:
            return str(node_id) in self._meta or str(node_id) in self._memory_lru

    def get_dataframe(self, node_id: str, port: str = "O") -> Optional[pd.DataFrame]:
        """Direct accessor for a single port DataFrame."""
        with self._lock:
            if node_id not in self:
                return None
            try:
                ports = self[node_id]
                return ports.get(port)
            except Exception:
                return None

    def get_column_metadata(self, node_id: str, port: str = "O") -> Optional[List[Dict[str, Any]]]:
        """Returns column quality and mini-histograms, lazily computing on demand if not cached."""
        with self._lock:
            node_meta = self._meta.get(node_id)
            if not node_meta or port not in node_meta:
                return None

            cached = node_meta[port].get("column_meta")
            if cached is not None:
                return cached

            df = self.get_dataframe(node_id, port)
            if df is not None and isinstance(df, pd.DataFrame):
                cols_meta = compute_column_metadata(df)
                node_meta[port]["column_meta"] = cols_meta
                return cols_meta

            return []

    def get_record_count(self, node_id: str, port: str = "O") -> int:
        with self._lock:
            node_meta = self._meta.get(node_id)
            if node_meta and port in node_meta:
                return node_meta[port].get("row_count", 0)
            return 0

    def get_profiling(self, node_id: str, port: str = "O") -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._profiling_cache.get((node_id, port))

    def set_profiling(self, node_id: str, port: str, profile_data: Dict[str, Any]):
        with self._lock:
            self._profiling_cache[(node_id, port)] = profile_data

    def clear(self):
        with self._lock:
            self._memory_lru.clear()
            self._profiling_cache.clear()
            if os.path.exists(self.cache_dir):
                for f in os.listdir(self.cache_dir):
                    try:
                        os.remove(os.path.join(self.cache_dir, f))
                    except Exception:
                        pass
            self._meta.clear()

    def destroy(self):
        """Wipes in-memory state and deletes the temporary disk directory."""
        with self._lock:
            self._memory_lru.clear()
            self._meta.clear()
            self._profiling_cache.clear()
            if os.path.exists(self.cache_dir):
                shutil.rmtree(self.cache_dir, ignore_errors=True)


class RunCacheEntry:
    """Represents the cached state and intermediate DataFrames for a single execution run."""
    def __init__(
        self,
        run_id: str,
        session_id: Optional[str] = None,
        workflow_name: str = "",
        cache_root_dir: Optional[str] = None,
        max_in_memory_nodes: int = 4
    ):
        self.run_id = run_id
        self.session_id = session_id
        self.workflow_name = workflow_name
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.data_cache = SpillableRunDataCache(
            run_id=run_id,
            cache_root_dir=cache_root_dir,
            max_in_memory_nodes=max_in_memory_nodes
        )
        self.execution_result: Optional[Any] = None

    def touch(self):
        self.last_accessed = time.time()

    def get_dataframe(self, node_id: str, port: str = "O") -> Optional[pd.DataFrame]:
        self.touch()
        return self.data_cache.get_dataframe(node_id, port)

    def set_node_outputs(self, node_id: str, outputs: Dict[str, pd.DataFrame]):
        self.touch()
        self.data_cache[node_id] = outputs

    def get_column_metadata(self, node_id: str, port: str = "O") -> Optional[List[Dict[str, Any]]]:
        self.touch()
        return self.data_cache.get_column_metadata(node_id, port)

    def destroy(self):
        self.data_cache.destroy()


class SessionRunCacheManager:
    """
    Thread-safe manager for multiple execution runs with session association,
    LRU capacity bounding, TTL eviction, and automatic Feather temp file pruning.
    """
    def __init__(
        self,
        max_runs: int = 2,
        ttl_seconds: int = 7200,
        cache_root_dir: Optional[str] = None,
        max_in_memory_nodes: int = 4
    ):
        self.max_runs = max_runs
        self.ttl_seconds = ttl_seconds
        self.cache_root_dir = cache_root_dir or GLOBAL_CACHE_ROOT
        self.max_in_memory_nodes = max_in_memory_nodes
        self._runs: Dict[str, RunCacheEntry] = {}
        self._session_latest_run: Dict[str, str] = {}
        self._latest_run_id: Optional[str] = None
        self._lock = threading.Lock()
        os.makedirs(self.cache_root_dir, exist_ok=True)

    def create_run(
        self,
        session_id: Optional[str] = None,
        workflow_name: str = "",
        run_id: Optional[str] = None
    ) -> RunCacheEntry:
        with self._lock:
            self._evict_expired_or_overflow_locked()

            final_run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
            entry = RunCacheEntry(
                run_id=final_run_id,
                session_id=session_id,
                workflow_name=workflow_name,
                cache_root_dir=self.cache_root_dir,
                max_in_memory_nodes=self.max_in_memory_nodes
            )
            self._runs[final_run_id] = entry
            self._latest_run_id = final_run_id

            if session_id:
                self._session_latest_run[session_id] = final_run_id

            return entry

    def store_run_data(
        self,
        run_id: str,
        data_cache: Any,
        execution_result: Optional[Any] = None,
        session_id: Optional[str] = None
    ):
        with self._lock:
            entry = self._runs.get(run_id)
            if not entry:
                self._evict_expired_or_overflow_locked()
                entry = RunCacheEntry(
                    run_id=run_id,
                    session_id=session_id,
                    cache_root_dir=self.cache_root_dir,
                    max_in_memory_nodes=self.max_in_memory_nodes
                )
                self._runs[run_id] = entry
                self._latest_run_id = run_id
                if session_id:
                    self._session_latest_run[session_id] = run_id

            if isinstance(data_cache, SpillableRunDataCache):
                entry.data_cache = data_cache
            elif isinstance(data_cache, dict):
                for nid, outs in data_cache.items():
                    entry.data_cache[nid] = outs

            entry.execution_result = execution_result
            if session_id and not entry.session_id:
                entry.session_id = session_id
                self._session_latest_run[session_id] = run_id
            entry.touch()

    def get_run(self, run_id: Optional[str] = None, session_id: Optional[str] = None) -> Optional[RunCacheEntry]:
        with self._lock:
            if run_id:
                if run_id in self._runs:
                    entry = self._runs[run_id]
                    if session_id and entry.session_id and entry.session_id != session_id:
                        return None
                    entry.touch()
                    return entry
                return None

            target_id = None
            if session_id and session_id in self._session_latest_run:
                target_id = self._session_latest_run.get(session_id)
            elif self._latest_run_id and self._latest_run_id in self._runs:
                target_id = self._latest_run_id

            if target_id and target_id in self._runs:
                entry = self._runs[target_id]
                entry.touch()
                return entry

            return None

    def get_latest_run(self) -> Optional[RunCacheEntry]:
        with self._lock:
            if self._latest_run_id and self._latest_run_id in self._runs:
                entry = self._runs[self._latest_run_id]
                entry.touch()
                return entry
            return None

    def size(self) -> int:
        with self._lock:
            return len(self._runs)

    def __len__(self) -> int:
        return self.size()

    def cleanup_expired(self) -> List[str]:
        with self._lock:
            now = time.time()
            expired_ids = [rid for rid, entry in self._runs.items() if now - entry.last_accessed > self.ttl_seconds]
            for rid in expired_ids:
                self._delete_run_locked(rid)
            return expired_ids

    def _evict_expired_or_overflow_locked(self):
        now = time.time()
        expired_ids = [rid for rid, entry in self._runs.items() if now - entry.last_accessed > self.ttl_seconds]
        for rid in expired_ids:
            self._delete_run_locked(rid)

        while len(self._runs) >= self.max_runs:
            oldest_id = min(self._runs.keys(), key=lambda rid: self._runs[rid].last_accessed)
            self._delete_run_locked(oldest_id)

    def _delete_run_locked(self, run_id: str):
        entry = self._runs.pop(run_id, None)
        if not entry:
            return

        entry.destroy()

        if entry.session_id and self._session_latest_run.get(entry.session_id) == run_id:
            del self._session_latest_run[entry.session_id]

        if self._latest_run_id == run_id:
            if self._runs:
                self._latest_run_id = max(self._runs.keys(), key=lambda rid: self._runs[rid].last_accessed)
            else:
                self._latest_run_id = None

    def purge_all(self):
        """Purges all cached runs, terminates resident memory, and cleans up all temporary files."""
        with self._lock:
            for entry in list(self._runs.values()):
                try:
                    entry.destroy()
                except Exception:
                    pass
            self._runs.clear()
            self._session_latest_run.clear()
            self._latest_run_id = None
            try:
                if os.path.exists(self.cache_root_dir):
                    shutil.rmtree(self.cache_root_dir, ignore_errors=True)
                    os.makedirs(self.cache_root_dir, exist_ok=True)
            except Exception:
                pass

    def get_total_disk_bytes(self) -> int:
        """Returns total disk space occupied by cache files."""
        total = 0
        try:
            if os.path.exists(self.cache_root_dir):
                for dirpath, _, filenames in os.walk(self.cache_root_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total += os.path.getsize(fp)
                        except Exception:
                            pass
        except Exception:
            pass
        return total

    def clear(self):
        self.purge_all()

