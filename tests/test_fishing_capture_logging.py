import ast
import inspect
import textwrap
import unittest

import fishing_capture


class FishingCaptureLoggingRegressionTests(unittest.TestCase):
    def test_capture_never_writes_jsonl_through_application_logger(self):
        tree=ast.parse(textwrap.dedent(inspect.getsource(fishing_capture.FishingCapture.capture)))
        bad=[]
        session_writes=0
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write':
                if isinstance(node.func.value,ast.Name) and node.func.value.id=='log':
                    bad.append(node.lineno)
                if isinstance(node.func.value,ast.Name) and node.func.value.id=='session_log':
                    session_writes+=1
        self.assertEqual(bad,[],f'application logger used as file handle at lines {bad}')
        self.assertGreaterEqual(session_writes,1)


if __name__=='__main__':
    unittest.main()
