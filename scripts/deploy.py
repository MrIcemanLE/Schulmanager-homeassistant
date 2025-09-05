#!/usr/bin/env python3
"""
Deployment script for Schulmanager Integration
Handles version bumping, changelog updates, and Git operations
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

class VersionManager:
    """Manages version bumping and changelog updates"""
    
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.manifest_path = repo_path / "custom_components" / "schulmanager" / "manifest.json"
        self.version_path = repo_path / "VERSION"
        self.changelog_path = repo_path / "CHANGELOG.md"
    
    def get_current_version(self) -> str:
        """Get current version from VERSION file"""
        if self.version_path.exists():
            return self.version_path.read_text().strip()
        return "0.1.0"
    
    def bump_version(self, bump_type: str = "patch") -> str:
        """Bump version using semantic versioning"""
        current = self.get_current_version()
        major, minor, patch = map(int, current.split('.'))
        
        if bump_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump_type == "minor":
            minor += 1
            patch = 0
        elif bump_type == "patch":
            patch += 1
        else:
            raise ValueError(f"Invalid bump type: {bump_type}")
        
        new_version = f"{major}.{minor}.{patch}"
        return new_version
    
    def update_version_files(self, new_version: str):
        """Update version in all relevant files"""
        # Update VERSION file
        self.version_path.write_text(new_version)
        
        # Update manifest.json
        with open(self.manifest_path, 'r') as f:
            manifest = json.load(f)
        manifest["version"] = new_version
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
    
    def update_changelog(self, new_version: str, changes: str):
        """Update changelog with new version and changes"""
        if not self.changelog_path.exists():
            return
        
        changelog_content = self.changelog_path.read_text()
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Create new version entry
        new_entry = f"\n## [{new_version}] - {today}\n\n{changes}\n"
        
        # Insert after [Unreleased] section
        unreleased_pattern = r"(## \[Unreleased\].*?)(## \[)"
        if re.search(unreleased_pattern, changelog_content, re.DOTALL):
            changelog_content = re.sub(
                unreleased_pattern,
                f"\\1{new_entry}\\2",
                changelog_content,
                flags=re.DOTALL
            )
        else:
            # If no existing versions, add after unreleased section
            unreleased_end = changelog_content.find("\n\n## ")
            if unreleased_end == -1:
                changelog_content += new_entry
            else:
                changelog_content = (
                    changelog_content[:unreleased_end] + 
                    new_entry + 
                    changelog_content[unreleased_end:]
                )
        
        # Clear unreleased section
        changelog_content = re.sub(
            r"(## \[Unreleased\]\s*)(### Added.*?)(## \[)",
            "\\1\n### Added\n### Changed\n### Deprecated\n### Removed\n### Fixed\n### Security\n\n\\3",
            changelog_content,
            flags=re.DOTALL
        )
        
        self.changelog_path.write_text(changelog_content)

class GitManager:
    """Handles Git operations"""
    
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
    
    def run_git_command(self, cmd: list) -> Tuple[int, str, str]:
        """Run a git command and return result"""
        result = subprocess.run(
            ["git"] + cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    
    def commit_and_tag(self, version: str, message: str):
        """Commit changes and create version tag"""
        # Add all changes
        self.run_git_command(["add", "."])
        
        # Commit
        commit_msg = f"Release v{version}\n\n{message}"
        code, stdout, stderr = self.run_git_command(["commit", "-m", commit_msg])
        if code != 0:
            print(f"Commit failed: {stderr}")
            return False
        
        # Create tag
        code, stdout, stderr = self.run_git_command(["tag", "-a", f"v{version}", "-m", f"Version {version}"])
        if code != 0:
            print(f"Tagging failed: {stderr}")
            return False
        
        return True
    
    def push_changes(self):
        """Push changes and tags to origin"""
        # Push commits
        code, stdout, stderr = self.run_git_command(["push", "origin", "main"])
        if code != 0:
            print(f"Push failed: {stderr}")
            return False
        
        # Push tags
        code, stdout, stderr = self.run_git_command(["push", "--tags"])
        if code != 0:
            print(f"Push tags failed: {stderr}")
            return False
        
        return True

def main():
    """Main deployment function"""
    if len(sys.argv) < 3:
        print("Usage: python deploy.py <bump_type> <changes>")
        print("bump_type: major, minor, patch")
        print("changes: Description of changes for this release")
        sys.exit(1)
    
    bump_type = sys.argv[1]
    changes = sys.argv[2]
    
    if bump_type not in ["major", "minor", "patch"]:
        print("Invalid bump type. Use: major, minor, or patch")
        sys.exit(1)
    
    repo_path = Path(__file__).parent.parent
    version_manager = VersionManager(repo_path)
    git_manager = GitManager(repo_path)
    
    try:
        # Get new version
        current_version = version_manager.get_current_version()
        new_version = version_manager.bump_version(bump_type)
        
        print(f"Bumping version from {current_version} to {new_version}")
        
        # Update version files
        version_manager.update_version_files(new_version)
        
        # Update changelog
        version_manager.update_changelog(new_version, changes)
        
        # Git operations
        if git_manager.commit_and_tag(new_version, changes):
            print(f"Successfully committed and tagged version {new_version}")
            
            # Ask for push confirmation
            response = input("Push to GitHub? (y/N): ")
            if response.lower() == 'y':
                if git_manager.push_changes():
                    print("Successfully pushed to GitHub!")
                    print(f"Release v{new_version} is now available")
                else:
                    print("Failed to push to GitHub")
            else:
                print("Changes committed locally but not pushed")
        else:
            print("Failed to commit and tag")
            
    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()