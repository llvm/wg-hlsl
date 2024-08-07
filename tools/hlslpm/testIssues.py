import unittest
from issue import parse_data, IssueData

class Test_ParseData(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(None, parse_data(None).type)
        self.assertEqual(None, parse_data([]).type)
        self.assertEqual(None, parse_data([""]).type)
        self.assertEqual(None, parse_data(["sduhas fliuash filsaudhfslaiudfhsa"]).type)

        # These don't start with "##", so aren't recognized
        self.assertEqual(None, parse_data(["Milestones"]).type)
        self.assertEqual(None, parse_data(["Workstreams"]).type)

        # These aren't recognized
        self.assertEqual(None, parse_data(["## Flibble"]).type)

    def test_type(self):
        self.assertEqual("Milestones", parse_data(["## Milestones"]).type)
        self.assertEqual("Workstreams", parse_data(["## Workstreams"]).type)        

        # allow some non-matches before a real one
        self.assertEqual("Workstreams", parse_data(["foo", "## Bar", "## Workstreams"]).type)

        # only the first one counts
        self.assertEqual("Workstreams", parse_data(["## Workstreams", "## Milestones"]).type)

    def test_sections(self):
        self.assertEqual([], parse_data(["## Milestones"]).sections)
        
        d = parse_data(["## Milestones", "### section header"])
        self.assertEqual(["section header"], [s.title for s in d.sections])

        d = parse_data(["## Milestones", "### section header", "### another section header"])
        self.assertEqual(["section header", "another section header"], [s.title for s in d.sections])

        d = parse_data(["## Milestones", "### section header", "line 1", "line 2", "### another", "line 3"])
        self.assertEqual(["section header", "another"], [s.title for s in d.sections])
        self.assertEqual(["line 1", "line 2"], d.sections[0].contents)
        self.assertEqual(["line 3"], d.sections[1].contents)

        # A dummy section is created for stuff before the first section header
        d = parse_data(["## Milestones", "line 1", "line 2", "### another", "line 3"])
        self.assertEqual([None, "another"], [s.title for s in d.sections])
        self.assertEqual(["line 1", "line 2"], d.sections[0].contents)
        self.assertEqual(["line 3"], d.sections[1].contents)


if __name__ == '__main__':
    unittest.main()

