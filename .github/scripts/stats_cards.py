"""Génère les cartes de stats et de langages du profil, repos privés compris.

Utilise uniquement la bibliothèque standard. Le jeton (lecture seule) est lu dans METRICS_TOKEN.
Usage : python stats_cards.py <dossier_de_sortie>
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape

API = "https://api.github.com"
TOKEN = os.environ["METRICS_TOKEN"]
LANGUES_IGNOREES = {"MQL5"}
NB_LANGUES = 8

COULEURS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Vue": "#41b883",
    "Java": "#b07219", "C": "#555555", "C#": "#178600", "C++": "#f34b7d", "Dart": "#00B4AB",
    "HTML": "#e34c26", "CSS": "#663399", "Shell": "#89e051", "PowerShell": "#012456",
    "Dockerfile": "#384d54", "Kotlin": "#A97BFF", "CMake": "#DA3434", "Makefile": "#427819",
    "Assembly": "#6E4C13", "SCSS": "#c6538c",
}

FOND, TITRE, TEXTE, SECONDAIRE, ICONE = "#0D1117", "#58A6FF", "#C9D1D9", "#8B949E", "#F97316"
POLICE = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"


def requete(url, data=None):
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "profil-stats-cards",
    })
    with urllib.request.urlopen(req) as rep:
        return json.load(rep)


def graphql(query):
    rep = requete(f"{API}/graphql", json.dumps({"query": query}).encode())
    if "errors" in rep:
        raise RuntimeError(rep["errors"])
    return rep["data"]


def mes_repos():
    repos, page = [], 1
    while True:
        lot = requete(f"{API}/user/repos?affiliation=owner&per_page=100&page={page}")
        if not lot:
            return [r for r in repos if not r["fork"]]
        repos += lot
        page += 1


def compter_commits(repo, login, depuis):
    total, page = 0, 1
    while True:
        try:
            lot = requete(f"{API}/repos/{repo['full_name']}/commits?author={login}&since={depuis}&per_page=100&page={page}")
        except urllib.error.HTTPError:  # repo vide
            return total
        total += len(lot)
        if len(lot) < 100:
            return total
        page += 1


def compter_pr(repos, login, depuis):
    """Pull requests ouvertes et revues de code, repo par repo (la recherche ne voit pas les repos privés)."""
    ouvertes = revues = 0
    for repo in repos:
        page = 1
        while True:
            lot = requete(f"{API}/repos/{repo['full_name']}/pulls?state=all&per_page=100&page={page}")
            for pr in lot:
                if pr["created_at"] < depuis:
                    continue
                if pr["user"]["login"] == login:
                    ouvertes += 1
                elif any(r["user"] and r["user"]["login"] == login for r in requete(f"{pr['url']}/reviews?per_page=100")):
                    revues += 1
            if len(lot) < 100:
                break
            page += 1
    return ouvertes, revues


def stats(repos):
    data = graphql("{ viewer { login contributionsCollection { contributionCalendar { totalContributions } } } }")["viewer"]
    login = data["login"]
    depuis = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        ouvertes, revues = compter_pr(repos, login, depuis)
    except urllib.error.HTTPError:  # le jeton n'a pas le droit « Pull requests : Read-only »
        ouvertes = revues = None
    lignes = [
        ("Contributions (12 derniers mois)", data["contributionsCollection"]["contributionCalendar"]["totalContributions"]),
        ("Commits (12 derniers mois)", sum(compter_commits(r, login, depuis) for r in repos)),
        ("Pull requests", ouvertes),
        ("Revues de code", revues),
    ]
    return login, [(lib, val) for lib, val in lignes if val is not None]


def langues(repos):
    total = {}
    for repo in repos:
        for nom, octets in requete(repo["languages_url"]).items():
            if nom not in LANGUES_IGNOREES:
                total[nom] = total.get(nom, 0) + octets
    somme = sum(total.values()) or 1
    top = sorted(total.items(), key=lambda kv: kv[1], reverse=True)[:NB_LANGUES]
    return [(nom, octets * 100 / somme) for nom, octets in top]


def carte_stats(login, lignes):
    hauteur = 165
    texte = "".join(
        f'<circle cx="31" cy="{66 + i * 26}" r="4" fill="{ICONE}"/>'
        f'<text x="45" y="{70 + i * 26}" class="l">{escape(lib)} :</text>'
        f'<text x="375" y="{70 + i * 26}" class="v">{val}</text>'
        for i, (lib, val) in enumerate(lignes)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="{hauteur}" viewBox="0 0 400 {hauteur}">
<style>.t{{font:600 16px {POLICE};fill:{TITRE}}}.l{{font:600 13px {POLICE};fill:{TEXTE}}}.v{{font:700 13px {POLICE};fill:{TEXTE};text-anchor:end}}</style>
<rect width="400" height="{hauteur}" rx="6" fill="{FOND}"/>
<text x="25" y="34" class="t">Statistiques GitHub de {escape(login)}</text>{texte}
</svg>"""


def carte_langues(liste):
    largeur, x0, barre = 400, 25, 350
    segments, x = [], x0
    for nom, pct in liste:
        w = barre * pct / 100
        segments.append(f'<rect x="{x:.1f}" y="50" width="{w:.1f}" height="8" fill="{COULEURS.get(nom, SECONDAIRE)}"/>')
        x += w
    legende = "".join(
        f'<circle cx="{x0 + 5 + (i % 2) * 175}" cy="{81 + (i // 2) * 21}" r="5" fill="{COULEURS.get(nom, SECONDAIRE)}"/>'
        f'<text x="{x0 + 15 + (i % 2) * 175}" y="{85 + (i // 2) * 21}" class="l">{escape(nom)} {pct:.1f} %</text>'
        for i, (nom, pct) in enumerate(liste)
    )
    hauteur = 165
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" viewBox="0 0 {largeur} {hauteur}">
<style>.t{{font:600 16px {POLICE};fill:{TITRE}}}.l{{font:400 12px {POLICE};fill:{TEXTE}}}</style>
<rect width="{largeur}" height="{hauteur}" rx="6" fill="{FOND}"/>
<text x="{x0}" y="34" class="t">Langages les plus utilisés</text>
<clipPath id="b"><rect x="{x0}" y="50" width="{barre}" height="8" rx="4"/></clipPath>
<g clip-path="url(#b)">{"".join(segments)}</g>{legende}
</svg>"""


def main():
    sortie = sys.argv[1] if len(sys.argv) > 1 else "dist"
    os.makedirs(sortie, exist_ok=True)
    repos = mes_repos()
    login, lignes = stats(repos)
    with open(os.path.join(sortie, "metrics-stats.svg"), "w", encoding="utf-8") as f:
        f.write(carte_stats(login, lignes))
    with open(os.path.join(sortie, "metrics-languages.svg"), "w", encoding="utf-8") as f:
        f.write(carte_langues(langues(repos)))
    print("Cartes générées :", lignes)


if __name__ == "__main__":
    main()
