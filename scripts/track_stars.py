import os
import csv
import json
from datetime import datetime
from github import Github

# Ensure data directory exists
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

def get_star_stats():
    """Fetch star statistics for all repositories"""
    token = os.environ.get('GITHUB_TOKEN')
    username = os.environ.get('GITHUB_USERNAME')

    if not token or not username:
        raise ValueError("GITHUB_TOKEN and GITHUB_USERNAME must be set")

    # Use the new authentication method
    from github import Auth
    auth = Auth.Token(token)
    g = Github(auth=auth)
    user = g.get_user(username)

    star_data = []
    total_stars = 0
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"Fetching star data for {username}'s repositories...")
    print("=" * 60)

    for repo in user.get_repos():
        try:
            stars = repo.stargazers_count
            total_stars += stars

            repo_data = {
                'timestamp': timestamp,
                'repo_name': repo.name,
                'stars': stars,
                'forks': repo.forks_count,
                'watchers': repo.watchers_count,
                'is_private': repo.private,
                'language': repo.language or 'N/A'
            }

            star_data.append(repo_data)

            if stars > 0:  # Only print repos with stars
                print(f"{repo.name}: {stars} stars")

        except Exception as e:
            print(f"✗ Error fetching data for {repo.name}: {str(e)}")
            continue

    print("=" * 60)
    print(f"\nTOTAL STARS ACROSS ALL REPOS: {total_stars}")
    print(f"Total repositories checked: {len(star_data)}")

    return star_data, total_stars, timestamp

def update_csv(star_data):
    """Update CSV file with star statistics"""
    csv_file = os.path.join(DATA_DIR, 'star_data.csv')
    file_exists = os.path.isfile(csv_file)

    fieldnames = ['timestamp', 'repo_name', 'stars', 'forks', 'watchers', 'is_private', 'language']

    with open(csv_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        # Write header only if file is new
        if not file_exists:
            writer.writeheader()

        # Write all star data
        for data in star_data:
            writer.writerow(data)

    print(f"\n✓ CSV file updated at {csv_file} with {len(star_data)} entries")

def update_summary(total_stars, timestamp, star_data):
    """Create/update JSON summary file with aggregate statistics"""
    summary_file = os.path.join(DATA_DIR, 'stars_summary.json')

    # Calculate additional stats
    public_repos = [r for r in star_data if not r['is_private']]
    starred_repos = [r for r in star_data if r['stars'] > 0]

    summary = {
        'last_updated': timestamp,
        'total_stars': total_stars,
        'total_repositories': len(star_data),
        'public_repositories': len(public_repos),
        'starred_repositories': len(starred_repos),
        'top_repositories': sorted(
            [{'name': r['repo_name'], 'stars': r['stars'], 'language': r['language']}
             for r in star_data],
            key=lambda x: x['stars'],
            reverse=True
        )[:10]
    }

    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"✓ Summary JSON updated at {summary_file}")
    print(f"\nTop 5 Most Starred Repos:")
    for i, repo in enumerate(summary['top_repositories'][:5], 1):
        print(f"  {i}. {repo['name']}: {repo['stars']} ⭐ ({repo['language']})")

def main():
    try:
        star_data, total_stars, timestamp = get_star_stats()

        if star_data:
            update_csv(star_data)
            update_summary(total_stars, timestamp, star_data)
            print("\n=== Star tracking completed successfully ===")
        else:
            print("\n⚠ No star data collected")

    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        raise

if __name__ == "__main__":
    main()
