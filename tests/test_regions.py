import importlib.util
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("regions", Path(__file__).parents[1] / "custom_components/tiny_liveboard/regions.py")
regions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regions)

RING = [[10,55],[11,55],[11,56],[10,55]]

def dataset(tmp_path, ring=RING):
    path = tmp_path / "regions.geojson"
    path.write_text(json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{"EMMA_ID":"DK_TEST"},"geometry":{"type":"Polygon","coordinates":[ring]}}]}))
    return path

def test_missing_dataset(tmp_path):
    assert regions.load_regions(tmp_path / "missing.json") == {}

def test_resolve(tmp_path):
    index = regions.load_regions(dataset(tmp_path))
    item = {"geocodes":[{"name":"EMMA_ID","value":"DK_TEST"}],"geometry_status":"unresolved_region"}
    result = regions.resolve_regions(item,index)
    assert result["geometry"]["coordinates"] == [[RING]]
    assert result["geometry_source"] == "EMMA_ID"
    assert "geometry" not in item
    assert regions.resolve_regions(dict(item,geometry_status="invalid"),index).get("geometry") is None

def test_partial_match_not_local(tmp_path):
    index = regions.load_regions(dataset(tmp_path))
    item = {"geocodes":[{"name":"EMMA_ID","value":"DK_TEST"},{"name":"EMMA_ID","value":"DK_UNKNOWN"}]}
    assert regions.resolve_regions(item,index) == item

@pytest.mark.parametrize("ring", [[[10,55],[11,55],[11,56]], [[10,95],[11,55],[11,56],[10,95]], [[10,55]]*4])
def test_invalid_geometry(tmp_path,ring):
    with pytest.raises(ValueError):
        regions.load_regions(dataset(tmp_path,ring))
