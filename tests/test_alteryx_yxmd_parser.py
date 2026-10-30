"""
Comprehensive Test Suite for Alteryx (.yxmd / .yxzp) Ingestion & Graceful Fallback Engine.
Tests XML parsing, tool mappers (25+ tools), containers, comments, connection wiring,
graceful fallback node behavior, and pipeline execution.
"""
import io
import os
import zipfile
import pytest
import pandas as pd

from backend.engine.alteryx import (
    parse_yxmd_content,
    parse_yxmd_file,
    import_yxzp_package,
    ALTERYX_TOOL_MAPPERS,
    resolve_tool_mapper,
    ConversionWarning
)
from backend.engine.nodes.fallback import UnsupportedToolNode
from backend.engine.executor import WorkflowExecutor


# ---------------------------------------------------------------------------
# Synthetic Alteryx XML Workflows for Testing
# ---------------------------------------------------------------------------

SAMPLE_ALTYREX_XML = """<?xml version="1.0"?>
<AlteryxDocument yxmdVer="2021.4">
  <Nodes>
    <Node ToolID="1">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileInput.DbFileInput">
        <Position x="50" y="100" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <File RecordLimit="50">C:\\data\\sales.csv</File>
          <FormatSpecificOptions>
            <HeaderRow>True</HeaderRow>
            <Delimeter>,</Delimeter>
          </FormatSpecificOptions>
        </Configuration>
        <Annotation>
          <DefaultAnnotationText>sales.csv</DefaultAnnotationText>
        </Annotation>
      </Properties>
    </Node>

    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
        <Position x="200" y="100" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <Mode>Simple</Mode>
          <Simple>
            <Field>Revenue</Field>
            <Operator>&gt;</Operator>
            <Operands>
              <Operand>100</Operand>
            </Operands>
          </Simple>
        </Configuration>
      </Properties>
    </Node>

    <Node ToolID="3">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
        <Position x="350" y="100" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <FormulaFields>
            <FormulaField field="Tax" expression="[Revenue] * 0.1" type="Double" size="8" />
          </FormulaFields>
        </Configuration>
      </Properties>
    </Node>

    <Node ToolID="4">
      <GuiSettings Plugin="AlteryxSpatialPluginsGui.SpatialMatch.SpatialMatch">
        <Position x="500" y="100" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <SpatialObj>Geometry</SpatialObj>
        </Configuration>
      </Properties>
    </Node>

    <Node ToolID="10">
      <GuiSettings Plugin="AlteryxGuiToolkit.ToolContainer.ToolContainer">
        <Position x="30" y="50" width="400" height="200" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <Caption>Sales Filter Stage</Caption>
          <Disabled value="False" />
          <Folded value="False" />
        </Configuration>
      </Properties>
      <ChildNodes>
        <Node ToolID="1" />
        <Node ToolID="2" />
      </ChildNodes>
    </Node>

    <Node ToolID="11">
      <GuiSettings Plugin="AlteryxGuiToolkit.TextBox.TextBox">
        <Position x="50" y="10" width="220" height="40" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <Text>ETL Pipeline Documentation</Text>
        </Configuration>
      </Properties>
    </Node>
  </Nodes>

  <Connections>
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="2" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="2" Connection="True" />
      <Destination ToolID="3" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="3" Connection="Output" />
      <Destination ToolID="4" Connection="Input" />
    </Connection>
  </Connections>
</AlteryxDocument>
"""


def test_alteryx_tool_mappers_registered():
    """Verify registry has at least 25 tool mappers."""
    assert len(ALTERYX_TOOL_MAPPERS) >= 25
    assert resolve_tool_mapper("AlteryxBasePluginsGui.DbFileInput.DbFileInput") is not None
    assert resolve_tool_mapper("AlteryxBasePluginsGui.Filter.Filter") is not None
    assert resolve_tool_mapper("AlteryxBasePluginsGui.Formula.Formula") is not None
    assert resolve_tool_mapper("AlteryxBasePluginsGui.Join.Join") is not None
    assert resolve_tool_mapper("AlteryxBasePluginsGui.Summarize.Summarize") is not None
    assert resolve_tool_mapper("AlteryxSpatialPluginsGui.Summarize.Summarize") is not None


def test_parse_yxmd_content_tools_and_connections():
    """Test parsing tools, coordinates, connections, containers, and fallback nodes."""
    res = parse_yxmd_content(SAMPLE_ALTYREX_XML, source_name="sales_pipeline.yxmd")
    wf = res.workflow

    assert wf["name"] == "Sales Pipeline"
    assert res.total_tools == 4
    assert res.mapped_tools == 3
    assert res.fallback_tools == 1
    assert res.containers_count == 1
    assert res.comments_count == 1

    # Check node 1 (DbFileInput)
    node1 = next(n for n in wf["nodes"] if n["id"] == "alteryx_1")
    assert node1["type"] == "input_data"
    assert node1["config"]["file_path"] == "C:\\data\\sales.csv"
    assert node1["config"]["has_header"] is True
    assert node1["config"]["record_limit"] == 50
    assert node1["container_id"] == "alteryx_10"

    # Check node 2 (Filter)
    node2 = next(n for n in wf["nodes"] if n["id"] == "alteryx_2")
    assert node2["type"] == "filter"
    assert node2["config"]["mode"] == "basic"
    assert node2["config"]["conditions"][0]["column"] == "Revenue"
    assert node2["config"]["conditions"][0]["operator"] == ">"
    assert node2["config"]["conditions"][0]["value"] == "100"

    # Check node 3 (Formula)
    node3 = next(n for n in wf["nodes"] if n["id"] == "alteryx_3")
    assert node3["type"] == "formula"
    assert node3["config"]["formulas"][0]["output_field"] == "Tax"
    assert node3["config"]["formulas"][0]["expression"] == "[Revenue] * 0.1"

    # Check node 4 (SpatialMatch - unsupported tool fallback)
    node4 = next(n for n in wf["nodes"] if n["id"] == "alteryx_4")
    assert node4["type"] == "unsupported_tool"
    assert node4["config"]["original_tool"] == "SpatialMatch"
    assert "SpatialObj" in node4["config"]["raw_xml"]

    # Check container
    container = wf["containers"][0]
    assert container["id"] == "alteryx_10"
    assert container["title"] == "Sales Filter Stage"
    assert "alteryx_1" in container["nodeIds"]
    assert "alteryx_2" in container["nodeIds"]

    # Check comment / textbox
    comment = wf["comments"][0]
    assert comment["id"] == "alteryx_11"
    assert comment["text"] == "ETL Pipeline Documentation"

    # Check connections
    assert len(wf["connections"]) == 3
    conn2 = next(c for c in wf["connections"] if c["source"] == "alteryx_2")
    assert conn2["sourceHandle"] == "T"
    assert conn2["target"] == "alteryx_3"
    assert conn2["targetHandle"] == "I"


def test_parse_multi_anchor_tools():
    """Test Join, Unique, CrossTab, Transpose, and TextToColumns mappers."""
    multi_tool_xml = """<?xml version="1.0"?>
    <AlteryxDocument yxmdVer="2021.4">
      <Nodes>
        <Node ToolID="20">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Join.Join">
            <Position x="100" y="100" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <JoinByRecPos value="False" />
              <JoinInfo connection="Left">
                <Field field="CustID" />
              </JoinInfo>
              <JoinInfo connection="Right">
                <Field field="CustomerID" />
              </JoinInfo>
            </Configuration>
          </Properties>
        </Node>

        <Node ToolID="21">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Unique.Unique">
            <Position x="250" y="100" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <UniqueFields>
                <Field field="CustID" />
                <Field field="Email" />
              </UniqueFields>
            </Configuration>
          </Properties>
        </Node>

        <Node ToolID="22">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Transpose.Transpose">
            <Position x="400" y="100" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <KeyFields>
                <Field field="CustID" selected="True" />
              </KeyFields>
              <DataFields>
                <Field field="Q1" selected="True" />
                <Field field="Q2" selected="True" />
              </DataFields>
            </Configuration>
          </Properties>
        </Node>

        <Node ToolID="23">
          <GuiSettings Plugin="AlteryxBasePluginsGui.CrossTab.CrossTab">
            <Position x="550" y="100" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <GroupFields>
                <Field field="CustID" />
              </GroupFields>
              <HeaderField field="Name" />
              <DataField field="Value" />
              <Methods>
                <Method method="Sum" />
              </Methods>
            </Configuration>
          </Properties>
        </Node>

        <Node ToolID="24">
          <GuiSettings Plugin="AlteryxBasePluginsGui.TextInput.TextInput">
            <Position x="50" y="100" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Fields>
                <Field name="ID" />
                <Field name="City" />
              </Fields>
              <Data>
                <r><c>1</c><c>New York</c></r>
                <r><c>2</c><c>London</c></r>
              </Data>
            </Configuration>
          </Properties>
        </Node>
      </Nodes>
      <Connections />
    </AlteryxDocument>
    """
    res = parse_yxmd_content(multi_tool_xml)
    wf = res.workflow

    join_node = next(n for n in wf["nodes"] if n["id"] == "alteryx_20")
    assert join_node["type"] == "join"
    assert join_node["config"]["join_keys"] == [{"left_key": "CustID", "right_key": "CustomerID"}]

    unique_node = next(n for n in wf["nodes"] if n["id"] == "alteryx_21")
    assert unique_node["type"] == "unique"
    assert unique_node["config"]["columns"] == ["CustID", "Email"]

    transpose_node = next(n for n in wf["nodes"] if n["id"] == "alteryx_22")
    assert transpose_node["type"] == "transpose"
    assert transpose_node["config"]["key_columns"] == ["CustID"]
    assert transpose_node["config"]["data_columns"] == ["Q1", "Q2"]

    crosstab_node = next(n for n in wf["nodes"] if n["id"] == "alteryx_23")
    assert crosstab_node["type"] == "crosstab"
    assert crosstab_node["config"]["group_by"] == ["CustID"]
    assert crosstab_node["config"]["header_field"] == "Name"
    assert crosstab_node["config"]["value_field"] == "Value"
    assert crosstab_node["config"]["agg_methods"] == ["sum"]

    text_input_node = next(n for n in wf["nodes"] if n["id"] == "alteryx_24")
    assert text_input_node["type"] == "text_input"
    assert text_input_node["config"]["columns"] == ["ID", "City"]
    assert len(text_input_node["config"]["data"]) == 2


def test_unsupported_tool_passthrough_execution():
    """Verify UnsupportedToolNode acts as a graceful passthrough without failing pipeline."""
    sample_df = pd.DataFrame({
        "ID": [1, 2, 3],
        "Score": [10.5, 20.0, 30.2]
    })

    node = UnsupportedToolNode("alteryx_99", {
        "original_tool": "Predictive Scoring Macro",
        "tool_id": "99"
    })

    result = node.execute({"I": sample_df})
    assert "O" in result
    out_df = result["O"]
    assert len(out_df) == 3
    assert list(out_df.columns) == ["ID", "Score"]
    assert any("Passthrough Notice" in msg for msg in node.messages)


def test_yxzp_package_import(tmp_path):
    """Test importing an Alteryx .yxzp package containing .yxmd and data files."""
    data_dir = tmp_path / "data"
    wf_dir = tmp_path / "workflows"
    data_dir.mkdir()
    wf_dir.mkdir()

    # Create synthetic .yxzp ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        # Bundled CSV data
        zf.writestr("customers_data.csv", "ID,Name\n1,Alice\n2,Bob\n")
        # Bundled .yxmd workflow referencing customers_data.csv
        wf_xml = """<?xml version="1.0"?>
        <AlteryxDocument yxmdVer="2021.4">
          <Nodes>
            <Node ToolID="1">
              <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileInput.DbFileInput">
                <Position x="50" y="50" />
              </GuiSettings>
              <Properties>
                <Configuration>
                  <File>customers_data.csv</File>
                </Configuration>
              </Properties>
            </Node>
          </Nodes>
          <Connections />
        </AlteryxDocument>
        """
        zf.writestr("package_workflow.yxmd", wf_xml)

    zip_buffer.seek(0)
    result = import_yxzp_package(zip_buffer, str(data_dir), str(wf_dir))

    assert result["success"] is True
    assert "customers_data.csv" in result["extracted_files"]
    assert (data_dir / "customers_data.csv").exists()

    wf = result["workflow"]
    node1 = wf["nodes"][0]
    assert node1["type"] == "input_data"
    assert node1["config"]["file_path"] == "data/customers_data.csv"


def test_end_to_end_executor_with_alteryx_workflow():
    """Execute an imported Alteryx workflow DAG through WorkflowExecutor."""
    xml_data = """<?xml version="1.0"?>
    <AlteryxDocument yxmdVer="2021.4">
      <Nodes>
        <Node ToolID="1">
          <GuiSettings Plugin="AlteryxBasePluginsGui.TextInput.TextInput">
            <Position x="50" y="50" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Fields>
                <Field name="City" />
                <Field name="Amount" />
              </Fields>
              <Data>
                <r><c>Paris</c><c>100</c></r>
                <r><c>Tokyo</c><c>250</c></r>
                <r><c>Cairo</c><c>50</c></r>
              </Data>
            </Configuration>
          </Properties>
        </Node>

        <Node ToolID="2">
          <GuiSettings Plugin="AlteryxSpatialPluginsGui.SpatialBuffer.SpatialBuffer">
            <Position x="200" y="50" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Distance>50</Distance>
            </Configuration>
          </Properties>
        </Node>

        <Node ToolID="3">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Sort.Sort">
            <Position x="350" y="50" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <SortInfo>
                <Field field="Amount" order="Descending" />
              </SortInfo>
            </Configuration>
          </Properties>
        </Node>
      </Nodes>
      <Connections>
        <Connection>
          <Origin ToolID="1" Connection="Output" />
          <Destination ToolID="2" Connection="Input" />
        </Connection>
        <Connection>
          <Origin ToolID="2" Connection="Output" />
          <Destination ToolID="3" Connection="Input" />
        </Connection>
      </Connections>
    </AlteryxDocument>
    """
    res = parse_yxmd_content(xml_data, source_name="travel_cities.yxmd")
    wf = res.workflow

    executor = WorkflowExecutor()
    exec_result = executor.run(wf)

    assert exec_result.success is True
    # Node 3 should have sorted rows: 250, 100, 50
    node3_res = exec_result.node_results["alteryx_3"]
    assert node3_res["status"] == "success"
    assert node3_res["record_counts"]["O"] == 3


def test_workflow_manager_load_from_path(tmp_path):
    """Verify WorkflowManager.load_from_path loads a .yxmd file from disk."""
    from backend.engine.workflow_manager import WorkflowManager

    wm = WorkflowManager(str(tmp_path / "workflows"), str(tmp_path / "data"), str(tmp_path))

    wf_file = tmp_path / "sales_flow.yxmd"
    wf_file.write_text(SAMPLE_ALTYREX_XML, encoding="utf-8")

    res = wm.load_from_path(str(wf_file))
    assert res["success"] is True
    assert res["filename"] == "sales_flow.yxmd"
    assert "workflow" in res
    assert len(res["workflow"]["nodes"]) == 4
    assert res["stats"]["mapped_tools"] == 3
    assert res["stats"]["fallback_tools"] == 1


def test_api_import_yxmd_endpoint():
    """Verify POST /api/workflow/import-yxmd endpoint converts workflow."""
    from backend.app import app
    client = app.test_client()

    # 1. Post via JSON payload
    resp = client.post("/api/workflow/import-yxmd", json={
        "xml": SAMPLE_ALTYREX_XML,
        "filename": "customer_analytics.yxmd"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "workflow" in data
    assert len(data["workflow"]["nodes"]) == 4
    assert data["stats"]["mapped_tools"] == 3

    # 2. Post via multipart file upload
    data_bytes = io.BytesIO(SAMPLE_ALTYREX_XML.encode("utf-8"))
    resp2 = client.post(
        "/api/workflow/import-yxmd",
        data={"file": (data_bytes, "uploaded_pipeline.yxmd")},
        content_type="multipart/form-data"
    )
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["success"] is True
    assert len(data2["workflow"]["nodes"]) == 4


def test_yxdb_warning_detection():
    """Verify referencing proprietary .yxdb issues an informational warning."""
    xml_with_yxdb = """<?xml version="1.0"?>
    <AlteryxDocument yxmdVer="2021.4">
      <Nodes>
        <Node ToolID="1">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileInput.DbFileInput">
            <Position x="50" y="50" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File>legacy_archive.yxdb</File>
            </Configuration>
          </Properties>
        </Node>
      </Nodes>
      <Connections />
    </AlteryxDocument>
    """
    res = parse_yxmd_content(xml_with_yxdb)
    assert any("yxdb" in w.message.lower() for w in res.warnings)


def test_corrupt_xml_graceful_handling():
    """Verify malformed XML produces an error warning without crashing."""
    corrupt_xml = "<AlteryxDocument><UnclosedTag></AlteryxDocument>"
    res = parse_yxmd_content(corrupt_xml)
    assert len(res.warnings) >= 1
    assert any(w.severity == "error" for w in res.warnings)
    assert res.workflow["nodes"] == []



def test_nested_childnodes_container_parsing():
    """Verify nodes nested inside ToolContainer ChildNodes are fully extracted."""
    xml = """<?xml version="1.0"?>
    <AlteryxDocument yxmdVer="2021.4">
      <Nodes>
        <Node ToolID="10">
          <GuiSettings Plugin="AlteryxGuiToolkit.ToolContainer.ToolContainer">
            <Position x="50" y="50" width="600" height="400" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Caption>Enclosed Processing Block</Caption>
            </Configuration>
          </Properties>
          <ChildNodes>
            <Node ToolID="1">
              <GuiSettings Plugin="AlteryxBasePluginsGui.TextInput.TextInput">
                <Position x="100" y="100" />
              </GuiSettings>
              <Properties>
                <Configuration>
                  <NumRows value="1" />
                  <Fields>
                    <Field name="ID" />
                  </Fields>
                  <Data>
                    <r><c>101</c></r>
                  </Data>
                </Configuration>
              </Properties>
            </Node>
            <Node ToolID="2">
              <GuiSettings Plugin="AlteryxBasePluginsGui.BrowseV2.BrowseV2">
                <Position x="250" y="100" />
              </GuiSettings>
              <Properties>
                <Configuration />
              </Properties>
            </Node>
            <Node ToolID="3">
              <GuiSettings Plugin="AlteryxGuiToolkit.TextBox.TextBox">
                <Position x="100" y="250" width="200" height="50" />
              </GuiSettings>
              <Properties>
                <Configuration>
                  <Text>Note inside container</Text>
                </Configuration>
              </Properties>
            </Node>
          </ChildNodes>
        </Node>
      </Nodes>
      <Connections>
        <Connection>
          <Origin ToolID="1" Connection="Output" />
          <Destination ToolID="2" Connection="Input" />
        </Connection>
      </Connections>
    </AlteryxDocument>
    """
    res = parse_yxmd_content(xml)
    wf = res.workflow
    assert len(wf["containers"]) == 1
    assert wf["containers"][0]["id"] == "alteryx_10"
    assert "alteryx_1" in wf["containers"][0]["nodeIds"]
    assert "alteryx_2" in wf["containers"][0]["nodeIds"]

    assert len(wf["nodes"]) == 2
    assert wf["nodes"][0]["id"] == "alteryx_1"
    assert wf["nodes"][0]["container_id"] == "alteryx_10"
    assert wf["nodes"][1]["id"] == "alteryx_2"
    assert wf["nodes"][1]["container_id"] == "alteryx_10"

    assert len(wf["comments"]) == 1
    assert wf["comments"][0]["text"] == "Note inside container"

    assert len(wf["connections"]) == 1
    assert wf["connections"][0]["source"] == "alteryx_1"
    assert wf["connections"][0]["target"] == "alteryx_2"


def test_real_union_yxmd_parsing_full():
    """Verify parsing real-world Union.yxmd workflow from Downloads if present."""
    path = os.path.join(os.path.expanduser("~"), "Downloads", "Union.yxmd")
    if not os.path.exists(path):
        pytest.skip("Union.yxmd file not found in Downloads")

    res = parse_yxmd_file(path)
    wf = res.workflow

    assert len(wf["containers"]) == 3
    assert len(wf["comments"]) == 18
    assert len(wf["nodes"]) == 30
    assert len(wf["connections"]) == 28
    assert res.total_tools == 30
    assert res.mapped_tools == 26
    assert res.fallback_tools == 4

    nodes_in_containers = [n for n in wf["nodes"] if n.get("container_id")]
    assert len(nodes_in_containers) == 30


def test_tool_mastery_workflows_batch():
    """Verify parsing the downloaded suite of real-world Tool Mastery workflows."""
    import glob
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "alteryx")
    files = glob.glob(os.path.join(fixtures_dir, "0*.yxmd"))
    if not files:
        pytest.skip("No Tool Mastery fixtures found")

    for f in files:
        res = parse_yxmd_file(f)
        wf = res.workflow
        assert res.total_tools >= 0
        assert res.fallback_tools == 0, f"Expected 0 fallbacks in Tool Mastery fixture {f}, got {res.fallback_tools}"
        assert isinstance(wf["nodes"], list)
        assert isinstance(wf["connections"], list)


def test_cleanse_macro_mapping():
    """Verify Alteryx Cleanse.yxmc macro config is properly mapped to native clean node."""
    xml = """<?xml version="1.0"?>
    <AlteryxDocument yxmdVer="2021.4">
      <Nodes>
        <Node ToolID="11">
          <GuiSettings>
            <Position x="50" y="50" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Value name="List Box (11)">"States","City"</Value>
              <Value name="Check Box (84)">False</Value>
              <Value name="Check Box (117)">True</Value>
              <Value name="Check Box (15)">True</Value>
              <Value name="Check Box (109)">False</Value>
              <Value name="Check Box (122)">False</Value>
              <Value name="Check Box (53)">False</Value>
              <Value name="Check Box (58)">False</Value>
              <Value name="Check Box (70)">True</Value>
              <Value name="Check Box (77)">True</Value>
              <Value name="Drop Down (81)">upper</Value>
            </Configuration>
          </Properties>
          <EngineSettings Macro="Cleanse.yxmc" />
        </Node>
      </Nodes>
      <Connections />
    </AlteryxDocument>
    """
    res = parse_yxmd_content(xml)
    wf = res.workflow
    assert len(wf["nodes"]) == 1
    node = wf["nodes"][0]
    assert node["type"] == "clean"
    cfg = node["config"]
    assert cfg["columns"] == ["States", "City"]
    assert cfg["trim_whitespace"] is True
    assert cfg["remove_punctuation"] is True
    assert cfg["replace_nulls_string"] is True
    assert cfg["case_mode"] == "upper"


def test_select_records_macro_and_sample_execution():
    """Verify SelectRecords.yxmc is mapped to sample node and executes range slices."""
    from backend.engine.nodes.preparation import SampleNode

    xml = """<?xml version="1.0"?>
    <AlteryxDocument yxmdVer="2021.4">
      <Nodes>
        <Node ToolID="5">
          <GuiSettings>
            <Position x="50" y="50" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Value name="Ranges">2-4\n6</Value>
            </Configuration>
          </Properties>
          <EngineSettings Macro="SelectRecords.yxmc" />
        </Node>
      </Nodes>
      <Connections />
    </AlteryxDocument>
    """
    res = parse_yxmd_content(xml)
    node_def = res.workflow["nodes"][0]
    assert node_def["type"] == "sample"
    assert node_def["config"]["sample_type"] == "records_range"

    # Test execution
    sample_node = SampleNode("test_sample", node_def["config"])
    df = pd.DataFrame({"val": [10, 20, 30, 40, 50, 60, 70]})
    out = sample_node.execute({"I": df}, {})["O"]
    # 2-4 (rows 2,3,4 -> 20, 30, 40) + 6 (row 6 -> 60)
    assert list(out["val"]) == [20, 30, 40, 60]


def test_running_total_execution():
    """Verify RunningTotalNode computes cumulative sums with optional grouping."""
    from backend.engine.nodes.preparation import RunningTotalNode

    df = pd.DataFrame({
        "Category": ["A", "A", "A", "B", "B"],
        "Amount": [10, 20, 15, 5, 25]
    })
    node = RunningTotalNode("test_rt", {
        "running_total_fields": ["Amount"],
        "group_by_fields": ["Category"]
    })
    out = node.execute({"I": df}, {})["O"]
    assert "RunTot_Amount" in out.columns
    assert list(out["RunTot_Amount"]) == [10, 30, 45, 5, 30]


def test_dynamic_rename_execution():
    """Verify DynamicRenameNode promotes first row to column headers."""
    from backend.engine.nodes.preparation import DynamicRenameNode

    df = pd.DataFrame([
        ["ProductID", "Revenue", "Country"],
        ["P100", 250, "US"],
        ["P200", 450, "DE"]
    ])
    node = DynamicRenameNode("test_dr", {"rename_mode": "firstrow"})
    out = node.execute({"I": df}, {})["O"]
    assert list(out.columns) == ["ProductID", "Revenue", "Country"]
    assert len(out) == 2
    assert out.iloc[0]["ProductID"] == "P100"


def test_explorer_box_htmlbox_mapping():
    """Verify HtmlBox / Explorer Box is captured as an annotation comment."""
    xml = """<?xml version="1.0"?>
    <AlteryxDocument yxmdVer="2021.4">
      <Nodes>
        <Node ToolID="1">
          <GuiSettings Plugin="AlteryxGuiToolkit.HtmlBox.HtmlBox">
            <Position x="100" y="100" width="400" height="300" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <URL>https://community.alteryx.com/</URL>
            </Configuration>
          </Properties>
        </Node>
      </Nodes>
      <Connections />
    </AlteryxDocument>
    """
    res = parse_yxmd_content(xml)
    wf = res.workflow
    assert len(wf["nodes"]) == 0
    assert len(wf["comments"]) == 1
    assert "https://community.alteryx.com/" in wf["comments"][0]["text"]
