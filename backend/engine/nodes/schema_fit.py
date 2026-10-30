"""
Schema Fit Tool Node — authentic Alteryx GenAI implementation.
Transforms unformatted Source data (port S) to match the schema, naming,
and data types of reference Target data (port T) using AI-synthesized,
transparent Python transformations.

Anchors:
- Inputs:
    M: LLM Model configuration from LLM Override tool (optional)
    T: Reference formatted Target dataset
    S: Unformatted Source dataset to transform
- Outputs:
    T: Transformation steps table (columns: "Transformation Step", "Code")
    D: Transformed Source data matching Target schema
"""
import re
import json
import difflib
import datetime
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base import BaseNode, NodeExecutionError, sanitize_dataframe, infer_alteryx_type
from backend.engine.ai.provider_base import LLMConfig
from backend.engine.ai.provider_registry import get_provider
from backend.engine.sandbox import run_pandas_code
from backend.engine.ai.egress import EgressNotApproved




def _normalize_name(name: str) -> str:
    """Normalizes column name for fuzzy matching (lowercase alphanumeric)."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


class SchemaFitNode(BaseNode):
    type_name = "schema_fit"
    category = "ai"
    display_name = "Schema Fit"
    description = "Transform Source data to match Target schema using AI-generated Python steps"
    input_ports = ["M", "T", "S"]
    output_ports = ["T", "D"]

    def execute(
        self,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, pd.DataFrame]:
        # ------------------------------------------------------------------ #
        # 1. Validate Input Anchors
        # ------------------------------------------------------------------ #
        df_target_raw = inputs.get("T")
        df_source_raw = inputs.get("S")

        if df_target_raw is None or not isinstance(df_target_raw, pd.DataFrame):
            raise NodeExecutionError(
                "Schema Fit: Target reference data is missing from anchor 'T'. "
                "Connect a dataset defining the desired target schema."
            )

        if df_source_raw is None or not isinstance(df_source_raw, pd.DataFrame):
            raise NodeExecutionError(
                "Schema Fit: Source data is missing from anchor 'S'. "
                "Connect the unformatted dataset you want to transform."
            )

        df_target = sanitize_dataframe(df_target_raw.copy())
        df_source = sanitize_dataframe(df_source_raw.copy())

        if df_source.empty:
            self.messages.append("Schema Fit: Source dataset is empty. Returning empty schema match.")
            empty_t = pd.DataFrame(columns=["Transformation Step", "Code"])
            empty_d = pd.DataFrame(columns=df_target.columns)
            return {"T": empty_t, "D": empty_d}

        # ------------------------------------------------------------------ #
        # 2. Extract Configuration & Resolve Model (Anchor M or Local)
        # ------------------------------------------------------------------ #
        cfg = self.config or {}
        max_transformations = int(cfg.get("max_transformations", 5))
        max_transformations = max(1, min(max_transformations, 20))
        only_target_columns = bool(cfg.get("only_target_columns", True))
        custom_code = (cfg.get("custom_code") or "").strip()

        # Check for model override connected on anchor M
        llm_config_resolved: Dict[str, Any] = {}
        df_m = inputs.get("M")
        if df_m is not None:
            if hasattr(df_m, "attrs") and "llm_config" in df_m.attrs:
                llm_config_resolved = df_m.attrs["llm_config"]
            elif isinstance(df_m, dict):
                llm_config_resolved = df_m
            elif isinstance(df_m, pd.DataFrame) and "Setting" in df_m.columns and "Value" in df_m.columns:
                settings_dict = dict(zip(df_m["Setting"], df_m["Value"]))
                llm_config_resolved = {
                    "provider_type": settings_dict.get("Provider", "ollama").lower(),
                    "model": settings_dict.get("Model", ""),
                    "connection": {
                        "base_url": settings_dict.get("Base URL", ""),
                        "api_key": ""  # resolved from the credential store by get_provider()
                    }
                }

        # Fallback to embedded node config if anchor M is not connected
        if not llm_config_resolved:
            llm_config_resolved = {
                "provider_type": cfg.get("provider_type", "ollama"),
                "model": cfg.get("model", ""),
                "connection": cfg.get("connection", {}),
                "temperature": float(cfg.get("temperature", 0.2)),
                "max_tokens": int(cfg.get("max_tokens", 1024)),
                "timeout_seconds": float(cfg.get("timeout_seconds", 30.0)),
            }

        # ------------------------------------------------------------------ #
        # 3. If User Provided Custom Override Code, Execute Directly
        # ------------------------------------------------------------------ #
        if custom_code:
            self.messages.append("Schema Fit: Executing user-provided custom Python transformation code.")
            df_out, err = self._run_sandbox(df_source, custom_code)
            if err:
                raise NodeExecutionError(f"Schema Fit: Custom code execution failed: {err}")
            if only_target_columns:
                keep = [c for c in df_target.columns if c in df_out.columns]
                df_out = df_out[keep]
            df_t = pd.DataFrame([{
                "Transformation Step": "User-defined custom script execution",
                "Code": custom_code
            }])
            return {"T": sanitize_dataframe(df_t), "D": sanitize_dataframe(df_out)}

        # ------------------------------------------------------------------ #
        # 4. Synthesize Transformations (LLM with Self-Correction or Heuristic)
        # ------------------------------------------------------------------ #
        target_schema_info = self._extract_schema_profile(df_target)
        source_schema_info = self._extract_schema_profile(df_source)

        steps: List[Dict[str, str]] = []
        df_transformed = df_source.copy()
        used_ai = False

        # Attempt AI synthesis if provider configured
        provider_type = llm_config_resolved.get("provider_type")
        model_name = llm_config_resolved.get("model")

        if provider_type and model_name:
            try:
                ai_steps, ai_df = self._synthesize_with_llm(
                    df_source=df_source,
                    df_target=df_target,
                    source_schema=source_schema_info,
                    target_schema=target_schema_info,
                    llm_config=llm_config_resolved,
                    max_attempts=max_transformations,
                    only_target_columns=only_target_columns
                )
                if ai_steps and ai_df is not None:
                    steps = ai_steps
                    df_transformed = ai_df
                    used_ai = True
            except EgressNotApproved:
                raise  # consent is a hard stop; do not silently fall back
            except Exception as e:
                self.messages.append(f"Schema Fit: LLM synthesis notice: {e}. Utilizing deterministic schema matcher.")

        # If LLM wasn't used or produced no steps, use deterministic heuristic matcher
        if not used_ai:
            steps, df_transformed = self._heuristic_transform(
                df_source=df_source,
                df_target=df_target,
                only_target_columns=only_target_columns
            )
            self.messages.append(
                f"Schema Fit: Applied {len(steps)} deterministic transformation step(s) to align with target schema."
            )
        else:
            self.messages.append(
                f"Schema Fit: Applied {len(steps)} AI-synthesized transformation step(s) using {provider_type}/{model_name}."
            )

        # ------------------------------------------------------------------ #
        # 5. Format Outputs: Anchor T (Steps) and Anchor D (Transformed Data)
        # ------------------------------------------------------------------ #
        if not steps:
            steps = [{
                "Transformation Step": "Identity pass-through (Source already aligns with Target)",
                "Code": "df = df.copy()"
            }]

        df_steps = pd.DataFrame(steps)
        if "Transformation Step" not in df_steps.columns or "Code" not in df_steps.columns:
            df_steps = pd.DataFrame({
                "Transformation Step": [s.get("step", s.get("Transformation Step", "Step")) for s in steps],
                "Code": [s.get("code", s.get("Code", "")) for s in steps]
            })

        df_steps = sanitize_dataframe(df_steps)
        df_transformed = sanitize_dataframe(df_transformed)

        return {"T": df_steps, "D": df_transformed}

    # ---------------------------------------------------------------------- #
    # Helper: Extract Schema Profile for Prompt & Matching
    # ---------------------------------------------------------------------- #
    def _extract_schema_profile(self, df: pd.DataFrame) -> Dict[str, Any]:
        profile: Dict[str, Any] = {}
        for col in df.columns:
            series = df[col]
            alt_type = infer_alteryx_type(series)
            non_null = series.dropna().head(3).tolist()
            # Convert non-serializable objects (like timestamps) to strings
            sample_clean = []
            for item in non_null:
                if isinstance(item, (pd.Timestamp, datetime.date, datetime.datetime)):
                    sample_clean.append(str(item))
                elif isinstance(item, (np.integer, int)):
                    sample_clean.append(int(item))
                elif isinstance(item, (np.floating, float)):
                    sample_clean.append(float(item))
                else:
                    sample_clean.append(str(item))

            profile[str(col)] = {
                "type": alt_type,
                "dtype": str(series.dtype),
                "null_count": int(series.isna().sum()),
                "samples": sample_clean
            }
        return profile

    # ---------------------------------------------------------------------- #
    # Helper: LLM Synthesis with Self-Correction Reflection Loop
    # ---------------------------------------------------------------------- #
    def _synthesize_with_llm(
        self,
        df_source: pd.DataFrame,
        df_target: pd.DataFrame,
        source_schema: Dict[str, Any],
        target_schema: Dict[str, Any],
        llm_config: Dict[str, Any],
        max_attempts: int,
        only_target_columns: bool
    ) -> Tuple[List[Dict[str, str]], Optional[pd.DataFrame]]:
        provider = get_provider(
            llm_config.get("provider_type", "ollama"),
            llm_config.get("connection", {})
        )
        model = llm_config.get("model", "")
        config_obj = LLMConfig(
            model=model,
            temperature=float(llm_config.get("temperature", 0.2)),
            max_tokens=int(llm_config.get("max_tokens", 1024)),
            timeout_seconds=float(llm_config.get("timeout_seconds", 30.0))
        )

        system_prompt = (
            "You are an expert Python and Pandas data engineer. Your task is to transform a source DataFrame named `df` "
            "so that its columns, data formats, and structure match a reference target DataFrame.\n\n"
            "Rules:\n"
            "1. Output MUST be a strictly valid JSON array of transformation steps.\n"
            "2. Each object in the array must have two keys:\n"
            "   - 'Transformation Step': A concise, plain-English explanation of the transformation step.\n"
            "   - 'Code': Executable Python/Pandas code modifying `df` in-place or reassigning `df`.\n"
            "3. Use only safe Pandas (`df['col']`, `df.rename()`, `df.astype()`, `pd.to_datetime()`, etc.).\n"
            "4. Match target column names exactly. Handle casing, snake_case/camelCase, spaces, and abbreviations.\n"
            "5. Convert values (e.g. currency '$100' to float, dates to standard format).\n"
            "6. If a target column cannot be derived from source, initialize it with `np.nan`.\n"
            f"7. {'Only retain the target columns in target order.' if only_target_columns else 'Retain target columns first, keeping extra source columns.'}\n"
            "8. DO NOT output any markdown backticks, conversational preamble, or explanations outside the JSON array."
        )

        user_prompt = (
            f"Target Schema:\n{json.dumps(target_schema, indent=2)}\n\n"
            f"Source Schema:\n{json.dumps(source_schema, indent=2)}\n\n"
            "Generate the Python transformation steps to reshape `df` from Source to Target schema."
        )

        last_error = ""
        current_user_prompt = user_prompt

        for attempt in range(1, max_attempts + 1):
            response = provider.generate(
                system_prompt=system_prompt,
                user_prompt=current_user_prompt,
                config=config_obj
            )
            if not response or not response.text:
                continue

            # Clean response text to parse JSON
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:-1]) if len(lines) > 2 else raw_text
                raw_text = raw_text.strip()

            try:
                steps_data = json.loads(raw_text)
                if not isinstance(steps_data, list):
                    raise ValueError("LLM response did not return a JSON array.")

                # Normalize keys
                normalized_steps = []
                for s in steps_data:
                    step_desc = s.get("Transformation Step") or s.get("step") or s.get("description") or "Transform"
                    code_snippet = s.get("Code") or s.get("code") or ""
                    if code_snippet:
                        normalized_steps.append({
                            "Transformation Step": step_desc,
                            "Code": code_snippet
                        })

                # Test run in sandbox
                combined_code = "\n".join(s["Code"] for s in normalized_steps)
                res_df, err = self._run_sandbox(df_source, combined_code)

                if err:
                    last_error = err
                    current_user_prompt = (
                        f"Previous attempt failed with error:\n{err}\n"
                        f"Please correct the Python code steps and return the JSON array."
                    )
                    continue

                # Verify target columns present
                missing_targets = [c for c in df_target.columns if c not in res_df.columns]
                if missing_targets and attempt < max_attempts:
                    current_user_prompt = (
                        f"The transformed dataframe is missing required target columns: {missing_targets}.\n"
                        f"Current columns: {list(res_df.columns)}.\n"
                        f"Please ensure all target columns are created and returned."
                    )
                    continue

                if only_target_columns:
                    target_cols_present = [c for c in df_target.columns if c in res_df.columns]
                    res_df = res_df[target_cols_present]

                return normalized_steps, res_df

            except Exception as parse_err:
                last_error = str(parse_err)
                current_user_prompt = (
                    f"Invalid JSON returned: {parse_err}. "
                    "Ensure response is strictly a JSON array without markdown fences."
                )

        raise NodeExecutionError(f"LLM synthesis was unable to complete after {max_attempts} attempts. Last error: {last_error}")

    # ---------------------------------------------------------------------- #
    # Helper: Safe Sandboxed Python Execution
    # ---------------------------------------------------------------------- #
    def _run_sandbox(self, df_input: pd.DataFrame, code_str: str) -> Tuple[pd.DataFrame, Optional[str]]:
        """Static AST gate + isolated child process with a time limit (see backend/engine/sandbox.py)."""
        return run_pandas_code(df_input, code_str)

    # ---------------------------------------------------------------------- #
    # Helper: Deterministic Heuristic Schema Matcher (Zero-Token Offline)
    # ---------------------------------------------------------------------- #
    def _heuristic_transform(
        self,
        df_source: pd.DataFrame,
        df_target: pd.DataFrame,
        only_target_columns: bool
    ) -> Tuple[List[Dict[str, str]], pd.DataFrame]:
        df = df_source.copy()
        steps: List[Dict[str, str]] = []

        source_cols = list(df.columns)
        target_cols = list(df_target.columns)

        # 1. Column Name Mapping (Exact -> Normalized -> Fuzzy)
        matched_pairs: Dict[str, str] = {}  # source_col -> target_col
        used_target: set = set()

        # Abbreviations dictionary for schema matching
        abbrevs = {
            "rev": "revenue", "cust": "customer", "amt": "amount", "emp": "employee",
            "prod": "product", "desc": "description", "addr": "address", "dt": "date",
            "qty": "quantity", "cat": "category", "pct": "percent", "dept": "department",
            "tot": "total", "cnt": "count", "val": "value", "sal": "salary", "pay": "salary",
            "num": "number", "no": "number", "src": "source", "tgt": "target"
        }

        def tokenize_col(col_name: str) -> Tuple[List[str], List[str]]:
            s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(col_name))
            s2 = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1)
            raw_tokens = [tok.lower() for tok in re.split(r"[^a-zA-Z0-9]+", s2) if tok]
            exp_tokens = [abbrevs.get(tok, tok) for tok in raw_tokens]
            return raw_tokens, exp_tokens

        def score_pair(s_col: str, t_col: str) -> float:
            if s_col == t_col:
                return 1.0
            sn = _normalize_name(s_col)
            tn = _normalize_name(t_col)
            if sn == tn:
                return 0.95
            s_raw, s_exp = tokenize_col(s_col)
            t_raw, t_exp = tokenize_col(t_col)
            if "".join(s_exp) == "".join(t_exp):
                return 0.92
            s_set, t_set = set(s_exp), set(t_exp)
            if t_set.issubset(s_set):
                return 0.88
            if s_set.issubset(t_set):
                return 0.85
            overlap = len(s_set.intersection(t_set))
            if overlap > 0:
                return 0.70 + (0.15 * (overlap / max(len(s_set), len(t_set))))
            for sr in s_raw:
                for tr in t_raw:
                    if len(sr) >= 3 and len(tr) >= 3 and (sr.startswith(tr) or tr.startswith(sr)):
                        return 0.75
            if (len(sn) >= 3 and len(tn) >= 3) and (sn in tn or tn in sn):
                return 0.70
            return difflib.SequenceMatcher(None, sn, tn).ratio()

        # Phase A: Exact Match
        for s in source_cols:
            if s in target_cols and s not in used_target:
                matched_pairs[s] = s
                used_target.add(s)

        # Phase B: Semantic & Fuzzy Token Matching
        for s in source_cols:
            if s in matched_pairs:
                continue
            remaining_targets = [t for t in target_cols if t not in used_target]
            if not remaining_targets:
                break
            best_target = None
            best_score = 0.0
            for t in remaining_targets:
                sc = score_pair(s, t)
                if sc > best_score:
                    best_score = sc
                    best_target = t

            if best_target and best_score >= 0.65:
                matched_pairs[s] = best_target
                used_target.add(best_target)

        # Apply renames where source != target
        renames = {s: t for s, t in matched_pairs.items() if s != t}
        if renames:
            rename_desc = ", ".join(f"'{s}' -> '{t}'" for s, t in renames.items())
            steps.append({
                "Transformation Step": f"Rename matching columns to target names: {rename_desc}",
                "Code": f"df = df.rename(columns={json.dumps(renames)})"
            })
            df = df.rename(columns=renames)

        # 2. Type Conformance & Cleaning
        for t_col in target_cols:
            if t_col not in df.columns:
                continue
            s_series = df[t_col]
            t_series = df_target[t_col]
            t_alteryx = infer_alteryx_type(t_series)
            s_alteryx = infer_alteryx_type(s_series)

            # 1. Case: Target is Bool
            if pd.api.types.is_bool_dtype(t_series) or t_alteryx == "Bool":
                if not pd.api.types.is_bool_dtype(s_series) or not pd.api.types.is_bool_dtype(df[t_col]):
                    steps.append({
                        "Transformation Step": f"Convert '{t_col}' to boolean flag",
                        "Code": f"df['{t_col}'] = df['{t_col}'].astype(str).str.strip().str.lower().isin(['true', '1', 'yes', 't', 'y'])"
                    })
                    df[t_col] = df[t_col].astype(str).str.strip().str.lower().isin(['true', '1', 'yes', 't', 'y'])

            # 2. Case: Target is Date/DateTime
            elif pd.api.types.is_datetime64_any_dtype(t_series) or t_alteryx in ("Date", "DateTime"):
                if not pd.api.types.is_datetime64_any_dtype(s_series) or not pd.api.types.is_datetime64_any_dtype(df[t_col]):
                    steps.append({
                        "Transformation Step": f"Parse date/time values in '{t_col}'",
                        "Code": f"df['{t_col}'] = pd.to_datetime(df['{t_col}'], errors='coerce')"
                    })
                    df[t_col] = pd.to_datetime(df[t_col], errors='coerce')

            # 3. Case: Target is Numeric (excluding Bool)
            elif (pd.api.types.is_numeric_dtype(t_series) or t_alteryx in ("Int64", "Int32", "Double", "Float")) and not pd.api.types.is_bool_dtype(t_series):
                if not pd.api.types.is_numeric_dtype(s_series) or not pd.api.types.is_numeric_dtype(df[t_col]) or s_alteryx == "String":
                    steps.append({
                        "Transformation Step": f"Clean numeric formatting and cast '{t_col}' to numeric",
                        "Code": f"df['{t_col}'] = pd.to_numeric(df['{t_col}'].astype(str).str.replace(r'[^0-9.-]', '', regex=True), errors='coerce')"
                    })
                    df[t_col] = pd.to_numeric(df[t_col].astype(str).str.replace(r'[^0-9.-]', '', regex=True), errors='coerce')

        # 3. Add Missing Target Columns
        missing = [t for t in target_cols if t not in df.columns]
        if missing:
            for m_col in missing:
                steps.append({
                    "Transformation Step": f"Initialize missing target column '{m_col}' with nulls",
                    "Code": f"df['{m_col}'] = np.nan"
                })
                df[m_col] = np.nan

        # 4. Filter / Reorder Columns
        if only_target_columns:
            ordered_cols = [c for c in target_cols if c in df.columns]
            steps.append({
                "Transformation Step": "Exclude non-target columns and align column sequence to target schema",
                "Code": f"df = df[{json.dumps(ordered_cols)}]"
            })
            df = df[ordered_cols]
        else:
            ordered_cols = [c for c in target_cols if c in df.columns]
            extra_cols = [c for c in df.columns if c not in target_cols]
            all_cols = ordered_cols + extra_cols
            steps.append({
                "Transformation Step": "Reorder columns with target schema first, retaining extra source columns",
                "Code": f"df = df[{json.dumps(all_cols)}]"
            })
            df = df[all_cols]

        return steps, df
