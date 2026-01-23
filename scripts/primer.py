#!/usr/bin/env python3
"""Primer script for testing pytokens against real-world Python repositories."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Repository:
    """Configuration for a test repository."""

    name: str
    url: str
    ref: str


@dataclass
class ValidationResult:
    """Result of validation for a single repository."""

    repo_name: str
    total_files: int
    success_count: int
    skip_count: int
    failure_count: int
    failed_files: list[str]


@dataclass
class ComparisonResult:
    """Result of comparing two validation runs."""

    repo_name: str
    base_failures: set[str]
    pr_failures: set[str]
    new_failures: set[str]
    fixed_failures: set[str]
    base_stats: ValidationResult
    pr_stats: ValidationResult


class PrimerRunner:
    """Runs primer validation and comparison."""

    def __init__(self, config_path: Path, workspace_dir: Path):
        """Initialize primer runner."""
        self.config_path = config_path
        self.workspace_dir = workspace_dir
        self.repos_dir = workspace_dir / "repos"
        self.results_dir = workspace_dir / "results"

        # Create directories
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration
        with open(config_path) as f:
            config_data = json.load(f)

        self.repositories = [
            Repository(
                name=repo["name"],
                url=repo["url"],
                ref=repo["ref"],
            )
            for repo in config_data["repositories"]
        ]
        self.settings = config_data.get("settings", {})
        self.timeout = self.settings.get("timeout_per_repo", 300)

    def clone_or_update_repo(self, repo: Repository) -> Path:
        """Clone repository or update if it already exists."""
        repo_path = self.repos_dir / repo.name

        if repo_path.exists():
            print(f"Updating {repo.name}...")
            try:
                subprocess.run(
                    ["git", "fetch", "origin"],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    timeout=self.timeout,
                )
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to update {repo.name}: {e}")
                return repo_path
        else:
            print(f"Cloning {repo.name}...")
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth=1",
                        "--branch",
                        repo.ref,
                        repo.url,
                        str(repo_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=self.timeout,
                )
            except subprocess.CalledProcessError as e:
                print(f"Error: Failed to clone {repo.name}: {e}")
                raise

        # Checkout the specified ref
        try:
            subprocess.run(
                ["git", "checkout", repo.ref],
                cwd=repo_path,
                check=True,
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["git", "pull"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                timeout=self.timeout,
            )
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to checkout {repo.ref} in {repo.name}: {e}")

        return repo_path

    def run_validation(self, repo: Repository) -> ValidationResult:
        """Run pytokens validation on a repository."""
        print(f"Validating {repo.name}...")

        repo_path = self.clone_or_update_repo(repo)

        # Run pytokens validator with JSON output
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytokens",
                    "--validate",
                    "--json",
                    str(repo_path),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,  # Don't raise on non-zero exit
            )

            # Parse JSON output
            validation_data = json.loads(result.stdout)

            # Count results
            success_count = sum(
                1 for item in validation_data if item["status"] == "SUCCESS"
            )
            skip_count = sum(1 for item in validation_data if item["status"] == "SKIP")
            failure_count = sum(
                1 for item in validation_data if item["status"] == "FAILURE"
            )
            failed_files = [
                item["filepath"]
                for item in validation_data
                if item["status"] == "FAILURE"
            ]

            return ValidationResult(
                repo_name=repo.name,
                total_files=len(validation_data),
                success_count=success_count,
                skip_count=skip_count,
                failure_count=failure_count,
                failed_files=failed_files,
            )

        except subprocess.TimeoutExpired:
            print(f"Error: Validation timed out for {repo.name}")
            return ValidationResult(
                repo_name=repo.name,
                total_files=0,
                success_count=0,
                skip_count=0,
                failure_count=0,
                failed_files=[],
            )
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse validation output for {repo.name}: {e}")
            print(f"Output was: {result.stdout[:500]}")
            return ValidationResult(
                repo_name=repo.name,
                total_files=0,
                success_count=0,
                skip_count=0,
                failure_count=0,
                failed_files=[],
            )

    def run_all_validations(self) -> list[ValidationResult]:
        """Run validation on all configured repositories."""
        results: list[ValidationResult] = []
        for repo in self.repositories:
            try:
                result = self.run_validation(repo)
                results.append(result)
            except Exception as e:
                print(f"Error validating {repo.name}: {e}")
                # Continue with other repos
                continue

        return results

    def compare_results(
        self,
        base_results: list[ValidationResult],
        pr_results: list[ValidationResult],
    ) -> list[ComparisonResult]:
        """Compare validation results between base and PR."""
        comparisons: list[ComparisonResult] = []

        # Create a dict for easy lookup
        base_dict = {r.repo_name: r for r in base_results}
        pr_dict = {r.repo_name: r for r in pr_results}

        for repo_name in base_dict.keys() | pr_dict.keys():
            base_result = base_dict.get(repo_name)
            pr_result = pr_dict.get(repo_name)

            if not base_result or not pr_result:
                continue

            base_failures = set(base_result.failed_files)
            pr_failures = set(pr_result.failed_files)

            new_failures = pr_failures - base_failures
            fixed_failures = base_failures - pr_failures

            comparisons.append(
                ComparisonResult(
                    repo_name=repo_name,
                    base_failures=base_failures,
                    pr_failures=pr_failures,
                    new_failures=new_failures,
                    fixed_failures=fixed_failures,
                    base_stats=base_result,
                    pr_stats=pr_result,
                )
            )

        return comparisons

    def generate_report(self, comparisons: list[ComparisonResult]) -> str:
        """Generate markdown report from comparison results."""
        lines = ["# Pytokens Primer Report", ""]

        # Summary
        total_repos = len(comparisons)
        repos_with_regressions = sum(1 for c in comparisons if c.new_failures)
        repos_with_improvements = sum(1 for c in comparisons if c.fixed_failures)
        repos_unchanged = total_repos - repos_with_regressions - repos_with_improvements

        lines.extend(
            [
                "## Summary",
                f"- Repositories tested: {total_repos}",
                f"- Repositories with regressions: {repos_with_regressions} {'❌' if repos_with_regressions > 0 else ''}",
                f"- Repositories with improvements: {repos_with_improvements} {'✅' if repos_with_improvements > 0 else ''}",
                f"- Repositories unchanged: {repos_unchanged}",
                "",
            ]
        )

        # Regressions section
        regressions = [c for c in comparisons if c.new_failures]
        if regressions:
            lines.extend(["## Regressions", ""])
            for comp in regressions:
                lines.extend(
                    [
                        f"### {comp.repo_name}",
                        f"**New failures: {len(comp.new_failures)} files**",
                        "",
                    ]
                )
                for filepath in sorted(comp.new_failures):
                    lines.append(f"- {filepath}")
                lines.extend(
                    [
                        "",
                        f"**Stats**: {comp.pr_stats.success_count} passed, "
                        f"{comp.pr_stats.failure_count} failed (+{len(comp.new_failures)}), "
                        f"{comp.pr_stats.skip_count} skipped",
                        "",
                        "---",
                        "",
                    ]
                )

        # Improvements section
        improvements = [
            c for c in comparisons if c.fixed_failures and not c.new_failures
        ]
        if improvements:
            lines.extend(["## Improvements", ""])
            for comp in improvements:
                lines.extend(
                    [
                        f"### {comp.repo_name}",
                        f"**Fixed: {len(comp.fixed_failures)} files**",
                        "",
                    ]
                )
                for filepath in sorted(comp.fixed_failures):
                    lines.append(f"- {filepath}")
                lines.extend(
                    [
                        "",
                        f"**Stats**: {comp.pr_stats.success_count} passed (+{len(comp.fixed_failures)}), "
                        f"{comp.pr_stats.failure_count} failed, "
                        f"{comp.pr_stats.skip_count} skipped",
                        "",
                        "---",
                        "",
                    ]
                )

        # Conclusion
        lines.extend(["## Conclusion", ""])
        if repos_with_regressions > 0:
            total_new_failures = sum(len(c.new_failures) for c in regressions)
            lines.append(
                f"❌ **Regressions detected** - {total_new_failures} new failures"
            )
        else:
            lines.append("✅ **No regressions detected** - Safe to merge!")

        return "\n".join(lines)

    def run_primer_for_commit(self, commit: str) -> list[ValidationResult]:
        """Run primer on all repos for a specific pytokens commit."""
        # Resolve ref to commit hash (handles branches, tags, remote refs like origin/main)
        result = subprocess.run(
            ["git", "rev-parse", commit],
            capture_output=True,
            text=True,
            check=True,
        )
        commit_hash = result.stdout.strip()

        print(f"\n=== Running primer for {commit} ({commit_hash[:8]}) ===\n")

        # Checkout the commit hash
        subprocess.run(
            ["git", "checkout", commit_hash],
            check=True,
            capture_output=True,
        )

        # Reinstall pytokens
        print("Installing pytokens...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".", "-q"],
            check=True,
            capture_output=True,
        )

        # Run validations
        results = self.run_all_validations()

        # Save results
        results_file = self.results_dir / f"results-{commit[:8]}.json"
        with open(results_file, "w") as f:
            json.dump(
                [
                    {
                        "repo_name": r.repo_name,
                        "total_files": r.total_files,
                        "success_count": r.success_count,
                        "skip_count": r.skip_count,
                        "failure_count": r.failure_count,
                        "failed_files": r.failed_files,
                    }
                    for r in results
                ],
                f,
                indent=2,
            )

        print(f"\nResults saved to {results_file}")
        return results

    def compare_commits(
        self, base_commit: str, pr_commit: str, output_file: Path | None = None
    ) -> int:
        """Compare validation results between two commits."""
        # Get current branch/commit to restore later
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        original_ref = result.stdout.strip()
        if original_ref == "HEAD":
            # Detached HEAD, get the commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            original_ref = result.stdout.strip()

        # Save current primer.py and primer.json to preserve them across checkouts
        import shutil
        import tempfile

        temp_dir = Path(tempfile.mkdtemp())
        primer_script = Path(__file__)
        primer_config = self.config_path

        # Copy to temp location
        temp_script = temp_dir / "primer.py"
        temp_config = temp_dir / "primer.json"
        shutil.copy2(primer_script, temp_script)
        shutil.copy2(primer_config, temp_config)

        def restore_primer_files() -> None:
            """Restore primer.py and primer.json from temp location."""
            shutil.copy2(temp_script, primer_script)
            shutil.copy2(temp_config, primer_config)

        try:
            # Run for base
            base_results = self.run_primer_for_commit(base_commit)
            restore_primer_files()  # Restore after checkout

            # Run for PR
            pr_results = self.run_primer_for_commit(pr_commit)
            restore_primer_files()  # Restore after checkout

            # Compare
            comparisons = self.compare_results(base_results, pr_results)

            # Generate report
            report = self.generate_report(comparisons)
            print("\n" + "=" * 80)
            print(report)
            print("=" * 80 + "\n")

            # Save report if output file specified
            if output_file:
                output_file.write_text(report)
                print(f"Report saved to {output_file}")

            # Return non-zero if regressions detected
            has_regressions = any(c.new_failures for c in comparisons)
            return 1 if has_regressions else 0

        finally:
            # Restore original branch/commit
            print(f"\nRestoring original state: {original_ref}")
            subprocess.run(
                ["git", "checkout", original_ref], check=True, capture_output=True
            )
            restore_primer_files()  # Final restore
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", ".", "-q"],
                check=True,
                capture_output=True,
            )

            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Pytokens primer validation tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run validation on all repos")
    run_parser.add_argument(
        "--config", default="primer.json", help="Path to config file"
    )
    run_parser.add_argument(
        "--workspace",
        default=".primer-cache",
        help="Workspace directory for repos and results",
    )

    # Compare command
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare validation results between two commits",
    )
    compare_parser.add_argument("--base", required=True, help="Base commit/branch")
    compare_parser.add_argument("--pr", required=True, help="PR commit/branch")
    compare_parser.add_argument(
        "--config", default="primer.json", help="Path to config file"
    )
    compare_parser.add_argument(
        "--workspace",
        default=".primer-cache",
        help="Workspace directory for repos and results",
    )
    compare_parser.add_argument("--output", help="Output file for report (markdown)")

    args = parser.parse_args()

    # Resolve paths
    config_path = Path(args.config)
    workspace_dir = Path(args.workspace)

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        return 1

    runner = PrimerRunner(config_path, workspace_dir)

    if args.command == "run":
        results = runner.run_all_validations()
        print("\n=== Summary ===")
        for result in results:
            print(
                f"{result.repo_name}: {result.success_count} passed, "
                f"{result.failure_count} failed, {result.skip_count} skipped"
            )
        return 0

    elif args.command == "compare":
        output_file = Path(args.output) if args.output else None
        return runner.compare_commits(args.base, args.pr, output_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
