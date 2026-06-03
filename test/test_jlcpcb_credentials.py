import inspect
import os
import unittest
from unittest.mock import Mock, patch

import jlcparts.jlcpcb as jlcpcb


class JlcPcbCredentialTest(unittest.TestCase):
    def test_explicit_credentials_override_env_and_import_time_globals(self):
        env = {
            "JLCPCB_APP_ID": "env-app",
            "JLCPCB_ACCESS_KEY": "env-access",
            "JLCPCB_SECRET_KEY": "env-secret",
        }
        with patch.dict(os.environ, env), \
             patch.object(jlcpcb, "JLCPCB_APP_ID", "global-app", create=True), \
             patch.object(jlcpcb, "JLCPCB_ACCESS_KEY", "global-access", create=True), \
             patch.object(jlcpcb, "JLCPCB_SECRET_KEY", "global-secret", create=True):
            credentials = jlcpcb.JlcPcbCredentials(
                app_id="explicit-app",
                access_key="explicit-access",
                secret_key="explicit-secret",
            )
            interface = jlcpcb.createComponentInterface(
                credentials=credentials,
                lastKey="cursor-1",
            )

        self.assertEqual(interface.appId, "explicit-app")
        self.assertEqual(interface.accessKey, "explicit-access")
        self.assertEqual(interface.secretKey, "explicit-secret")
        self.assertEqual(interface.lastPage, "cursor-1")

    def test_env_credentials_are_used_when_no_explicit_credentials(self):
        env = {
            "JLCPCB_APP_ID": "env-app",
            "JLCPCB_ACCESS_KEY": "env-access",
            "JLCPCB_SECRET_KEY": "env-secret",
        }
        with patch.dict(os.environ, env), \
             patch.object(jlcpcb, "JLCPCB_APP_ID", None, create=True), \
             patch.object(jlcpcb, "JLCPCB_ACCESS_KEY", None, create=True), \
             patch.object(jlcpcb, "JLCPCB_SECRET_KEY", None, create=True):
            interface = jlcpcb.createComponentInterface(lastKey="cursor-2")

        self.assertEqual(interface.appId, "env-app")
        self.assertEqual(interface.accessKey, "env-access")
        self.assertEqual(interface.secretKey, "env-secret")
        self.assertEqual(interface.lastPage, "cursor-2")

    def test_missing_credentials_fail_only_when_official_interface_is_constructed(self):
        with patch.dict(os.environ, {}, clear=True):
            credentials = jlcpcb.JlcPcbCredentials.from_env()

        self.assertIsNone(credentials.app_id)
        self.assertIsNone(credentials.access_key)
        self.assertIsNone(credentials.secret_key)

        with self.assertRaisesRegex(RuntimeError, "JLCPCB_APP_ID"):
            jlcpcb.createComponentInterface(credentials=credentials)

    def test_live_lookup_component_fetches_official_detail_and_merges_website_enrichment(self):
        credentials = jlcpcb.JlcPcbCredentials(
            app_id="app",
            access_key="access",
            secret_key="secret",
        )
        official_payload = {
            "componentCode": "C11255",
            "firstTypeName": "Resistors",
            "secondTypeName": "Chip Resistor",
            "componentModel": "0603WAF1002T5E",
            "componentSpecification": "0603",
            "manufacturer": "UNI-ROYAL",
            "libraryType": "basic",
            "description": "10k resistor",
            "stockCount": 123,
            "priceRanges": [{"startQuantity": 1, "endQuantity": -1, "unitPrice": "0.001"}],
            "parameters": [],
        }
        website_detail = {
            "websiteComponentId": 11806,
            "assemblyProcess": "SMT",
            "assemblyMode": "smtWeld",
            "lossNumber": 1,
            "leastNumber": 2,
            "leastPatchNumber": 2,
            "minPurchaseNum": 1,
        }
        post_calls = []

        def fake_post(self, path, payload):
            post_calls.append((path, payload))
            return {
                "code": 200,
                "data": {
                    "componentDetailResponseVOList": [official_payload],
                },
            }

        checkpoint_writer = Mock(side_effect=AssertionError("live lookup must not persist"))
        with patch.object(jlcpcb.JlcPcbInterface, "_post", fake_post), \
             patch.object(
                 jlcpcb,
                 "_website_component_enrichment",
                 Mock(return_value=website_detail),
             ) as website_mock, \
             patch.object(jlcpcb, "writeCheckpoint", checkpoint_writer):
            result = jlcpcb.live_lookup_component(
                "C11255",
                credentials=credentials,
                include_website_detail=True,
            )

        self.assertEqual(post_calls, [
            (
                jlcpcb.JLCPCB_COMPONENT_DETAIL_PATH,
                {"componentCodes": ["C11255"]},
            ),
        ])
        website_mock.assert_called_once_with("C11255")
        checkpoint_writer.assert_not_called()
        self.assertEqual(result["lcsc"], "C11255")
        self.assertEqual(result["sources"], ["jlcpcb_openapi", "jlcpcb_website"])
        self.assertEqual(result["official_payload"], official_payload)
        self.assertEqual(result["website_detail"], website_detail)
        self.assertIsNone(result["website_error"])
        self.assertEqual(result["normalized_component"]["lcscPart"], "C11255")
        self.assertEqual(result["normalized_component"]["libraryType"], "base")
        self.assertEqual(result["normalized_component"]["jlcExtra"]["websiteComponentId"], 11806)
        self.assertEqual(
            result["normalized_component"]["jlcExtra"]["attributes"]["Assembly Mode"],
            "smtWeld",
        )
        self.assertIsInstance(result["fetched_at"], str)
        self.assertTrue(result["fetched_at"].endswith("Z"))

    def test_live_lookup_component_accepts_lcsc_keyword(self):
        self.assertEqual(
            str(inspect.signature(jlcpcb.live_lookup_component)),
            "(lcsc, credentials=None, include_website_detail=True)",
        )
        credentials = jlcpcb.JlcPcbCredentials(
            app_id="app",
            access_key="access",
            secret_key="secret",
        )
        official_payload = {
            "componentCode": "C11255",
            "componentModel": "0603WAF1002T5E",
            "libraryType": "basic",
            "priceRanges": [],
            "parameters": [],
        }
        post_calls = []

        def fake_post(self, path, payload):
            post_calls.append((path, payload))
            return {
                "code": 200,
                "data": {
                    "componentDetailResponseVOList": [official_payload],
                },
            }

        with patch.object(jlcpcb.JlcPcbInterface, "_post", fake_post):
            result = jlcpcb.live_lookup_component(
                lcsc="C11255",
                credentials=credentials,
                include_website_detail=False,
            )

        self.assertEqual(post_calls, [
            (
                jlcpcb.JLCPCB_COMPONENT_DETAIL_PATH,
                {"componentCodes": ["C11255"]},
            ),
        ])
        self.assertEqual(result["lcsc"], "C11255")
        self.assertEqual(result["normalized_component"]["lcscPart"], "C11255")

    def test_live_lookup_component_keeps_official_data_when_website_detail_fails(self):
        credentials = jlcpcb.JlcPcbCredentials(
            app_id="app",
            access_key="access",
            secret_key="secret",
        )
        official_payload = {
            "componentCode": "C11255",
            "componentModel": "0603WAF1002T5E",
            "libraryType": "basic",
            "description": "10k resistor",
            "stockCount": 123,
            "priceRanges": [],
            "parameters": [],
        }

        def fake_post(self, path, payload):
            return {
                "code": 200,
                "data": {
                    "componentDetailResponseVOList": [official_payload],
                },
            }

        with patch.object(jlcpcb.JlcPcbInterface, "_post", fake_post), \
             patch.object(
                 jlcpcb,
                 "_website_component_enrichment",
                 Mock(side_effect=RuntimeError("website unavailable")),
             ):
            result = jlcpcb.live_lookup_component(
                "C11255",
                credentials=credentials,
                include_website_detail=True,
            )

        self.assertEqual(result["lcsc"], "C11255")
        self.assertEqual(result["sources"], ["jlcpcb_openapi"])
        self.assertEqual(result["official_payload"], official_payload)
        self.assertIsNone(result["website_detail"])
        self.assertIn("website unavailable", result["website_error"])
        self.assertEqual(result["normalized_component"]["lcscPart"], "C11255")
        self.assertEqual(result["normalized_component"]["mfrPart"], "0603WAF1002T5E")


if __name__ == "__main__":
    unittest.main()
