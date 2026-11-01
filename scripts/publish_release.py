"""
Publish a release: check everything is ready, tag it, and push the tag. GitHub Actions then builds the installer
and attaches it to a GitHub Release (see .github/workflows/ci.yml); teammates download it from the Releases page.

    py scripts/publish_release.py            # dry run: runs every check, changes nothing
    py scripts/publish_release.py --push     # also creates the tag and pushes it

Before running with --push: set the new number in backend/_version.py, add its section to CHANGELOG.md, and commit.
"""
import argparse
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=check).stdout.strip()


def fail(msg):
    print(f"[STOP] {msg}")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true", help="create and push the tag (default is a dry run)")
    parser.add_argument("--skip-tests", action="store_true", help="skip the test suite (not recommended)")
    args = parser.parse_args()

    from backend._version import __version__
    tag = f"v{__version__}"
    print(f"Version in backend/_version.py: {__version__}  ->  tag {tag}")

    if not re.fullmatch(r"\d+\.\d+\.\d+", __version__):
        fail("Version must look like 2.1.0 (three numbers).")
    if git("status", "--porcelain", "--untracked-files=no"):
        fail("There are uncommitted changes. Commit them first.")
    branch = git("branch", "--show-current")
    print(f"Branch: {branch}")
    if git("tag", "--list", tag):
        fail(f"Tag {tag} already exists. Raise the version in backend/_version.py (and CHANGELOG.md) for a new release.")

    changelog = open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8").read()
    if f"## {__version__}" not in changelog and f"## [{__version__}]" not in changelog:
        fail(f"CHANGELOG.md has no '## {__version__}' section. Rename 'Unreleased' to '{__version__}' (with the date) and commit.")

    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    if not upstream:
        fail("This branch has no upstream. Push it first: git push -u origin " + branch)
    ahead = git("rev-list", "--count", f"{upstream}..HEAD")
    if ahead != "0":
        fail(f"{ahead} commit(s) are not pushed yet. Push the branch first so the tag points at code GitHub has.")

    if not args.skip_tests:
        print("Running the test suite (a few minutes)...")
        r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=REPO)
        if r.returncode != 0:
            fail("Tests failed. Fix them before releasing.")
        if git("status", "--porcelain", "--untracked-files=no"):
            fail("The test run changed tracked files. Investigate before releasing.")

    print(f"\nAll checks passed for {tag}.")
    if not args.push:
        print("Dry run only. Run again with --push to tag and publish.")
        return
    git("tag", "-a", tag, "-m", f"Release {__version__}")
    subprocess.run(["git", "push", "origin", tag], cwd=REPO, check=True)
    print(f"\nPushed {tag}. GitHub Actions is now building the installer.")
    print("Watch it under the repository's Actions tab; when it finishes the installer appears under Releases.")


if __name__ == "__main__":
    main()
