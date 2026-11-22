#!/usr/bin/python3

import asyncio
import os
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Any, cast

import aiohttp
import requests

###############################################################################
# Queries
###############################################################################


class Queries:
    def __init__(self, username, access_token, session, max_connections=10):
        self.username = username
        self.access_token = access_token
        self.session = session
        self.semaphore = asyncio.Semaphore(max_connections)

    async def query(self, generated_query: str) -> Dict:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            async with self.semaphore:
                r = await self.session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                )
            result = await r.json()
            if result is not None:
                return result
        except Exception:
            print("aiohttp failed for GraphQL query")
            async with self.semaphore:
                r2 = requests.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                )
                result = r2.json()
                if result is not None:
                    return result
        return {}

    async def query_rest(self, path: str, params: Optional[Dict] = None) -> Dict:
        for _ in range(60):
            headers = {"Authorization": f"token {self.access_token}"}
            if params is None:
                params = {}
            if path.startswith("/"):
                path = path[1:]
            try:
                async with self.semaphore:
                    r = await self.session.get(
                        f"https://api.github.com/{path}",
                        headers=headers,
                        params=tuple(params.items()),
                    )
                if r.status == 202:
                    await asyncio.sleep(2)
                    continue
                result = await r.json()
                if result is not None:
                    return result
            except Exception:
                async with self.semaphore:
                    r2 = requests.get(
                        f"https://api.github.com/{path}",
                        headers=headers,
                        params=tuple(params.items()),
                    )
                    if r2.status_code == 202:
                        await asyncio.sleep(2)
                        continue
                    elif r2.status_code == 200:
                        return r2.json()
        return {}

    @staticmethod
    def repos_overview(owned_cursor=None) -> str:
        """Only fetch repos owned by the user, not forked repos."""
        return f"""{{
  viewer {{
    login
    name
    repositories(
        first: 100,
        orderBy: {{field: UPDATED_AT, direction: DESC}},
        isFork: false,
        ownerAffiliations: OWNER,
        after: {"null" if owned_cursor is None else '"' + owned_cursor + '"'}
    ) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        nameWithOwner
        stargazers {{ totalCount }}
        forkCount
        isFork
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
          edges {{ size node {{ name color }} }}
        }}
      }}
    }}
  }}
}}"""

    @staticmethod
    def contrib_years() -> str:
        return """
query {
  viewer {
    contributionsCollection {
      contributionYears
    }
  }
}"""

    @staticmethod
    def contribs_by_year(year: str) -> str:
        return f"""
    year{year}: contributionsCollection(
        from: "{year}-01-01T00:00:00Z",
        to: "{int(year) + 1}-01-01T00:00:00Z"
    ) {{
      contributionCalendar {{
        totalContributions
      }}
    }}"""

    @classmethod
    def all_contribs(cls, years: List[str]) -> str:
        by_years = "\n".join(map(cls.contribs_by_year, years))
        return f"""
query {{
  viewer {{
    {by_years}
  }}
}}"""

    @staticmethod
    def contribution_calendar() -> str:
        """Fetch daily contribution data for the past year."""
        return """
query {
  viewer {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            weekday
          }
        }
      }
    }
  }
}"""


###############################################################################
# Streak logic
###############################################################################

# A streak survives this many empty days in a row. It breaks on the next one.
# 1 -> a single day off is forgiven; two empty days in a row end the streak.
STREAK_GRACE_DAYS = 1


def compute_streaks(
    days: List[Dict],
    today: Optional[date] = None,
    grace: int = STREAK_GRACE_DAYS,
) -> Dict[str, Any]:
    """
    days: [{"date": "YYYY-MM-DD", "count": int}, ...]

    A streak runs from its first active day to its last active day. Empty days
    inside it (up to `grace` in a row) are bridged and count toward its length.
    `today` is ignored while it is still empty, since the day isn't over yet.
    """
    today = today or datetime.now(timezone.utc).date()
    series = sorted(
        (date.fromisoformat(d["date"]), d["count"])
        for d in days
        if date.fromisoformat(d["date"]) <= today
    )
    if series and series[-1][0] == today and series[-1][1] == 0:
        series.pop()

    best = (0, None, None)  # length, start, end

    def consider(start: date, end: date) -> None:
        nonlocal best
        length = (end - start).days + 1
        if length > best[0]:
            best = (length, start, end)

    run_start: Optional[date] = None
    run_end: Optional[date] = None
    pending: List[date] = []  # empty days since the last active day
    bridged: List[date] = []  # empty days inside the current run

    for d, count in series:
        if count > 0:
            if run_start is None:
                run_start = d
            else:
                bridged.extend(pending)
            run_end = d
            pending = []
        elif run_start is not None:
            pending.append(d)
            if len(pending) > grace:  # streak broken
                consider(run_start, run_end)
                run_start = run_end = None
                pending, bridged = [], []

    current = 0
    if run_start is not None:
        consider(run_start, run_end)
        current = (run_end - run_start).days + 1

    last_active = max((d for d, c in series if c > 0), default=None)
    iso = lambda x: x.isoformat() if x else None

    return {
        "current_streak": current,
        "current_start": iso(run_start),
        "current_end": iso(run_end),
        "longest_streak": best[0],
        "longest_start": iso(best[1]),
        "longest_end": iso(best[2]),
        "grace_dates": [x.isoformat() for x in bridged + (pending if run_start else [])],
        "last_active": iso(last_active),
        "total_this_year": sum(c for _, c in series),
    }


###############################################################################
# Stats
###############################################################################


class Stats:
    def __init__(
        self,
        username: str,
        access_token: str,
        session: aiohttp.ClientSession,
        exclude_repos: Optional[Set] = None,
        exclude_langs: Optional[Set] = None,
        ignore_forked_repos: bool = True,  # Default to True to only count owned repos
    ):
        self.username = username
        self._ignore_forked_repos = ignore_forked_repos
        self._exclude_repos = set() if exclude_repos is None else exclude_repos
        self._exclude_langs = set() if exclude_langs is None else exclude_langs
        self.queries = Queries(username, access_token, session)

        self._name: Optional[str] = None
        self._stargazers: Optional[int] = None
        self._forks: Optional[int] = None
        self._total_contributions: Optional[int] = None
        self._languages: Optional[Dict[str, Any]] = None
        self._repos: Optional[List[str]] = None  # Changed to List for order
        self._lines_changed: Optional[Tuple[int, int]] = None
        self._views: Optional[int] = None
        self._daily_contributions: Optional[List[Dict]] = None
        self._commit_langs: Optional[Dict[str, float]] = None

    async def get_stats(self) -> None:
        """Fetch stats only from repos owned by the user."""
        self._stargazers = 0
        self._forks = 0
        self._languages = {}
        self._repos = []
        exclude_langs_lower = {x.lower() for x in self._exclude_langs}
        next_owned = None

        while True:
            raw = await self.queries.query(
                Queries.repos_overview(owned_cursor=next_owned)
            )
            raw = raw or {}
            viewer = raw.get("data", {}).get("viewer", {})

            self._name = viewer.get("name") or viewer.get("login", "No Name")

            owned = viewer.get("repositories", {})
            repos = owned.get("nodes", [])

            for repo in repos:
                if repo is None:
                    continue
                name = repo.get("nameWithOwner")

                # Skip excluded repos
                if name in self._exclude_repos:
                    continue

                # Skip forked repos if configured
                if self._ignore_forked_repos and repo.get("isFork", False):
                    continue

                self._repos.append(name)
                self._stargazers += repo.get("stargazers", {}).get("totalCount", 0)
                self._forks += repo.get("forkCount", 0)

                # Process languages
                for lang in repo.get("languages", {}).get("edges", []):
                    lname = lang.get("node", {}).get("name", "Other")
                    if lname.lower() in exclude_langs_lower:
                        continue
                    if lname in self._languages:
                        self._languages[lname]["size"] += lang.get("size", 0)
                        self._languages[lname]["occurrences"] += 1
                    else:
                        self._languages[lname] = {
                            "size": lang.get("size", 0),
                            "occurrences": 1,
                            "color": lang.get("node", {}).get("color"),
                        }

            has_more = owned.get("pageInfo", {}).get("hasNextPage", False)
            if has_more:
                next_owned = owned.get("pageInfo", {}).get("endCursor", next_owned)
            else:
                break

        # Calculate language proportions
        langs_total = sum(v.get("size", 0) for v in self._languages.values())
        for v in self._languages.values():
            v["prop"] = 100 * (v.get("size", 0) / langs_total) if langs_total else 0

    @property
    async def name(self) -> str:
        if self._name is None:
            await self.get_stats()
        return self._name  # type: ignore

    @property
    async def stargazers(self) -> int:
        if self._stargazers is None:
            await self.get_stats()
        return self._stargazers  # type: ignore

    @property
    async def forks(self) -> int:
        if self._forks is None:
            await self.get_stats()
        return self._forks  # type: ignore

    @property
    async def languages(self) -> Dict:
        if self._languages is None:
            await self.get_stats()
        return self._languages  # type: ignore

    @property
    async def languages_proportional(self) -> Dict:
        if self._languages is None:
            await self.get_stats()
        return {k: v.get("prop", 0) for k, v in self._languages.items()}  # type: ignore

    @property
    async def repos(self) -> List[str]:
        if self._repos is None:
            await self.get_stats()
        return self._repos  # type: ignore

    @property
    async def total_contributions(self) -> int:
        if self._total_contributions is not None:
            return self._total_contributions
        self._total_contributions = 0
        years = (
            (await self.queries.query(Queries.contrib_years()))
            .get("data", {})
            .get("viewer", {})
            .get("contributionsCollection", {})
            .get("contributionYears", [])
        )
        by_year = (
            (await self.queries.query(Queries.all_contribs(years)))
            .get("data", {})
            .get("viewer", {})
            .values()
        )
        for year in by_year:
            self._total_contributions += year.get("contributionCalendar", {}).get(
                "totalContributions", 0
            )
        return cast(int, self._total_contributions)

    @property
    async def lines_changed(self) -> Tuple[int, int]:
        if self._lines_changed is not None:
            return self._lines_changed
        additions = deletions = 0
        for repo in await self.repos:
            r = await self.queries.query_rest(f"/repos/{repo}/stats/contributors")
            for obj in r if isinstance(r, list) else []:
                if not isinstance(obj, dict):
                    continue
                if (obj.get("author") or {}).get("login", "") != self.username:
                    continue
                for week in obj.get("weeks", []):
                    additions += week.get("a", 0)
                    deletions += week.get("d", 0)
        self._lines_changed = (additions, deletions)
        return self._lines_changed

    @property
    async def views(self) -> int:
        if self._views is not None:
            return self._views
        total = 0
        for repo in await self.repos:
            r = await self.queries.query_rest(f"/repos/{repo}/traffic/views")
            if r and isinstance(r, dict):
                for view in r.get("views", []):
                    total += view.get("count", 0)
        self._views = total
        return total

    @property
    async def daily_contributions(self) -> List[Dict]:
        """
        Returns a flat list of {date, count} dicts for the past year,
        sorted oldest → newest.
        """
        if self._daily_contributions is not None:
            return self._daily_contributions

        result = await self.queries.query(Queries.contribution_calendar())
        weeks = (
            result.get("data", {})
            .get("viewer", {})
            .get("contributionsCollection", {})
            .get("contributionCalendar", {})
            .get("weeks", [])
        )
        days = []
        for week in weeks:
            for day in week.get("contributionDays", []):
                days.append(
                    {
                        "date": day["date"],
                        "count": day["contributionCount"],
                    }
                )
        days.sort(key=lambda d: d["date"])
        self._daily_contributions = days
        return days

    @property
    async def streak_stats(self) -> Dict:
        """See compute_streaks(). One empty day in a row never breaks a streak."""
        return compute_streaks(await self.daily_contributions)

    @property
    async def languages_by_commits(self) -> Dict[str, float]:
        """
        Language → weighted score (byte proportion × commit count per repo).
        Only includes owned repos.
        """
        if self._commit_langs is not None:
            return self._commit_langs

        repo_commits: Dict[str, int] = {}
        for repo in await self.repos:
            r = await self.queries.query_rest(f"/repos/{repo}/stats/contributors")
            if not isinstance(r, list):
                continue
            for obj in r:
                if not isinstance(obj, dict):
                    continue
                if (obj.get("author") or {}).get(
                    "login", ""
                ).lower() != self.username.lower():
                    continue
                total = sum(w.get("c", 0) for w in obj.get("weeks", []))
                if total > 0:
                    repo_commits[repo] = total
                break

        exclude_lower = {x.lower() for x in self._exclude_langs}
        scores: Dict[str, float] = {}
        for repo, commit_count in repo_commits.items():
            lang_data = await self.queries.query_rest(f"/repos/{repo}/languages")
            if not isinstance(lang_data, dict) or not lang_data:
                continue
            total_bytes = sum(lang_data.values()) or 1
            for lang, nbytes in lang_data.items():
                if lang.lower() in exclude_lower:
                    continue
                scores[lang] = (
                    scores.get(lang, 0.0) + (nbytes / total_bytes) * commit_count
                )

        self._commit_langs = scores
        return scores


###############################################################################
# Main (testing)
###############################################################################


async def main() -> None:
    token = os.getenv("ACCESS_TOKEN")
    user = os.getenv("GITHUB_USERNAME") or os.getenv("GITHUB_ACTOR")
    if not token or not user:
        raise RuntimeError("ACCESS_TOKEN and GITHUB_ACTOR must be set")
    async with aiohttp.ClientSession() as session:
        s = Stats(user, token, session)

        # Test the stats
        name = await s.name
        stars = await s.stargazers
        forks = await s.forks
        repos = await s.repos

        print(f"User: {name}")
        print(f"Stars: {stars:,}")
        print(f"Forks: {forks:,}")
        print(f"Repos: {len(repos)}")

        streak = await s.streak_stats
        print(f"Current streak : {streak['current_streak']} days")
        print(f"Longest streak : {streak['longest_streak']} days")
        print(f"Total this year: {streak['total_this_year']:,}")


if __name__ == "__main__":
    asyncio.run(main())
