# Contributing to Fabrication BOM API by NEPDESK

Thank you for your interest in contributing! This guide will walk you
through setting up the project on your local machine and submitting
your first pull request.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Fork & Clone](#fork--clone)
3. [Set Up the Development Environment](#set-up-the-development-environment)
4. [Install Pre-Commit Hooks](#install-pre-commit-hooks)
5. [Run the Local Server](#run-the-local-server)
6. [Making Changes](#making-changes)
7. [Submitting a Pull Request](#submitting-a-pull-request)
8. [Issue & Label Guide](#issue--label-guide)

---

## Code of Conduct

By participating in this project you agree to treat all contributors
with respect and professionalism. Harassment, discrimination, or
disruptive behaviour of any kind will not be tolerated.

---

## Fork & Clone

1. **Fork** the repository by clicking the *Fork* button on
   [github.com/nepdesk/fabrication-bom-api](https://github.com/nepdesk/fabrication-bom-api).

2. **Clone** your fork to your local machine:

   ```bash
   git clone https://github.com/<your-username>/fabrication-bom-api.git
   cd fabrication-bom-api
   ```

3. **Add the upstream remote** so you can pull future changes:

   ```bash
   git remote add upstream https://github.com/nepdesk/fabrication-bom-api.git
   ```

---

## Set Up the Development Environment

### Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Python | 3.10+ | 3.11 recommended |
| LibreDWG *or* ODA File Converter | latest | Required for `.dwg` → `.dxf` conversion |

On macOS you can install LibreDWG with:

```bash
brew install libredwg
```

### Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate      # macOS / Linux
# venv\Scripts\activate       # Windows
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Install Development Tools

```bash
pip install ruff pre-commit
```

---

## Install Pre-Commit Hooks

This project uses [pre-commit](https://pre-commit.com/) to
automatically check every commit for style and formatting issues.

```bash
pre-commit install
```

After this, every `git commit` will automatically run:

| Hook | What it Does |
|---|---|
| `trailing-whitespace` | Removes trailing spaces |
| `end-of-file-fixer` | Ensures files end with a newline |
| `check-yaml` | Validates YAML syntax |
| `check-added-large-files` | Blocks files > 5 MB (prevents `.dxf`/`.zip` accidents) |
| `ruff` | Lints Python code and auto-fixes issues |
| `ruff-format` | Formats Python code to project style |

You can also run the hooks manually against all files:

```bash
pre-commit run --all-files
```

---

## Run the Local Server

Start the FastAPI development server with hot-reload:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

| URL | Description |
|---|---|
| [http://localhost:5000](http://localhost:5000) | Web Dashboard |
| [http://localhost:5000/docs](http://localhost:5000/docs) | Interactive API Docs (Swagger) |

---

## Making Changes

1. **Create a feature branch** from `main`:

   ```bash
   git checkout main
   git pull upstream main
   git checkout -b feat/your-feature-name
   ```

2. **Write your code.** Follow the existing project structure:
   - `app/routers/` — API endpoint definitions
   - `app/models/` — Pydantic schemas and database operations
   - `app/services/` — Business logic (extraction, conversion)
   - `static/` — Frontend HTML, CSS, and JavaScript

3. **Run the linter** before committing:

   ```bash
   ruff check .
   ruff format .
   ```

4. **Commit your changes.** The pre-commit hooks will run
   automatically. If a hook modifies a file, simply `git add` the
   changed files and commit again.

   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

5. **Push** your branch:

   ```bash
   git push origin feat/your-feature-name
   ```

---

## Submitting a Pull Request

1. Go to your fork on GitHub and click **"Compare & pull request"**.
2. The PR description will auto-populate from our template.
   Fill in every section and check all boxes in the
   **Quality Checklist** before submitting.
3. A GitHub Actions workflow will run `ruff check .` on your PR.
   The merge button will only be enabled once all checks pass.

> **Important:** Do not commit any `.db` database files, proprietary
> `.dxf` drawings, or `.zip` test archives. These are excluded via
> `.gitignore`, but please double-check your staged files.

---

## Issue & Label Guide

We use the following labels to organize issues:

| Label | Meaning |
|---|---|
| `good first issue` | Beginner-friendly, well-defined tasks |
| `help wanted` | Open to external contributors |
| `bug` | Something isn't working |
| `enhancement` | New feature or improvement |
| `documentation` | Docs-related work |

Browse the [Issues tab](https://github.com/nepdesk/fabrication-bom-api/issues)
and look for `good first issue` or `help wanted` to get started!

---

## License

By contributing to this repository, you agree that your contributions
will be licensed under the [GNU GPLv3](LICENSE) license.
