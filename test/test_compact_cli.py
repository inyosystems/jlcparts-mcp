from click.testing import CliRunner

from jlcparts.ui import cli
from test_compact_index import build_upstream_catalog_fixture


def test_cli_exposes_compact_commands_and_hides_official_refresh():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "download-catalog" in result.output
    assert "build-index" in result.output
    assert "mcp" in result.output
    assert "enrich-cache" not in result.output
    assert "refresh-cache" not in result.output
    assert "fetchdb" not in result.output
    assert "fetchtable" not in result.output
    assert "fetchdetails" not in result.output
    assert "getlibrary" not in result.output
    assert "listcategories" not in result.output
    assert "listattributes" not in result.output
    assert "buildtables" not in result.output
    assert "buildwebdb" not in result.output
    assert "migratecache" not in result.output
    assert "updatepreferred" not in result.output
    assert "testcomponent" not in result.output


def test_build_index_cli_builds_compact_index(tmp_path):
    catalog_path = build_upstream_catalog_fixture(tmp_path / "catalog")
    index_path = tmp_path / "mcp-index.sqlite3"

    result = CliRunner().invoke(
        cli,
        [
            "build-index",
            "--catalog",
            str(catalog_path),
            "--index",
            str(index_path),
            "--force",
            "--progress-interval",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert index_path.exists()
    assert '"component_count": 3' in result.output
