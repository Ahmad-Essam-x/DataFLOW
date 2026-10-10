"""
Alteryx Compatibility & Ingestion Package.
Provides native parsing of .yxmd workflows and .yxzp packaged archives
with 25+ tool mappers and graceful fallback nodes.
"""
from .models import ConversionWarning, YxmdParseResult
from .tool_mappers import ALTERYX_TOOL_MAPPERS, resolve_tool_mapper, map_alteryx_type
from .yxmd_parser import parse_yxmd_content, parse_yxmd_file
from .package_importer import import_yxzp_package

__all__ = [
    "ConversionWarning",
    "YxmdParseResult",
    "ALTERYX_TOOL_MAPPERS",
    "resolve_tool_mapper",
    "map_alteryx_type",
    "parse_yxmd_content",
    "parse_yxmd_file",
    "import_yxzp_package",
]
