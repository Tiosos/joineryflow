"""Which spec files failed in Playwright JSON reports, and which passed in all of them.

Usage: python3 scripts/playwright_failures.py REPORT.json [REPORT.json ...]
Used by the parallel experiment (.github/workflows/e2e-parallel-experiment.yml): a file that
passes in every report is a candidate for the parallel project; one that fails in any stays serial.
"""
import json
import sys


def walk(suite, file=""):
    file = suite.get("file") or file
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
            err = ""
            for r in test.get("results", []):
                if r.get("error"):
                    err = r["error"].get("message", "").strip().splitlines()[0][:160]
            yield spec.get("file") or file, spec["title"], test.get("status"), err
    for child in suite.get("suites", []):
        yield from walk(child, file)


def main(paths):
    files: set[str] = set()
    failed: dict[str, list[tuple[int, str, str]]] = {}
    for n, path in enumerate(paths, 1):
        try:
            with open(path) as f:
                report = json.load(f)
        except OSError:
            print(f"### Run {n}: no report ({path})\n")
            continue
        count = 0
        for s in report.get("suites", []):
            for file, title, status, err in walk(s):
                files.add(file)
                count += 1
                if status not in ("expected", "skipped"):
                    failed.setdefault(file, []).append((n, title, err))
        print(f"### Run {n}: {count} tests\n")
    if not files:
        print("No tests were reported.")
        return
    print("### Failed in at least one run (keep serial)\n")
    print("| file | run | test | first error line |\n| --- | :-: | --- | --- |")
    for file in sorted(failed):
        for n, title, err in failed[file]:
            print(f"| {file} | {n} | {title.replace('|', '/')} | {err.replace('|', '/')} |")
    if not failed:
        print("| none | | | |")
    passed = sorted(files - set(failed))
    print(f"\n### Passed in every run ({len(passed)} of {len(files)} files): candidates for the parallel project\n")
    print(", ".join(f"`{f}`" for f in passed))


if __name__ == "__main__":
    main(sys.argv[1:])
