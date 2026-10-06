import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PACKAGES = [
    "shot_list", "footage", "assembly", "motion_graphics",
    "script_input", "graph_intake", "page_intake", "image_intake",
]


def _tracked_or_untracked_files(cwd=ROOT):
    # -z gives raw, unquoted paths (plain `git ls-files` quotes non-ASCII names).
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout
    return [name for name in out.split("\0") if name]


def test_file_listing_returns_non_ascii_paths_unquoted(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    name = "candidates_\u00e9 \u202f.json"
    (tmp_path / name).write_text("{}")
    assert _tracked_or_untracked_files(cwd=tmp_path) == [name]


def test_no_font_files_or_versed_assets_in_the_repo():
    files = _tracked_or_untracked_files()
    assert [f for f in files if f.lower().endswith((".otf", ".ttf"))] == []
    assert [f for f in files if f.startswith("design-assets/")] == []


def test_no_secrets_or_run_state_in_the_repo():
    files = set(_tracked_or_untracked_files())
    for name in (".env", "shot_list.json", "youtube_quota_usage.json", "excluded_channel_ids.json"):
        assert name not in files
    assert not [f for f in files if f.startswith(("candidates_", "footage_output/", ".envato_automation_profile/"))]


def test_pyproject_names_the_bridged_project_and_lists_every_package():
    text = open(os.path.join(ROOT, "pyproject.toml")).read()
    assert 'name = "bridged-video-generator"' in text
    for package in PACKAGES:
        assert f'"{package}*"' in text


def test_every_package_imports_with_no_pythonpath():
    code = "; ".join(f"import {p}" for p in PACKAGES)
    result = subprocess.run(
        [os.path.join(ROOT, ".venv", "bin", "python"), "-c", code],
        cwd="/", capture_output=True, text=True,  # run from / so the project folder is not on the path
    )
    assert result.returncode == 0, result.stderr
