import requests
import json
import re
import argparse
from nltk.metrics import edit_distance

dbRegistry = {
    "prosocour": "https://www.prosocour.chateauversailles-recherche.fr/api/public/v2/personnes/search"
}

def extractYear(dateStr):
    if not dateStr:
        return None
    match = re.search(r'\d{4}', str(dateStr))
    return int(match.group()) if match else None

def SortedLevenshtein(str1, str2):
    """
    Calculates Levenshtein distance on alphabetically sorted words 
    to handle inverted names (ex: 'Louis Noailles' vs 'Noailles Louis').
    Returns a similarity float between 0.0 and 1.0
    """
    if not str1 and not str2: return 1.0
    if not str1 or not str2: return 0.0
    
    # Clean, split, sort and rejoin
    s1Sorted = " ".join(sorted(str1.lower().replace('-', ' ').split()))
    s2Sorted = " ".join(sorted(str2.lower().replace('-', ' ').split()))
    
    dist = edit_distance(s1Sorted, s2Sorted)
    maxLength = max(len(s1Sorted), len(s2Sorted))
    
    return 1.0 - (dist / maxLength)

def checkCrossMatch(query, name, surname):
    """
    Verifies if the query contains AT LEAST one word from the first name 
    AND one word from the last name.
    """
    queryTokens = set(query.lower().replace('-', ' ').split())
    nameTokens = set(name.lower().replace('-', ' ').split()) if name else set()
    surnameTokens = set(surname.lower().replace('-', ' ').split()) if surname else set()
    
    hasNameMatch = len(queryTokens & nameTokens) > 0
    hasSurnameMatch = len(queryTokens & surnameTokens) > 0
    
    return hasNameMatch and hasSurnameMatch

def calculateScore(targetQuery, candidateData, targetDn=None, targetDb=None, targetDm=None):
    candidateFullName = candidateData.get('fullName', '')
    candidateName = candidateData.get('name', '')
    candidateSurname = candidateData.get('surname', '')

    score = 0.0
    maxScore = 0.0

    # Identity Evaluation (Max 60 points)
    maxScore += 60.0
    
    # Levenshtein similarity maps to 40 points
    similarity = SortedLevenshtein(targetQuery, candidateFullName)
    score += similarity * 40.0
    
    # Cross-match bonus awards 20 points if both first and last names are hit
    if checkCrossMatch(targetQuery, candidateName, candidateSurname):
        score += 20.0

    # Date Evaluation (Dynamically increases max possible score if arguments are provided)
    if targetDn is not None:
        maxScore += 20.0
        candidateDn = candidateData.get('dn')
        if candidateDn is not None:
            diff = abs(targetDn - candidateDn)
            if diff == 0: score += 20.0
            elif diff <= 1: score += 10.0 # Tolerance of 1 year

    if targetDb is not None:
        maxScore += 10.0
        candidateDb = candidateData.get('db')
        if candidateDb is not None:
            diff = abs(targetDb - candidateDb)
            if diff == 0: score += 10.0
            elif diff <= 1: score += 5.0

    if targetDm is not None:
        maxScore += 20.0
        candidateDm = candidateData.get('dm')
        if candidateDm is not None:
            diff = abs(targetDm - candidateDm)
            if diff == 0: score += 20.0
            elif diff <= 1: score += 10.0

    finalScore = score / maxScore
    return round(finalScore, 2)

def safeExtractListValue(dataDict, listKey, itemKey):
    lst = dataDict.get(listKey, [])
    if isinstance(lst, list) and len(lst) > 0 and isinstance(lst[0], dict):
        return lst[0].get(itemKey, '')
    return ''

def safeExtractDate(dataDict, dateKey):
    val = dataDict.get(dateKey)
    if isinstance(val, dict):
        return extractYear(val.get('date') or val.get('annee'))
    return extractYear(val)

def ProsocourData(item):
    if not isinstance(item, dict):
        return None

    source = item.get('source', item)
    
    surname = safeExtractListValue(source, 'noms', 'nom')
    name = safeExtractListValue(source, 'prenoms', 'prenom')
    fullName = source.get('affichage', f"{name} {surname}".strip())
    
    dn = safeExtractDate(source, 'naissance')
    db = safeExtractDate(source, 'bapteme')
    dm = safeExtractDate(source, 'mort')
    title = safeExtractListValue(source, 'titres', 'titre')
    personId = item.get('id', source.get('id', ''))
    pictureUrl = source.get('portrait_url', None)
    
    return {
        "base": "prosocour",
        "scoring": 0.0,
        "dn": dn,
        "db": db,
        "dm": dm,
        "name": name,
        "surname": surname,
        "fullName": fullName,
        "title": title,
        "picture": pictureUrl,
        "id": personId,
        "url": f"https://www.prosocour.chateauversailles-recherche.fr/info_personne/{personId}" if personId else None
    }

def fetchProsocour(query, url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.prosocour.chateauversailles-recherche.fr",
        "Referer": f"https://www.prosocour.chateauversailles-recherche.fr/search?s={query}"
    }

    payload = {
        "size": 20, # Search 20 by 20
        "sort": [
            {"_score": {"order": "desc"}},
            {"_id": "asc"}
        ],
        "where": {
            "$or": [
                {"noms.nom": query},
                {"prenoms.prenom": query},
                {"affichage": query},
                {"variantes_patronymiques.variante_patronymique": query}
            ]
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        jsonData = response.json()
        
        if isinstance(jsonData, dict) and 'result' in jsonData and 'hits' in jsonData['result']:
            return jsonData['result']['hits']
        return []
            
    except requests.exceptions.RequestException:
        return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--base", required=True)
    parser.add_argument("-q", "--query", required=True)
    # New Arguments
    parser.add_argument("-mini", "--minimum", type=float, default=0.0, help="Minimum scoring threshold (e.g. 0.5)")
    parser.add_argument("-dn", type=int, default=None, help="Target birth year")
    parser.add_argument("-db", type=int, default=None, help="Target baptism year")
    parser.add_argument("-dm", type=int, default=None, help="Target death year")
    
    args = parser.parse_args()
    dbChoice = args.base.lower()

    if dbChoice not in dbRegistry:
        print(json.dumps([]))
        return
        
    rawResults = fetchProsocour(args.query, dbRegistry[dbChoice])
    
    if not rawResults:
        print(json.dumps([]))
        return

    normalizedResults = []
    for item in rawResults:
        candidate = ProsocourData(item)
        if candidate:
            candidate['scoring'] = calculateScore(
                targetQuery=args.query, 
                candidateData=candidate, 
                targetDn=args.dn, 
                targetDb=args.db, 
                targetDm=args.dm
            )
            
            # Apply the minimum scoring filter
            if candidate['scoring'] >= args.minimum:
                normalizedResults.append(candidate)

    sortedResults = sorted(normalizedResults, key=lambda x: x['scoring'], reverse=True)
    
    topResults = []
    for item in sortedResults[:10]:
        item.pop('fullName', None)
        topResults.append(item)

    print(json.dumps(topResults, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()