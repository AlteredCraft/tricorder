import unittest

from planview.render import Links, render


class RenderTest(unittest.TestCase):
    def test_blocks(self):
        out = render("# Title\n\nPara **bold** and `code`.\n\n- one\n- two\n  cont\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertIn('<h1 id="title">', out)
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<code>code</code>", out)
        self.assertIn("<li>two cont", out)
        self.assertIn("<td>1</td>", out)

    def test_escapes_html(self):
        out = render("a <script>x</script> & b")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_ordered_start_and_fence(self):
        out = render("3. third\n4. fourth\n\n```sh\n# not heading\n```\n")
        self.assertIn('<ol start="3">', out)
        self.assertIn("# not heading", out)
        self.assertNotIn("<h1", out)

    def test_framework_tokens(self):
        links = Links(
            ident=lambda i: f"/id/{i}" if i == "G-0001.02" else None,
            commit=lambda sha: f"https://x/commit/{sha}",
            issue=lambda n: f"https://x/issues/{n}",
        )
        out = render("1. [pass] ok [C2 fail] see G-0001.02 and G-0009 · `abc1234` #7 `20260101-run`", links)
        self.assertIn('<span class="verdict v-pass">pass</span>', out)
        self.assertIn('<span class="ctag v-fail">C2 fail</span>', out)
        self.assertIn('<a class="idref" href="/id/G-0001.02">G-0001.02</a>', out)
        self.assertNotIn("/id/G-0009", out)
        self.assertIn('href="https://x/commit/abc1234"', out)
        self.assertIn('href="https://x/issues/7"', out)
        self.assertIn("<code>20260101-run</code>", out)

    def test_links_and_dead_links(self):
        links = Links(href=lambda t: None if t == "gone.md" else "/doc/" + t)
        out = render("[here](a.md) and [gone](gone.md) and [ADR-0001](x.md)", links)
        self.assertIn('<a href="/doc/a.md">here</a>', out)
        self.assertIn('class="deadlink"', out)
        self.assertIn('<a href="/doc/x.md">ADR-0001</a>', out)  # no nested autolink

    def test_header_field_lines_stay_separate(self):
        out = render("Status: Proposed\nGoal: G-0001\n\nplain\nwrapped: text")
        self.assertIn('<p class="fields">Status: Proposed<br>Goal: G-0001</p>', out)
        self.assertIn("<p>plain wrapped: text</p>", out)

    def test_stray_nul_bytes_cannot_hang(self):
        self.assertIn("ab", render("a\x00b"))
        self.assertIn("x999y", render("x\x00999\x00y"))

    def test_comment(self):
        self.assertIn('class="comment"', render("<!-- note -->"))


if __name__ == "__main__":
    unittest.main()
