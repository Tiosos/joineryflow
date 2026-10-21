"""Print the slowest tests of Playwright JSON reports as a Markdown table.

Usage: python3 scripts/playwright_slowest.py [--top N] REPORT.json [REPORT.json ...]
CI appends the output to $GITHUB_STEP_SUMMARY (see the e2e job in ci.yml).
"""
import json
import sys


def walk(suite, file=""):
    file = suite.get("file") or file
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
            ms = sum(r.get("duration", 0) for r in test.get("results", []))
            yield ms, spec.get("file") or file, spec["title"]
    for child in suite.get("suites", []):
        yield from walk(child, file)


def main(argv):
    top = 15
    if argv[:1] == ["--top"]:
        top, argv = int(argv[1]), argv[2:]
    for path in argv:
        try:
            with open(path) as f:
                report = json.load(f)
        except OSError:
            print(f"### {path}\n\nNo report (the run did not get that far).\n")
            continue
        tests = [t for s in report.get("suites", []) for t in walk(s)]
        total = sum(ms for ms, _, _ in tests) / 1000
        print(f"### {path}: {len(tests)} tests, {total:.0f} s of test time\n")
        print("| s | spec | test |\n| ---: | --- | --- |")
        for ms, file, title in sorted(tests, reverse=True)[:top]:
            print(f"| {ms / 1000:.1f} | {file} | {title.replace('|', '/')} |")
        per_file: dict[str, float] = {}
        for ms, file, _ in tests:
            per_file[file] = per_file.get(file, 0) + ms / 1000
        print("\n| s | spec file (total) |\n| ---: | --- |")
        for file, s in sorted(per_file.items(), key=lambda kv: -kv[1])[:top]:
            print(f"| {s:.1f} | {file} |")
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
