#!/usr/bin/env python3
"""Primer script for testing pytokens against real-world Python repositories."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def restore_primer_files(
    temp_script: Path, temp_config: Path, primer_script: Path, primer_config: Path
) -> None:
    """Restore primer.py and primer.json from temp location."""
    # Ensure directories exist (in case old commit doesn't have them)
    primer_script.parent.mkdir(parents=True, exist_ok=True)
    primer_config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(temp_script, primer_script)
    shutil.copy2(temp_config, primer_config)


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

    def __init__(self, config_path: Path, workspace_dir: Path, debug: bool = False):
        """Initialize primer runner."""
        self.debug = debug
        self.logger = logging.getLogger(__name__)

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

        # Debug logging for initialization
        self.logger.debug(f"Loaded configuration from {config_path}")
        self.logger.debug(f"Workspace directory: {workspace_dir}")
        self.logger.debug(f"Found {len(self.repositories)} repositories")
        for repo in self.repositories:
            self.logger.debug(f"  - {repo.name} ({repo.ref})")
        self.logger.debug(f"Timeout per repo: {self.timeout}s")

    def _run_subprocess(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        description: str = "",
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        """Run subprocess with debug-aware output handling."""
        cmd_str = " ".join(cmd)
        self.logger.debug(f"Running: {cmd_str}")
        if description:
            self.logger.debug(f"Purpose: {description}")

        # Always run the subprocess with capture if it was requested
        if "capture_output" not in kwargs:
            kwargs["capture_output"] = True

        # Run the subprocess
        try:
            result = subprocess.run(cmd, env=env, **kwargs)
        except subprocess.CalledProcessError as e:
            # If debug mode and command failed, log the output before re-raising
            if self.debug:
                self.logger.debug(f"Command failed with exit code {e.returncode}")
                if hasattr(e, "stdout") and e.stdout:
                    self.logger.debug(
                        f"stdout: {e.stdout if isinstance(e.stdout, str) else e.stdout.decode()}"
                    )
                if hasattr(e, "stderr") and e.stderr:
                    self.logger.debug(
                        f"stderr: {e.stderr if isinstance(e.stderr, str) else e.stderr.decode()}"
                    )
            raise

        # In debug mode, log the captured output
        if self.debug:
            if result.returncode != 0:
                self.logger.debug(f"Command failed with exit code {result.returncode}")
            if hasattr(result, "stdout") and result.stdout:
                self.logger.debug(
                    f"stdout: {result.stdout if isinstance(result.stdout, str) else result.stdout.decode()}"
                )
            if hasattr(result, "stderr") and result.stderr:
                self.logger.debug(
                    f"stderr: {result.stderr if isinstance(result.stderr, str) else result.stderr.decode()}"
                )

        return result

    def clone_or_update_repo(self, repo: Repository) -> Path:
        """Clone repository or update if it already exists."""
        repo_path = self.repos_dir / repo.name

        if repo_path.exists():
            self.logger.debug(
                f"Repository {repo.name} exists at {repo_path}, updating..."
            )
            print(f"Updating {repo.name}...")
            try:
                self._run_subprocess(
                    ["git", "fetch", "origin"],
                    description=f"Fetching updates for {repo.name}",
                    cwd=repo_path,
                    check=True,
                    timeout=self.timeout,
                )
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to update {repo.name}: {e}")
                return repo_path
        else:
            self.logger.debug(
                f"Repository {repo.name} not found, cloning from {repo.url}"
            )
            print(f"Cloning {repo.name}...")
            try:
                self._run_subprocess(
                    [
                        "git",
                        "clone",
                        "--depth=1",
                        "--branch",
                        repo.ref,
                        repo.url,
                        str(repo_path),
                    ],
                    description=f"Cloning {repo.name}",
                    check=True,
                    timeout=self.timeout,
                )
            except subprocess.CalledProcessError as e:
                print(f"Error: Failed to clone {repo.name}: {e}")
                raise

        # Checkout the specified ref
        self.logger.debug(f"Checking out ref {repo.ref} for {repo.name}")
        try:
            self._run_subprocess(
                ["git", "checkout", repo.ref],
                description=f"Checking out {repo.ref}",
                cwd=repo_path,
                check=True,
                timeout=30,
            )
            self._run_subprocess(
                ["git", "pull"],
                description="Pulling latest changes",
                cwd=repo_path,
                check=True,
                timeout=self.timeout,
            )
            self.logger.debug(f"Successfully checked out {repo.ref}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to checkout {repo.ref} in {repo.name}: {e}")

        return repo_path

    def run_validation(self, repo: Repository) -> ValidationResult:
        """Run pytokens validation on a repository."""
        self.logger.debug(f"Starting validation for {repo.name}")
        print(f"Validating {repo.name}...")

        repo_path = self.clone_or_update_repo(repo)

        # Run pytokens validator with JSON output
        result = None
        try:
            result = self._run_subprocess(
                [
                    sys.executable,
                    "-m",
                    "pytokens",
                    "--validate",
                    "--json",
                    str(repo_path),
                ],
                description=f"Running pytokens validation on {repo.name}",
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,  # Don't raise on non-zero exit
            )

            # Parse JSON output
            self.logger.debug(f"Parsing validation output for {repo.name}")
            if not result.stdout.strip():
                print(f"Error: No output from validator for {repo.name}")
                print(f"stderr: {result.stderr}")
                print(f"returncode: {result.returncode}")
                return ValidationResult(
                    repo_name=repo.name,
                    total_files=0,
                    success_count=0,
                    skip_count=0,
                    failure_count=0,
                    failed_files=[],
                )

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

            self.logger.debug(
                f"Validation complete for {repo.name}: {success_count} passed, {failure_count} failed, {skip_count} skipped"
            )

            return ValidationResult(
                repo_name=repo.name,
                total_files=len(validation_data),
                success_count=success_count,
                skip_count=skip_count,
                failure_count=failure_count,
                failed_files=failed_files,
            )

        except subprocess.TimeoutExpired:
            self.logger.debug(f"Validation timeout for {repo.name}")
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
            self.logger.debug(f"JSON parse error for {repo.name}: {e}")
            print(f"\n{'='*80}")
            print(f"FATAL ERROR: Failed to parse JSON validation output for {repo.name}")
            print(f"JSON Error: {e}")
            if result:
                print(f"\nFirst 1000 characters of output:")
                print(f"{result.stdout[:1000]}")
            print(f"\nThis indicates pytokens is printing non-JSON content to stdout.")
            print(f"Check that --json mode properly suppresses all diagnostic output.")
            print(f"{'='*80}\n")
            raise RuntimeError(
                f"JSON parsing failed for {repo.name}. "
                f"Validation output is contaminated with non-JSON content."
            )

    def run_all_validations(self) -> list[ValidationResult]:
        """Run validation on all configured repositories."""
        self.logger.debug("Starting validation suite for all repositories")
        results: list[ValidationResult] = []
        for i, repo in enumerate(self.repositories):
            try:
                self.logger.debug(
                    f"Processing repository {repo.name} ({i+1}/{len(self.repositories)})"
                )
                result = self.run_validation(repo)
                results.append(result)
            except RuntimeError:
                # RuntimeError indicates a fatal error (e.g., JSON parsing failure)
                # Re-raise to fail the entire primer run
                raise
            except Exception as e:
                self.logger.debug(f"Exception during validation: {e}", exc_info=True)
                print(f"Error validating {repo.name}: {e}")
                # Continue with other repos for non-fatal errors
                continue

        return results

    def compare_results(
        self,
        base_results: list[ValidationResult],
        pr_results: list[ValidationResult],
    ) -> list[ComparisonResult]:
        """Compare validation results between base and PR."""
        self.logger.debug("Comparing validation results")
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

            self.logger.debug(
                f"Comparing {repo_name}: {len(new_failures)} new, {len(fixed_failures)} fixed"
            )

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

    def run_primer_for_commit(
        self,
        commit_hash: str,
        temp_repo_dir: Path,
        primer_script: Path,
        primer_config: Path,
    ) -> list[ValidationResult]:
        """Run primer on all repos for a specific pytokens commit hash."""
        self.logger.debug(f"Running primer for commit {commit_hash}")
        print(f"\n=== Running primer for {commit_hash[:8]} ===\n")

        # Clean any untracked files before checkout
        self._run_subprocess(
            ["git", "clean", "-fd"],
            description="Cleaning untracked files",
            cwd=temp_repo_dir,
            check=True,
        )

        # Checkout the commit hash in temp repo (force to overwrite any local changes)
        self._run_subprocess(
            ["git", "checkout", "-f", commit_hash],
            description=f"Checking out commit {commit_hash[:8]}",
            cwd=temp_repo_dir,
            check=True,
        )

        # Copy current primer files to temp repo
        self.logger.debug("Copying current primer files to temp repo")
        (temp_repo_dir / "scripts").mkdir(exist_ok=True)
        shutil.copy2(primer_script, temp_repo_dir / "scripts" / "primer.py")
        shutil.copy2(primer_config, temp_repo_dir / "primer.json")

        # Create a fresh venv for this commit
        venv_dir = temp_repo_dir.parent / f"venv-{commit_hash[:8]}"
        self.logger.debug(f"Creating fresh venv at {venv_dir}")
        print("Creating fresh virtual environment...")
        self._run_subprocess(
            [sys.executable, "-m", "venv", str(venv_dir)],
            description=f"Creating venv for {commit_hash[:8]}",
            check=True,
        )

        # Determine the python executable in the new venv
        if sys.platform == "win32":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"

        # Install pytokens from temp repo into fresh venv
        print("Installing pytokens in fresh environment...")
        self._run_subprocess(
            [str(venv_python), "-m", "pip", "install", "-e", str(temp_repo_dir), "-q"],
            env={**os.environ, "PYTOKENS_USE_MYPYC": "0"},
            description=f"Installing pytokens for {commit_hash[:8]}",
            check=True,
        )

        # Temporarily replace sys.executable to use the venv python for validations
        self.logger.debug(f"Using venv python: {venv_python}")
        original_executable = sys.executable
        sys.executable = str(venv_python)

        try:
            # Run validations
            self.logger.debug("Running validations")
            results = self.run_all_validations()
        finally:
            # Restore original sys.executable
            sys.executable = original_executable

        # Save results
        self.logger.debug("Validation complete, saving results")
        results_file = self.results_dir / f"results-{commit_hash[:8]}.json"
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

        self.logger.debug(f"Results saved to {results_file}")
        print(f"\nResults saved to {results_file}")
        return results

    def compare_commits(
        self, base_commit: str, pr_commit: str, output_file: Path | None = None
    ) -> int:
        """Compare validation results between two commits."""
        # Get current working directory (the real repo)
        current_dir = Path.cwd()

        # If base_commit looks like a remote ref (e.g., origin/main), fetch it first
        if "/" in base_commit and base_commit.startswith("origin/"):
            branch_name = base_commit.split("/", 1)[1]
            self.logger.debug(f"Fetching remote branch: {branch_name}")
            print(f"Fetching {branch_name} from origin...")
            try:
                # Fetch with enough depth to ensure we get the commit history
                # In CI shallow clones, we need to unshallow or fetch with sufficient depth
                self._run_subprocess(
                    ["git", "fetch", "--depth=100", "origin", branch_name],
                    description=f"Fetching {branch_name}",
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                self.logger.debug(f"Fetch with depth failed, trying unshallow: {e}")
                try:
                    # If depth fetch fails, try to unshallow
                    self._run_subprocess(
                        ["git", "fetch", "--unshallow", "origin"],
                        description="Unshallowing repository",
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    self.logger.debug(f"Unshallow also failed, trying simple fetch")
                    # Last resort: simple fetch
                    self._run_subprocess(
                        ["git", "fetch", "origin", branch_name],
                        description=f"Fetching {branch_name} (simple)",
                        check=False,
                    )

        # Resolve to commit hashes in current repo
        self.logger.debug(f"Resolving base commit: {base_commit}")
        base_commit_hash = self._run_subprocess(
            ["git", "rev-parse", base_commit],
            description="Resolving base commit hash",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        self.logger.debug(f"Resolving PR commit: {pr_commit}")
        pr_commit_hash = self._run_subprocess(
            ["git", "rev-parse", pr_commit],
            description="Resolving PR commit hash",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        self.logger.debug(f"Base: {base_commit_hash}, PR: {pr_commit_hash}")
        print(f"Base commit: {base_commit} -> {base_commit_hash[:8]}")
        print(f"PR commit: {pr_commit} -> {pr_commit_hash[:8]}")

        # Create a temp directory and clone the repo there
        self.logger.debug("Creating temp directory for git operations")
        temp_dir = Path(tempfile.mkdtemp())
        temp_repo_dir = temp_dir / "repo"

        primer_script = Path(__file__)
        primer_config = self.config_path

        try:
            # Get the origin URL from the current repo
            origin_url_result = self._run_subprocess(
                ["git", "config", "--get", "remote.origin.url"],
                description="Getting origin URL",
                cwd=current_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            origin_url = origin_url_result.stdout.strip() if origin_url_result.returncode == 0 else None

            # Clone the current repo to temp directory
            self.logger.debug(f"Cloning repo to temp directory: {temp_repo_dir}")
            print(f"Cloning repo to temporary directory...")
            self._run_subprocess(
                ["git", "clone", str(current_dir), str(temp_repo_dir)],
                description="Cloning repo to temp directory",
                check=True,
            )

            # If we have an origin URL, update the temp repo's origin to point to it
            # and fetch the commits we need from the actual remote
            if origin_url:
                self.logger.debug(f"Updating origin URL to: {origin_url}")
                self._run_subprocess(
                    ["git", "remote", "set-url", "origin", origin_url],
                    description="Updating origin URL",
                    cwd=temp_repo_dir,
                    check=True,
                )

                # Fetch enough history to ensure we have both commits
                # We can't fetch arbitrary commit SHAs, so we fetch all branches
                self.logger.debug("Fetching all branches from origin")
                print(f"Fetching branches from origin...")
                self._run_subprocess(
                    ["git", "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*"],
                    description="Fetching all branches",
                    cwd=temp_repo_dir,
                    check=True,
                )

            # Run for base commit
            base_results = self.run_primer_for_commit(
                base_commit_hash, temp_repo_dir, primer_script, primer_config
            )

            # Run for PR commit
            pr_results = self.run_primer_for_commit(
                pr_commit_hash, temp_repo_dir, primer_script, primer_config
            )

            # Compare
            self.logger.debug("Comparing results between base and PR")
            comparisons = self.compare_results(base_results, pr_results)

            # Generate report
            report = self.generate_report(comparisons)
            print("\n" + "=" * 80)
            print(report)
            print("=" * 80 + "\n")

            # Save report if output file specified
            if output_file:
                print(f"Writing report to {output_file.absolute()}")
                output_file.write_text(report)
                print(f"Report saved to {output_file.absolute()}")
                print(f"File exists: {output_file.exists()}")
            else:
                print("No output file specified")

            # Return non-zero if regressions detected
            has_regressions = any(c.new_failures for c in comparisons)
            self.logger.debug(f"Regressions detected: {has_regressions}")
            return 1 if has_regressions else 0

        finally:
            # Clean up temp directory
            self.logger.debug("Cleaning up temp directory")
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"Cleaned up temporary directory")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Pytokens primer validation tool")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and show subprocess output",
    )
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

    # Configure logging based on debug flag
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="[DEBUG] %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")

    # Resolve paths
    config_path = Path(args.config)
    workspace_dir = Path(args.workspace)

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        return 1

    runner = PrimerRunner(config_path, workspace_dir, debug=args.debug)

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
