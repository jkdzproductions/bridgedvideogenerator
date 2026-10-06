import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_no_versed_left_in_code_or_tests():
    out = subprocess.run(
        # (^|[^a-z])versed skips words like "reversed" but still catches __versedRange, VersedVideo...
        ["git", "grep", "-nIiE", "(^|[^a-z])versed", "--", ".", ":!docs", ":!HANDOFF.md", ":!CLAUDE.md",
         ":!tests/test_no_versed_left.py", ":!tests/test_scaffold.py",
         ":!tests/test_prompts_are_bridged.py", ":!tests/test_design_system_snapshot.py",
         ":!tests/test_docs_are_bridged.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert out.stdout == "", "leftover Versed names:\n" + out.stdout
