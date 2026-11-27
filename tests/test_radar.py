"""Local radar decoder regression tests; no network or HA required."""
import base64
import importlib.util
import io
import pathlib
import unittest
spec=importlib.util.spec_from_file_location("radar",pathlib.Path(__file__).resolve().parents[1]/"custom_components/tiny_liveboard/radar.py")
radar=importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)

class RadarTests(unittest.TestCase):
    def fixture(self):
        import h5py
        import numpy as np
        from pyproj import Transformer
        buf=io.BytesIO()
        transform=Transformer.from_crs("EPSG:4326","EPSG:3857",always_xy=True)
        left,bottom=transform.transform(0,0)
        right,top=transform.transform(45,40.97989806962013)
        with h5py.File(buf,"w") as f:
            w=f.create_group("where")
            w.attrs.update(dict(projdef="EPSG:3857",LL_lon=0.,LL_lat=0.,UR_lon=45.,UR_lat=40.97989806962013,xscale=(right-left)/4,yscale=(top-bottom)/4))
            d=f.create_group("dataset1/data1")
            d.create_group("what").attrs.update(dict(quantity="DBZH",gain=.5,offset=-32.,nodata=255,undetect=0))
            d.create_dataset("data",data=np.array([[255,0,144,144]]*4,dtype=np.uint8))
        return buf.getvalue()
    def test_invalid_tile(self):
        with self.assertRaises(ValueError):
            radar.decode_tile(b"",3,8,0)
    def test_transparency_and_reflectivity(self):
        from PIL import Image
        raw=radar.decode_tile(self.fixture(),3,4,3)
        image=Image.open(io.BytesIO(base64.b64decode(raw)))
        self.assertEqual(image.size,(256,256))
        self.assertEqual(image.getpixel((20,128))[3],0)
        self.assertEqual(image.getpixel((90,128))[3],0)
        self.assertGreater(image.getpixel((220,128))[3],0)
