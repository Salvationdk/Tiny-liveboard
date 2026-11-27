import ast
import pathlib
import unittest
from copy import deepcopy

source=pathlib.Path(__file__).resolve().parents[1]/"custom_components/tiny_liveboard/__init__.py"
tree=ast.parse(source.read_text(encoding="utf-8"))
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ("validate_screen_config","validate_layout")]
ns={}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),"exec"),ns)
validate=ns["validate_screen_config"]

class ScreenConfigTests(unittest.TestCase):
    def setUp(self):
        self.config={"profiles":{"Day":{},"Night":{}},"screens":{"kitchen":"Day"},"schedules":[{"screen":"kitchen","profile":"Night","days":[1,2],"start":"22:00","end":"07:00"}]}
    def test_valid_overnight(self):
        self.assertEqual(validate(self.config),self.config)
    def test_empty_legacy(self):
        self.assertEqual(validate({}),{})
    def test_invalid_rules(self):
        for key,value in [("days",[True]),("days",[]),("days",[7]),("start","24:00"),("end","22:00"),("profile","missing"),("screen","missing")]:
            with self.subTest(key=key,value=value):
                config=deepcopy(self.config)
                config["schedules"][0][key]=value
                with self.assertRaises(ValueError): validate(config)
    def test_unknown_assignment(self):
        self.config["screens"]["kitchen"]="missing"
        with self.assertRaises(ValueError): validate(self.config)
    def test_oversized(self):
        self.config["extra"]="x"*524288
        with self.assertRaises(ValueError): validate(self.config)

    def test_widget_geometry(self):
        self.config["widgets"]=[{"entity":"sensor.temperature","x":5,"y":5,"w":25,"h":20,"z":1}]
        self.assertEqual(validate(self.config),self.config)
        self.config["widgets"][0]["w"]=100
        with self.assertRaises(ValueError): validate(self.config)
    def test_invalid_profile_layout(self):
        self.config["profiles"]["Night"]["layout"]={"c0":{"x":0,"y":0,"w":50,"h":50}}
        with self.assertRaises(ValueError): validate(self.config)
    def test_lovelace_requires_card(self):
        self.config["widgets"]=[{"kind":"lovelace","x":0,"y":0,"w":50,"h":50,"z":1}]
        with self.assertRaises(ValueError): validate(self.config)
    def test_invalid_layer(self):
        self.config["layers"]={"weather":10}
        with self.assertRaises(ValueError): validate(self.config)
