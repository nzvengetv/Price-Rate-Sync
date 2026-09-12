# GitHub Setup Guide - PriceSync ZW-USD

Step-by-step guide to upload and manage your project on GitHub

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Create GitHub Repository](#create-github-repository)
3. [Local Git Setup](#local-git-setup)
4. [Upload to GitHub](#upload-to-github)
5. [Repository Management](#repository-management)
6. [Continuous Integration Setup](#continuous-integration-setup)

---

## Prerequisites

### Install Git

**Windows:**
```bash
# Download from: https://git-scm.com/download/win
# Or use Chocolatey:
choco install git
```

**macOS:**
```bash
# Using Homebrew:
brew install git
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install git
```

### Verify Installation
```bash
git --version
```

### Configure Git
```bash
git config --global user.name "Your Full Name"
git config --global user.email "your.email@example.com"
```

---

## Create GitHub Repository

### Step 1: Sign In to GitHub
1. Go to [https://github.com](https://github.com)
2. Log in to your account (create one if needed)

### Step 2: Create New Repository
1. Click **"+"** icon → **New repository**
2. Fill in details:
   - **Repository name**: `pricesync-zw-usd`
   - **Description**: "Automated Exchange Rate & Retail Pricing System for Zimbabwe"
   - **Visibility**: Public (or Private if preferred)
   - **Initialize with**: Leave unchecked (we'll push existing files)

3. Click **Create repository**

### Step 3: Copy Repository URL
After creation, you'll see:
```
https://github.com/yourusername/pricesync-zw-usd.git
```
Save this URL - you'll need it!

---

## Local Git Setup

### Step 1: Navigate to Project Directory
```bash
cd /path/to/your/pricesync-zw-usd
```

### Step 2: Initialize Git Repository
```bash
git init
```

### Step 3: Add All Files
```bash
git add .
```

**To check what files will be added:**
```bash
git status
```

### Step 4: Create Initial Commit
```bash
git commit -m "Initial commit: PriceSync v2.0 - Automated retail pricing system"
```

### Step 5: Rename Branch (Optional)
GitHub uses 'main' by default:
```bash
git branch -M main
```

---

## Upload to GitHub

### Step 1: Add Remote Repository
Replace `yourusername` with your GitHub username:
```bash
git remote add origin https://github.com/yourusername/pricesync-zw-usd.git
```

### Step 2: Verify Remote Connection
```bash
git remote -v
```

Should show:
```
origin  https://github.com/yourusername/pricesync-zw-usd.git (fetch)
origin  https://github.com/yourusername/pricesync-zw-usd.git (push)
```

### Step 3: Push to GitHub

**First time push:**
```bash
git push -u origin main
```

**Subsequent pushes:**
```bash
git push
```

### Step 4: Verify on GitHub
1. Visit your repository: `https://github.com/yourusername/pricesync-zw-usd`
2. Verify all files are there
3. Check README.md renders correctly

---

## Repository Management

### Daily Workflow

**After making changes:**

```bash
# Check what changed
git status

# Add specific files
git add pricesync_zw-usd.py

# Or add all changes
git add .

# Commit with descriptive message
git commit -m "Add new pricing features"

# Push to GitHub
git push
```

### Commit Message Best Practices

Good commit messages:
```bash
git commit -m "Fix: Exchange rate API fallback mechanism"
git commit -m "Feature: Add webhook integration for POS systems"
git commit -m "Docs: Update README with installation steps"
git commit -m "Refactor: Optimize bulk pricing calculations"
git commit -m "Test: Add unit tests for pricing engine"
```

### Branching (For Collaborative Development)

**Create feature branch:**
```bash
git checkout -b feature/add-new-feature
```

**Make changes and commit:**
```bash
git add .
git commit -m "Add new feature"
git push -u origin feature/add-new-feature
```

**Create Pull Request on GitHub:**
1. Go to repository
2. Click "Compare & pull request"
3. Add description
4. Click "Create pull request"

**Merge after review:**
```bash
git checkout main
git pull origin main
git branch -d feature/add-new-feature
```

---

## Repository Management

### Updating Repository Settings

**GitHub Settings Page:**
1. Go to repository → Settings
2. Configure:
   - **Description**: Brief project description
   - **Topics**: Add tags (e.g., `exchange-rate`, `zimbabwe`, `python`, `pricing`)
   - **License**: Select MIT
   - **Include README**: ✓ Checked
   - **Include CODE_OF_CONDUCT**: Optional

### Enable Issues & Discussions
1. Settings → Features
2. Enable: Issues, Discussions (optional)

### Add Topics/Tags
1. Go to repository main page
2. Click "Add topics"
3. Add relevant tags:
   - `exchange-rate`
   - `zimbabwe`
   - `retail-pricing`
   - `python`
   - `tkinter`
   - `automation`

---

## Continuous Integration Setup

### Option 1: GitHub Actions (Recommended)

**Step 1: Create workflow directory:**
```bash
mkdir -p .github/workflows
```

**Step 2: Create CI workflow file:**
Create `.github/workflows/python-app.yml`:

```yaml
name: Python Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run tests
      run: |
        python test_pricesync.py
```

**Step 3: Push workflow:**
```bash
git add .github/workflows/python-app.yml
git commit -m "Add: GitHub Actions CI/CD pipeline"
git push
```

### Option 2: Badges in README

Add to README after setup:

```markdown
![Python Tests](https://github.com/yourusername/pricesync-zw-usd/workflows/Python%20Tests/badge.svg)
```

---

## Adding to Version Control

### Initial File Structure
```
pricesync-zw-usd/
├── pricesync_zw-usd.py      # Main application
├── test_pricesync.py         # Test suite
├── requirements.txt          # Dependencies
├── README.md                 # Documentation
├── LICENSE                   # MIT License
├── GITHUB_SETUP.md          # This file
├── .gitignore               # Git ignore rules
└── .github/
    └── workflows/
        └── python-app.yml   # CI/CD config
```

### Create LICENSE File

Create `LICENSE` file with MIT License:

```
MIT License

Copyright (c) 2024 [Your Name]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

---

## Troubleshooting

### Issue: Authentication Failed

**Solution: Use GitHub Token (Recommended)**

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Click "Generate new token"
3. Select scopes: `repo`, `workflow`
4. Copy token
5. Use in URL: `https://[YOUR_TOKEN]@github.com/username/repo.git`

Or use SSH:
```bash
ssh-keygen -t rsa -b 4096 -C "your.email@example.com"
# Add public key to GitHub Settings → SSH keys
git remote set-url origin git@github.com:yourusername/pricesync-zw-usd.git
```

### Issue: Large Files

If any files are over 100MB:
```bash
# Remove from git history
git filter-branch --tree-filter 'rm -f [filename]' HEAD

# Or use Git LFS
git lfs install
git lfs track "*.db"
```

### Issue: Wrong Commit Message

```bash
# Amend last commit
git commit --amend -m "New message"
git push --force-with-lease
```

---

## Promoting Your Project

### Share on:
- 📢 Twitter/X with hashtags: `#Zimbabwe`, `#Python`, `#OpenSource`
- 💼 LinkedIn: Professional networks
- 📝 Dev.to: Tech community
- 🐙 GitHub Discussions: Ask for feedback

### Add Badges to README

```markdown
![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Status Active](https://img.shields.io/badge/status-active-brightgreen)
![Tests Passing](https://img.shields.io/badge/tests-passing-brightgreen)
```

---

## Maintenance Checklist

- [ ] README is up-to-date
- [ ] requirements.txt is current
- [ ] .gitignore is comprehensive
- [ ] LICENSE file included
- [ ] Tests pass locally
- [ ] No hardcoded credentials
- [ ] Code commented
- [ ] Issues tracked
- [ ] Contributing guidelines (optional)
- [ ] Changelog maintained

---

## Quick Reference Commands

```bash
# Initial setup
git init
git add .
git commit -m "Initial commit"
git remote add origin [URL]
git push -u origin main

# Daily work
git status
git add [file]
git commit -m "Message"
git push

# View history
git log --oneline
git log --graph --all --decorate

# Undo changes
git restore [file]              # Undo unstaged
git restore --staged [file]     # Unstage file
git revert [commit-hash]        # Undo published commit
```

---

## Resources

- [Git Documentation](https://git-scm.com/doc)
- [GitHub Guides](https://guides.github.com)
- [GitHub CLI Tool](https://cli.github.com)
- [GitHub Desktop](https://desktop.github.com)

---

## Support

For questions about GitHub setup:
- 📖 Read: [GitHub Help Documentation](https://docs.github.com)
- 💬 Ask: Stack Overflow with `git` and `github` tags
- 🐛 Report: GitHub Issues in repository

---

**Last Updated:** 2024
**Git Version:** 2.40+
**GitHub:** https://github.com
