"""Offline business and MCP protocol integration tests; run after building the UI."""
import copy
import json
import logging
import unittest
from unittest.mock import patch

from fastmcp import Client, FastMCP
from fastmcp.server import create_proxy
from gateway.gateway import register_nearby_ui_alias

from mcp_servers.holidays.server import (
    HOLIDAY_CATALOG, mcp, nearby_holidays,
)


class NearbyDistanceTests(unittest.TestCase):
    def test_same_location_and_radius_filter(self):
        result = nearby_holidays(48.8566, 2.3522, 1)
        self.assertEqual([h["destination"] for h in result], ["Paris"])
        self.assertEqual(result[0]["distance_km"], 0)

    def test_known_distance_order_and_catalog_not_mutated(self):
        before = copy.deepcopy(HOLIDAY_CATALOG)
        result = nearby_holidays(51.5074, -0.1278, 1000)
        self.assertEqual([h["destination"] for h in result], ["Paris", "Swiss Alps"])
        self.assertAlmostEqual(result[0]["distance_km"], 343.56, delta=1)
        self.assertEqual(HOLIDAY_CATALOG, before)

    def test_empty_and_global_radius(self):
        self.assertEqual(nearby_holidays(0, 0, 1), [])
        self.assertEqual(len(nearby_holidays(0, 0, 20050)), len(HOLIDAY_CATALOG))

    def test_radius_boundary_is_compared_before_rounding(self):
        self.assertEqual(nearby_holidays(51.5074, -0.1278, 343.55), [])
        self.assertEqual(nearby_holidays(51.5074, -0.1278, 343.57)[0]["destination"], "Paris")

    def test_poles_and_antimeridian_are_finite(self):
        for lat, lon in [(90, 180), (-90, -180), (0, 180), (0, -180)]:
            self.assertEqual(len(nearby_holidays(lat, lon, 20050)), 6)
        self.assertEqual(nearby_holidays(0, 180, 20050), nearby_holidays(0, -180, 20050))

    def test_invalid_ranges_and_non_finite(self):
        for args in [(91, 0, 1), (-91, 0, 1), (0, 181, 1), (0, -181, 1),
                     (0, 0, 0), (0, 0, -1), (0, 0, 20051),
                     (float("nan"), 0, 1), (0, float("inf"), 1), (0, 0, float("nan"))]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                nearby_holidays(*args)


class NearbyMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_holiday_tools_remain_available_and_unchanged(self):
        async with Client(mcp) as client:
            catalog = await client.call_tool("list_holidays", {})
            self.assertEqual(len(catalog.data), len(HOLIDAY_CATALOG))
            self.assertTrue(all("distance_km" not in item for item in catalog.data))
            search = await client.call_tool("search_holidays", {"destination": "Paris"})
            self.assertEqual([item["holiday_id"] for item in search.data], ["HOL001"])
            details = await client.call_tool("get_holiday_details", {"holiday_id": "HOL001"})
            self.assertEqual(details.data["destination"], "Paris")
            recommended = await client.call_tool("recommend_holiday", {"budget": 1000})
            self.assertEqual([item["price_usd"] for item in recommended.data], [450, 800, 950])

    async def test_malformed_arguments_are_not_logged_or_echoed(self):
        # SDK validation errors can log submitted input; reject those before it.
        with patch.object(logging.Logger, "warning") as warning:
            async with Client(mcp) as client:
                for arguments in [
                    {"latitude": "private-location-value", "longitude": 2},
                    {"latitude": 48.85, "longitude": 2.35, "location_consent": "invalid"},
                    {"radius_km": None},
                    {"latitude": 10 ** 400, "longitude": 0},
                    {"extra": "private-location-value"},
                ]:
                    result = await client.call_tool("get_nearby_holidays", arguments)
                    self.assertEqual(result.data["status"], "invalid_request")
                    self.assertNotIn("private-location-value", str(result.content))
        self.assertNotIn("private-location-value", str(warning.call_args_list))
        self.assertNotIn("48.85", str(warning.call_args_list))

    async def test_consent_validation_search_and_no_origin_echo(self):
        async with Client(mcp) as client:
            initial = await client.call_tool("get_nearby_holidays", {})
            self.assertEqual(initial.data["status"], "consent_required")
            denied = await client.call_tool("get_nearby_holidays", {"latitude": 48.8566, "longitude": 2.3522})
            self.assertEqual(denied.data["status"], "consent_required")
            invalid = await client.call_tool("get_nearby_holidays", {"latitude": 999, "longitude": 0, "location_consent": True})
            self.assertEqual(invalid.data["status"], "invalid_request")
            partial = await client.call_tool("get_nearby_holidays", {"latitude": 1, "location_consent": True})
            self.assertEqual(partial.data["status"], "invalid_request")
            found = await client.call_tool("get_nearby_holidays", {
                "latitude": 48.85, "longitude": 2.35, "radius_km": 10, "location_consent": True,
            })
            self.assertEqual(found.data["status"], "ok")
            self.assertEqual(found.data["holidays"][0]["destination"], "Paris")
            self.assertNotIn("latitude", found.data)
            self.assertNotIn("longitude", found.data)
            self.assertNotIn("48.85,", json.dumps(found.data))

    async def test_ui_resource_and_gateway_metadata_round_trip(self):
        # Mirror the production gateway's create_proxy + namespaced mount, using
        # an in-memory backend transport to keep this deterministic and offline.
        gateway = FastMCP("Nearby test gateway")
        gateway.mount(create_proxy(Client(mcp)), namespace="holidays")
        register_nearby_ui_alias(gateway, mcp)
        async with Client(gateway) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools if t.name == "holidays_get_nearby_holidays")
            uri = tool.meta["ui"]["resourceUri"]
            resources = await client.list_resources()
            self.assertIn(uri, [str(r.uri) for r in resources])
            contents = await client.read_resource(uri)
            self.assertEqual(contents[0].mimeType, "text/html;profile=mcp-app")
            self.assertEqual(contents[0].meta["ui"]["permissions"], {"geolocation": {}})
            self.assertIn("Explore holidays near you", contents[0].text)
            self.assertNotIn('src="./nearby.js"', contents[0].text)
            result = await client.call_tool(tool.name, {
                "latitude": 0, "longitude": 0, "radius_km": 1, "location_consent": True,
            })
            self.assertEqual(result.data["holidays"], [])


if __name__ == "__main__":
    unittest.main()
