import aiohttp
import asyncio
import os

GITHUB = "https://api.github.com"

# Read personal access token
GITHUB_PAT = os.getenv("GITHUB_PAT")


def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_PAT:
        headers["Authorization"] = f"Bearer {GITHUB_PAT}"
    return headers


# General function to fetch any API
async def fetch_json(session, url):
    try:
        async with session.get(url, headers=github_headers()) as resp:
            # Rate limit
            if resp.status == 403:
                reset = resp.headers.get("X-RateLimit-Reset")
                if reset:
                    now = int(asyncio.get_event_loop().time())
                    wait = int(reset) - now
                    await asyncio.sleep(max(wait, 2))
                    return await fetch_json(session, url)
            resp.raise_for_status()
            return await resp.json()
    except Exception as e:
        print("ERROR:", url, e)
        return {}


# Fetch closed issues (150 with pagination)
async def fetch_closed_issues(session, scrapLink):
    all_issues = []
    page = 1

    # Keep fetching until we have at least 150 issues
    while len(all_issues) < 150:
        url = f"{scrapLink}?state=closed&per_page=100&page={page}"
        issues = await fetch_json(session, url)

        if not isinstance(issues, list) or len(issues) == 0:
            break

        filtered = [i for i in issues if "pull_request" not in i]
        all_issues.extend(filtered)

        if len(issues) < 100:  # No more pages
            break

        page += 1

    return all_issues[:150]



# Find commit SHA that closed an issue
async def fetch_closing_sha(session, events_url):
    events = await fetch_json(session, events_url)

    if not isinstance(events, list):
        return None

    for e in events:
        if e.get("event") == "closed" and e.get("commit_id"):
            return e["commit_id"]

    return None


# Fetch commit diff
async def fetch_commit_diff(session, repo, sha):
    if not sha:
        return []

    url = f"{GITHUB}/repos/{repo}/commits/{sha}"
    data = await fetch_json(session, url)

    diffs = []
    for f in data.get("files", []):
        diffs.append({
            "path": f.get("filename"),
            "diff": f.get("patch", "")
        })
    return diffs


# Fetch issue comments
async def fetch_comments(session, url):
    data = await fetch_json(session, url)
    return data if isinstance(data, list) else []


# Process single issue
async def process_issue(session, issue, scrapLink):
    issue_id = issue["number"]
    repo = scrapLink.split("repos/")[1].split("/issues")[0]

    closing_sha_task = asyncio.create_task(
        fetch_closing_sha(session, issue["events_url"])
    )

    comments_task = asyncio.create_task(
        fetch_comments(session, issue["comments_url"])
    )

    closing_sha = await closing_sha_task
    diffs = await fetch_commit_diff(session, repo, closing_sha)
    comments = await comments_task

    return {
        "issue_id": issue.get("number"),
        "title": issue.get("title", ""),
        "body": issue.get("body", ""),
        "state": issue.get("state"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "closed_at": issue.get("closed_at"),
        "labels": [l.get("name") for l in issue.get("labels", [])],
        "author": issue.get("user", {}).get("login"),
        "assignee": issue.get("assignee", {}).get("login") if issue.get("assignee") else None,
        "comments_count": issue.get("comments", 0),
        "comments": comments,
        "code_diff": diffs,
        "events_url": issue.get("events_url"),
        "comments_url": issue.get("comments_url"),
        "html_url": issue.get("html_url"),
        "repo": repo,
    }



# Main function
async def scrapIssues(scrapLink) -> list:
    conn = aiohttp.TCPConnector(limit=30)

    async with aiohttp.ClientSession(connector=conn) as session:
        issues = await fetch_closed_issues(session, scrapLink)
        
        tasks = [
            process_issue(session, issue, scrapLink)
            for issue in issues
        ]

        results = await asyncio.gather(*tasks)
        if not results:
            return [{
                "issue_id": "no-data",
                "title": "No issues fetched",
                "body": "GitHub API returned zero issues.",
                "comments": [],
                "code_diff": [],
                "repo": scrapLink.split("repos/")[1].split("/issues")[0],
            }]

        return results
