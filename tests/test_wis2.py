import asyncio
import json
import pathlib
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch
root=pathlib.Path(__file__).resolve().parents[1]/"custom_components/tiny_liveboard"
pkg=types.ModuleType("wis2_fixture")
pkg.__path__=[str(root)]
sys.modules[pkg.__name__]=pkg
news=types.ModuleType("wis2_fixture.news")
def timestamp(value):
    try: return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()
    except (ValueError,AttributeError): return None
news.timestamp=timestamp
sys.modules[news.__name__]=news
from wis2_fixture.wis2 import WIS2Client, notification,parse_cap,WarningIndex,exact_geometry

class Wis2Tests(unittest.TestCase):
    def notice(self):
        return {"type":"Feature","properties":{"countryCode":"DK","alertId":"cancel"},"links":[{"rel":"xml","href":"https://api.meteoalarm.org/cap.xml"}]}
    def test_cancel_without_geometry(self):
        notice=notification(json.dumps(self.notice()).encode())
        self.assertIsNotNone(notice)
        cap=b'<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>cancel</identifier><status>Actual</status><scope>Public</scope><msgType>Cancel</msgType><sent>2026-11-27T12:00:00Z</sent><references>sender,old,2026-11-27T11:00:00Z</references></alert>'
        event=parse_cap(cap,notice)
        self.assertEqual(event["references"],["old"])
        index=WarningIndex()
        index.apply(event,"cancel",event["sent"])
        index.apply({"id":"old","sent":event["sent"]-60,"references":[],"items":[{"expires":"2026-11-28T12:00:00Z"}]},"old",event["sent"])
        self.assertEqual(index.items(event["sent"]),[])
    def test_reject_insecure_resource(self):
        data=self.notice()
        data["links"][0]["href"]="http://api.meteoalarm.org/cap.xml"
        with self.assertRaises(ValueError): notification(json.dumps(data).encode())
    def test_reject_invalid_polygon(self):
        with self.assertRaises(ValueError): exact_geometry(b'{"type":"Polygon","coordinates":[]}')
    def test_other_country(self):
        data=self.notice()
        data["properties"]["countryCode"]="DE"
        self.assertIsNone(notification(json.dumps(data).encode()))


class Wis2LifecycleTests(unittest.IsolatedAsyncioTestCase):
    class MqttError(Exception):
        pass

    class Hass:
        async def async_add_executor_job(self, job, *args):
            return await asyncio.to_thread(job, *args)

        def async_create_background_task(self, coro, name):
            return asyncio.create_task(coro, name=name)

    async def test_broker_outage_retries_and_stops(self):
        retried = asyncio.Event()
        attempts = 0
        error = self.MqttError

        class OfflineBroker:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                nonlocal attempts
                attempts += 1
                if attempts == 2:
                    retried.set()
                raise error("broker unavailable")

            async def __aexit__(self, *args):
                return False

        module = types.SimpleNamespace(Client=OfflineBroker, MqttError=error)
        client = WIS2Client(self.Hass())
        with patch("wis2_fixture.wis2.import_module", return_value=module), patch(
            "wis2_fixture.wis2.RETRY_MIN", 0.001
        ):
            client.start()
            try:
                await asyncio.wait_for(retried.wait(), 2)
                self.assertFalse(client.connected)
            finally:
                await client.stop()
        self.assertIsNone(client.task)

    async def test_tls_initialization_failure_leaves_atom_available(self):
        client = WIS2Client(self.Hass())
        with patch("wis2_fixture.wis2.import_module", return_value=object()), patch(
            "wis2_fixture.wis2.ssl.create_default_context", side_effect=OSError("certs unavailable")
        ):
            client.start()
            await asyncio.wait_for(client.task, 2)
            self.assertFalse(client.connected)
        await client.stop()
        self.assertIsNone(client.task)
