"""MCP tools for GitHub repository research and technical evaluation."""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from loguru import logger

from ... import config as cfg
from ..base import PlatformTools
from .client import GitHubClient, GitHubError


class GitHubTools(PlatformTools):
    """GitHub REST API tools."""

    name = "github"
    description = "GitHub 仓库、README、Issue、Release、Pull Request 与方案对比"

    def __init__(self) -> None:
        self._client: GitHubClient | None = None

    def is_available(self) -> bool:
        return True

    def reload(self) -> None:
        self._client = None

    def _get_client(self) -> GitHubClient:
        if self._client is None:
            self._client = GitHubClient(cfg.get_config().get("github_tokens", []))
        return self._client

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        string = {"type": "string"}
        integer = {"type": "integer"}
        return [
            self._definition("github_search_repositories", "Search GitHub repositories by query, language, stars, update time, and sorting.", {"query": string, "language": string, "min_stars": integer, "max_stars": integer, "pushed_after": string, "sort": string, "order": string, "page": integer, "per_page": integer}, ["query"]),
            self._definition("github_get_repository", "Get repository metadata, activity signals, topics, license, and default branch.", {"repository": string}, ["repository"]),
            self._definition("github_get_readme", "Get and decode a repository README for technical evaluation.", {"repository": string}, ["repository"]),
            self._definition("github_get_issues", "List repository issues, optionally filtered by state, labels, and sorting.", {"repository": string, "state": string, "labels": string, "sort": string, "direction": string, "page": integer, "per_page": integer}, ["repository"]),
            self._definition("github_get_issue", "Get one GitHub issue including its body and metadata.", {"repository": string, "number": integer}, ["repository", "number"]),
            self._definition("github_get_releases", "List repository releases with version, date, and release notes.", {"repository": string, "page": integer, "per_page": integer}, ["repository"]),
            self._definition("github_get_pull_requests", "List repository pull requests, optionally filtered by state and sorting.", {"repository": string, "state": string, "sort": string, "direction": string, "page": integer, "per_page": integer}, ["repository"]),
            self._definition("github_compare_repositories", "Compare two GitHub repositories for implementation and technical solution evaluation.", {"repositories": {"type": "array", "items": string, "minItems": 2, "maxItems": 2}}, ["repositories"]),
        ]

    @staticmethod
    def _definition(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {"name": name, "description": description, "inputSchema": {"type": "object", "properties": properties, "required": required}}

    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            client = self._get_client()
            if tool_name == "github_search_repositories":
                return await asyncio.to_thread(self._search, client, arguments)
            if tool_name == "github_get_repository":
                return await asyncio.to_thread(self._repository, client, arguments["repository"])
            if tool_name == "github_get_readme":
                return await asyncio.to_thread(self._readme, client, arguments["repository"])
            if tool_name == "github_get_issues":
                return await asyncio.to_thread(self._issues, client, arguments)
            if tool_name == "github_get_issue":
                return await asyncio.to_thread(self._issue, client, arguments)
            if tool_name == "github_get_releases":
                return await asyncio.to_thread(self._releases, client, arguments)
            if tool_name == "github_get_pull_requests":
                return await asyncio.to_thread(self._pulls, client, arguments)
            if tool_name == "github_compare_repositories":
                return await asyncio.to_thread(self._compare, client, arguments["repositories"])
            return "Error: Unknown GitHub tool '{}'".format(tool_name)
        except GitHubError as exc:
            return "GitHub API error: {}".format(exc)
        except (KeyError, TypeError, ValueError) as exc:
            return "Invalid GitHub arguments: {}".format(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected GitHub tool error")
            return "Error: {}".format(exc)

    @staticmethod
    def _split(repository: str) -> tuple[str, str]:
        parts = repository.strip().strip("/").split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("repository must use owner/name format")
        return parts[0], parts[1]

    def _search(self, client: GitHubClient, args: dict[str, Any]) -> str:
        query = args["query"].strip()
        if not query:
            raise ValueError("query must not be empty")
        filters = [query]
        if args.get("language"):
            filters.append("language:" + args["language"])
        if args.get("min_stars") is not None:
            filters.append("stars:>={}".format(args["min_stars"]))
        if args.get("max_stars") is not None:
            filters.append("stars:<={}".format(args["max_stars"]))
        if args.get("pushed_after"):
            filters.append("pushed:>" + args["pushed_after"])
        data = client.search_repositories(
            " ".join(filters),
            sort=args.get("sort", "stars"), order=args.get("order", "desc"),
            page=max(1, args.get("page", 1)), per_page=min(100, max(1, args.get("per_page", 20))),
        )
        lines = [
            "GitHub repository search: {}".format(query),
            "Total count: {}".format(data.get("total_count", 0)),
        ]
        for item in data.get("items", []):
            lines.append(self._repo_line(item))
        return "\n".join(lines)

    def _repository(self, client: GitHubClient, repository: str) -> str:
        owner, repo = self._split(repository)
        return self._format_repo(client.get_repository(owner, repo))

    def _readme(self, client: GitHubClient, repository: str) -> str:
        owner, repo = self._split(repository)
        data = client.get_readme(owner, repo)
        content = data.get("content", "")
        if data.get("encoding") == "base64":
            content = base64.b64decode(content).decode("utf-8", errors="replace")
        return "README: {}\nURL: {}\n\n{}".format(repository, data.get("html_url", ""), content)

    def _issues(self, client: GitHubClient, args: dict[str, Any]) -> str:
        owner, repo = self._split(args["repository"])
        items = client.get_issues(owner, repo, state=args.get("state", "open"), labels=args.get("labels"), sort=args.get("sort", "created"), direction=args.get("direction", "desc"), page=max(1, args.get("page", 1)), per_page=min(100, max(1, args.get("per_page", 20))))
        return self._format_items("Issues", items, lambda item: "#{} [{}] {} | {} | {}".format(item.get("number"), item.get("state"), item.get("title"), item.get("user", {}).get("login", ""), item.get("html_url", "")))

    def _issue(self, client: GitHubClient, args: dict[str, Any]) -> str:
        owner, repo = self._split(args["repository"])
        item = client.get_issue(owner, repo, args["number"])
        return "Issue #{} [{}] {}\nAuthor: {}\nCreated: {}\nUpdated: {}\nURL: {}\n\n{}".format(item.get("number"), item.get("state"), item.get("title"), item.get("user", {}).get("login", ""), item.get("created_at", ""), item.get("updated_at", ""), item.get("html_url", ""), item.get("body") or "(no body)")

    def _releases(self, client: GitHubClient, args: dict[str, Any]) -> str:
        owner, repo = self._split(args["repository"])
        items = client.get_releases(owner, repo, page=max(1, args.get("page", 1)), per_page=min(100, max(1, args.get("per_page", 20))))
        return self._format_items("Releases", items, lambda item: "{} | {} | {} | {}".format(item.get("tag_name", ""), item.get("name", ""), item.get("published_at", ""), item.get("html_url", "")))

    def _pulls(self, client: GitHubClient, args: dict[str, Any]) -> str:
        owner, repo = self._split(args["repository"])
        items = client.get_pull_requests(owner, repo, state=args.get("state", "open"), sort=args.get("sort", "created"), direction=args.get("direction", "desc"), page=max(1, args.get("page", 1)), per_page=min(100, max(1, args.get("per_page", 20))))
        return self._format_items("Pull Requests", items, lambda item: "#{} [{}] {} | {} | {}".format(item.get("number"), item.get("state"), item.get("title"), item.get("user", {}).get("login", ""), item.get("html_url", "")))

    def _compare(self, client: GitHubClient, repositories: list[str]) -> str:
        if len(repositories) != 2:
            raise ValueError("repositories must contain exactly two owner/name values")
        data = [client.get_repository(*self._split(repository)) for repository in repositories]
        lines = ["GitHub repository comparison"]
        for item in data:
            lines.append(self._format_repo(item))
        return "\n\n---\n\n".join(lines)

    @staticmethod
    def _repo_line(item: dict[str, Any]) -> str:
        return "- {} | ★ {} | forks {} | issues {} | {} | {}".format(item.get("full_name"), item.get("stargazers_count", 0), item.get("forks_count", 0), item.get("open_issues_count", 0), item.get("language") or "N/A", item.get("html_url", ""))

    @staticmethod
    def _format_repo(item: dict[str, Any]) -> str:
        return "Repository: {}\nDescription: {}\nStars: {} | Forks: {} | Open issues: {}\nLanguage: {} | License: {}\nTopics: {}\nCreated: {} | Updated: {} | Pushed: {}\nArchived: {} | Fork: {}\nDefault branch: {}\nURL: {}".format(item.get("full_name"), item.get("description") or "(no description)", item.get("stargazers_count", 0), item.get("forks_count", 0), item.get("open_issues_count", 0), item.get("language") or "N/A", (item.get("license") or {}).get("spdx_id", "N/A"), ", ".join(item.get("topics", [])) or "N/A", item.get("created_at", ""), item.get("updated_at", ""), item.get("pushed_at", ""), item.get("archived", False), item.get("fork", False), item.get("default_branch", ""), item.get("html_url", ""))

    @staticmethod
    def _format_items(title: str, items: list[dict[str, Any]], formatter: Any) -> str:
        lines = [title + ": " + str(len(items))]
        lines.extend(formatter(item) for item in items)
        return "\n".join(lines)
