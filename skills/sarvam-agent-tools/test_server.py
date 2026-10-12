"""Offline MCP protocol tests. Does not call paid APIs."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402


class Protocol(unittest.TestCase):
    def test_initialize(self):
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertIsNotNone(reply)
        self.assertEqual(reply["result"]["serverInfo"]["name"], "sarvam-agent-tools")
        self.assertIn("tools", reply["result"]["capabilities"])

    def test_initialized_is_notification(self):
        self.assertIsNone(server.handle({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }))

    def test_tools_list_has_three_tools(self):
        reply = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in reply["result"]["tools"]}
        self.assertEqual(names, {"transcribe", "translate", "speak"})
        for tool in reply["result"]["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertIn("description", tool)

    def test_unknown_method(self):
        reply = server.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
        self.assertEqual(reply["error"]["code"], -32601)

    def test_unknown_tool_does_not_call_api(self):
        reply = server.handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "explode", "arguments": {}},
        })
        self.assertEqual(reply["error"]["code"], -32602)

    def test_transcribe_missing_file_is_tool_error(self):
        # Handler runs, but must not hit the network: missing file fails first.
        reply = server.handle({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "transcribe", "arguments": {"path": "definitely-missing.wav"}},
        })
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("not found", reply["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
