import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "botlab_host"))
import botlab_host


class LegacySearchUIRootAnswersTheFlatShape(unittest.TestCase):
    """The 2023_02_06 interface's VolatileProcessInterface.elm decodes only a
    flat `SearchUIRootAddressResult { processId, uiRootAddress }`, with no
    notion of an in-progress search. Answering it with the 2024 interface's
    staged `SearchUIRootAddressResponse` is a shape its decoder's closed
    `oneOf` never matches, so the bot's setup state never learns the search
    happened and it re-asks forever -- confirmed live on the mining bot."""

    def test_legacy_flag_answers_the_flat_result_shape(self):
        host = botlab_host.VolatileHost(legacy_search_ui_root=True)
        host._find_ui_root = lambda process_id: 0x1234
        response = json.loads(host.handle_request(
            json.dumps({"SearchUIRootAddress": {"processId": 2796}})))
        self.assertEqual(response, {
            "SearchUIRootAddressResult": {"processId": 2796, "uiRootAddress": "0x1234"},
        })

    def test_legacy_flag_answers_none_when_the_root_is_not_found(self):
        host = botlab_host.VolatileHost(legacy_search_ui_root=True)
        host._find_ui_root = lambda process_id: None
        response = json.loads(host.handle_request(
            json.dumps({"SearchUIRootAddress": {"processId": 2796}})))
        self.assertEqual(response, {
            "SearchUIRootAddressResult": {"processId": 2796, "uiRootAddress": None},
        })

    def test_legacy_flag_blocks_rather_than_polls(self):
        host = botlab_host.VolatileHost(legacy_search_ui_root=True)
        calls = []
        def find(process_id):
            calls.append(process_id)
            return 0x1234
        host._find_ui_root = find
        for _ in range(3):
            host.handle_request(json.dumps({"SearchUIRootAddress": {"processId": 2796}}))
        self.assertEqual(calls, [2796])

    def test_default_still_answers_the_staged_shape(self):
        host = botlab_host.VolatileHost()
        response = json.loads(host.handle_request(
            json.dumps({"SearchUIRootAddress": {"processId": 2796}})))
        self.assertIn("SearchUIRootAddressResponse", response)
        self.assertIn("stage", response["SearchUIRootAddressResponse"])


if __name__ == "__main__":
    unittest.main()
