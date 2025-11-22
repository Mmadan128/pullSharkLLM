import pathway as pw
from pathway.io.python import ConnectorSubject
from data.source.issueScraper import scrapIssues
import asyncio


class GitHubIssueScraperSubject(ConnectorSubject):

    def __init__(self, scrap_link: str):
        super().__init__()
        self._scrap_link = scrap_link

    def run(self) -> None:

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        data = loop.run_until_complete(scrapIssues(self._scrap_link))
        loop.close()

        repo = self._scrap_link.split("repos/")[1].split("/issues")[0]

        for issue in data:
            issue_id = issue["issue_id"]
            title = issue["title"]
            body = issue["body"]
            comments = issue["comments"]
            diffs = issue["code_diff"]

            comments_txt = "\n".join(
                f"[{c.get('user',{}).get('login','unknown')}] {c.get('body','')}"
                for c in comments
            )

            diff_txt = "\n".join(
                f"--- {d.get('path','')} ---\n{d.get('diff','')}"
                for d in diffs
            )

            final_text = (
                f"Issue ID: {issue_id}\n"
                f"Title: {title}\n\n"
                f"{body}\n\n"
                f"Comments:\n{comments_txt}\n\n"
                f"Code Diff:\n{diff_txt}"
            )

            url = f"https://github.com/{repo}/issues/{issue_id}"
                
            metadata = {
                "issue_id": issue_id,
                "repo": repo,
                "title": title,
                "body": body,
                "comments": comments,
                "code_diff": diffs,
                "total_comments": len(comments),
                "total_files_changed": len(diffs),
            }

            self.next(
                url=url,
                data=final_text,      
                _metadata=metadata    
            )
