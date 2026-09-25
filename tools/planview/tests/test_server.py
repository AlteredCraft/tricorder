import json
import threading
import unittest
import urllib.error
import urllib.request

from planview.server import make_server

from .fixture import make_tree


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, base = make_tree()
        (base / ".local").mkdir()
        (base / ".local" / "secret.md").write_text("# secret\n")
        (base / "planning" / "data.json").write_text('{"a": 1}')
        cls.server = make_server(base / "planning", "127.0.0.1", 0, repo="https://github.com/o/r")
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.url + path) as res:
            return res.status, res.read().decode()

    def status(self, path):
        try:
            return self.get(path)[0]
        except urllib.error.HTTPError as err:
            return err.code

    def test_overview(self):
        _, body = self.get("/")
        self.assertIn("Ship the thing", body)
        self.assertIn("Next up", body)
        self.assertIn("Three runs (C2).", body)
        self.assertIn("Waiting on you", body)
        self.assertIn('class="cell v-fail"', body)

    def test_pages(self):
        for path in ("/activity", "/activity?spec=G-0001.01", "/adrs", "/docs", "/health",
                     "/doc/planning/milestones.md", "/doc/planning/plans/G-0001.01-first.md",
                     "/doc/planning/plans/G-0001-first-goal.md", "/doc/planning/adrs/ADR-0001-choice.md",
                     "/doc/README.md", "/raw/planning/data.json", "/static/app.css", "/static/app.js"):
            self.assertEqual(self.status(path), 200, path)

    def test_spec_page_relations(self):
        _, body = self.get("/doc/planning/plans/G-0001.01-first.md")
        self.assertIn("G-0001", body)
        self.assertIn("https://github.com/o/r/commit/abc1234", body)
        self.assertIn("https://github.com/o/r/issues/12", body)
        self.assertIn("ADR-0001", body)
        self.assertNotIn("Linked from", body)  # parent and ADR already shown above

    def test_json(self):
        _, body = self.get("/api/plan.json")
        data = json.loads(body)
        self.assertEqual(data["milestones"][0]["id"], "M-0001")

    def test_refuses_hidden_and_escaping_paths(self):
        for path in ("/doc/.local/secret.md", "/raw/.git/config", "/doc/../../etc/passwd",
                     "/raw/%2e%2e/%2e%2e/etc/passwd", "/static/../model.py", "/nope"):
            self.assertEqual(self.status(path), 404, path)


if __name__ == "__main__":
    unittest.main()
