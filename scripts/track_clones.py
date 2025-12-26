import os
import csv
import json
import traceback
from datetime import datetime, timedelta
from collections import defaultdict
from github import Github, Auth

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


def load_historical_data():
    """Load both cumulative totals and daily records"""
    summary_file = os.path.join(DATA_DIR, "clones_summary.json")

    if os.path.exists(summary_file):
        try:
            with open(summary_file, "r") as f:
                data = json.load(f)
                return {
                    "cumulative_totals": data.get("cumulative_totals", {}),
                    "daily_records": data.get("daily_records", {}),
                    "last_run": data.get("last_updated")
                }
        except:
            pass

    return {
        "cumulative_totals": {},
        "daily_records": {},
        "last_run": None
    }


def get_clone_stats():
    """Fetch clone statistics for all repositories"""
    token = os.environ.get("GITHUB_TOKEN")
    username = os.environ.get("GITHUB_USERNAME")

    print(f"=== Debug Info ===")
    print(f"Username: {username}")
    print(f"Token present: {'Yes' if token else 'No'}")
    print("=" * 60)

    if not token or not username:
        raise ValueError("GITHUB_TOKEN and GITHUB_USERNAME must be set")

    auth = Auth.Token(token)
    g = Github(auth=auth)

    try:
        user = g.get_user(username)
        print(f"✓ Successfully authenticated as: {user.login}")
    except Exception as e:
        print(f"✗ Authentication failed: {str(e)}")
        raise

    clone_data = []
    successful = 0
    failed = 0
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"\nFetching clone data for {username}'s repositories...")
    print("=" * 60)

    for repo in user.get_repos():
        try:
            # Get traffic data (clones)
            clones = repo.get_clones_traffic()

            # Get daily breakdown
            daily_clones = {}
            for day_data in clones.clones:
                day_str = day_data.timestamp.strftime("%Y-%m-%d")
                daily_clones[day_str] = {
                    "count": day_data.count,
                    "uniques": day_data.uniques
                }

            repo_data = {
                "timestamp": timestamp,
                "date": today,
                "repo_name": repo.name,
                "period_clones": clones.count,
                "period_unique": clones.uniques,
                "daily_breakdown": daily_clones
            }

            clone_data.append(repo_data)
            print(
                f"✓ {repo.name}: {clones.count} clones ({clones.uniques} unique) [last 14 days]"
            )
            successful += 1

        except Exception as e:
            failed += 1
            error_msg = str(e)
            print(f"✗ {repo.name}: {error_msg}")
            continue

    print("=" * 60)
    print(f"\nSummary:")
    print(f"    ✓ Successful: {successful}")
    print(f"    ✗ Failed: {failed}")
    print(f"  Total repos: {successful + failed}")

    return clone_data, timestamp, today


def update_csv(clone_data):
    """Update CSV file with clone statistics"""
    csv_file = os.path.join(DATA_DIR, "clone_data.csv")
    file_exists = os.path.isfile(csv_file)

    fieldnames = ["timestamp", "date", "repo_name", "period_clones", "period_unique"]

    with open(csv_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for data in clone_data:
            row = {k: v for k, v in data.items() if k in fieldnames}
            writer.writerow(row)

    print(f"\n✓ CSV file updated at {csv_file} with {len(clone_data)} entries")


def calculate_cumulative_totals(clone_data, historical_data, today):
    """Calculate cumulative totals using daily breakdown to avoid double-counting"""
    cumulative = historical_data["cumulative_totals"].copy()
    daily_records = historical_data["daily_records"].copy()

    for repo in clone_data:
        repo_name = repo["repo_name"]

        # Initialize repo if not seen before
        if repo_name not in cumulative:
            cumulative[repo_name] = {
                "total_clones": 0,
                "total_unique": 0,
                "first_tracked": repo["timestamp"],
            }

        if repo_name not in daily_records:
            daily_records[repo_name] = {}

        # Process each day in the breakdown
        for day_str, day_stats in repo["daily_breakdown"].items():
            # Only add clones if we haven't recorded this day before
            if day_str not in daily_records[repo_name]:
                daily_records[repo_name][day_str] = {
                    "count": day_stats["count"],
                    "uniques": day_stats["uniques"]
                }

                # Add to cumulative total
                cumulative[repo_name]["total_clones"] += day_stats["count"]

                print(f"  → Adding {day_stats['count']} clones from {day_str} for {repo_name}")

        # Clean up old daily records (keep only last 30 days to save space)
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        daily_records[repo_name] = {
            day: stats
            for day, stats in daily_records[repo_name].items()
            if day >= cutoff_date
        }

        # Update unique count (use max from recent period)
        cumulative[repo_name]["total_unique"] = max(
            cumulative[repo_name]["total_unique"],
            repo["period_unique"]
        )

        cumulative[repo_name]["last_updated"] = repo["timestamp"]

    return cumulative, daily_records


def update_clone_summary(clone_data, timestamp, today, cumulative_totals, daily_records):
    """Create/update JSON summary file with both period and cumulative data"""
    summary_file = os.path.join(DATA_DIR, "clones_summary.json")

    # Calculate period totals (last 14 days)
    period_total_clones = sum(r["period_clones"] for r in clone_data)
    period_total_unique = sum(r["period_unique"] for r in clone_data)

    # Calculate overall cumulative totals
    overall_total_clones = sum(r["total_clones"] for r in cumulative_totals.values())
    overall_total_unique = sum(r["total_unique"] for r in cumulative_totals.values())

    # Get top cloned repos (by cumulative total)
    top_clones_cumulative = sorted(
        [
            {
                "name": name,
                "total_clones": data["total_clones"],
                "total_unique": data["total_unique"],
            }
            for name, data in cumulative_totals.items()
        ],
        key=lambda x: x["total_clones"],
        reverse=True,
    )[:10]

    # Get top cloned repos (by period)
    top_clones_period = sorted(
        [
            {
                "name": r["repo_name"],
                "period_clones": r["period_clones"],
                "period_unique": r["period_unique"],
            }
            for r in clone_data
        ],
        key=lambda x: x["period_clones"],
        reverse=True,
    )[:10]

    summary = {
        "last_updated": timestamp,
        "last_run_date": today,
        "period_stats": {
            "description": "Clone statistics for the last 14 days",
            "total_clones": period_total_clones,
            "total_unique_clones": period_total_unique,
            "repositories_tracked": len(clone_data),
            "repositories_with_clones": len(
                [r for r in clone_data if r["period_clones"] > 0]
            ),
            "top_repositories": top_clones_period,
        },
        "cumulative_stats": {
            "description": "All-time cumulative clone statistics (since tracking began)",
            "total_clones": overall_total_clones,
            "total_unique_clones": overall_total_unique,
            "repositories_tracked": len(cumulative_totals),
            "repositories_with_clones": len(
                [r for r in cumulative_totals.values() if r["total_clones"] > 0]
            ),
            "top_repositories": top_clones_cumulative,
        },
        "cumulative_totals": cumulative_totals,
        "daily_records": daily_records,  # Store daily records to prevent double-counting
    }

    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"✓ Clone summary JSON updated at {summary_file}")
    print(f"\n{'='*60}")
    print(f"PERIOD STATS (Last 14 Days):")
    print(f"{'='*60}")
    print(f"    Period Clones: {period_total_clones}")
    print(f"    Unique Clones: {period_total_unique}")
    print(
        f"    Repos with Clones: {summary['period_stats']['repositories_with_clones']}/{len(clone_data)}"
    )

    print(f"\n{'='*60}")
    print(f"CUMULATIVE STATS (All-Time):")
    print(f"{'='*60}")
    print(f"    Total Clones: {overall_total_clones}")
    print(f"    Total Unique: {overall_total_unique}")
    print(
        f"    Repos with Clones: {summary['cumulative_stats']['repositories_with_clones']}/{len(cumulative_totals)}"
    )

    print(f"\nTop 5 Most Cloned Repos (All-Time):")
    for i, repo in enumerate(top_clones_cumulative[:5], 1):
        print(
            f"  {i}. {repo['name']}: {repo['total_clones']} clones ({repo['total_unique']} unique)"
        )


def main():
    try:
        # Load historical data
        historical_data = load_historical_data()
        print(f"Loaded historical data for {len(historical_data['cumulative_totals'])} repositories")
        if historical_data['last_run']:
            print(f"Last run: {historical_data['last_run']}\n")

        # Get current clone data (last 14 days with daily breakdown)
        clone_data, timestamp, today = get_clone_stats()

        if clone_data:
            # Update CSV with period data
            update_csv(clone_data)

            # Calculate new cumulative totals (avoiding double-counting)
            cumulative_totals, daily_records = calculate_cumulative_totals(
                clone_data, historical_data, today
            )

            # Update summary with both period and cumulative stats
            update_clone_summary(clone_data, timestamp, today, cumulative_totals, daily_records)

            print("\n=== Clone tracking completed successfully ===")
        else:
            print(
                "\n⚠ No clone data collected - this might be normal if all repos failed"
            )
            print("⚠ Check the errors above for permission issues")

    except Exception as e:
        print(f"\n✗ Fatal Error: {str(e)}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
