import requests
import json
import re
import argparse
from nltk.metrics import edit_distance

dbRegistry = {}

#Tolerance for the dates
TOLERANCE = 1

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

def calculateScore(targetQuery, candidateData, targetBy=None, targetBp=None, targetDy=None):
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
    if targetBy is not None:
        maxScore += 20.0
        candidateBy = candidateData.get('by')
        if candidateBy is not None:
            diff = abs(targetBy - candidateBy)
            if diff == 0: score += 20.0
            elif diff <= TOLERANCE: score += 10.0 # Tolerance of 1 year

    if targetBp is not None:
        maxScore += 10.0
        candidateBp = candidateData.get('bp')
        if candidateBp is not None:
            diff = abs(targetBp - candidateBp)
            if diff == 0: score += 10.0
            elif diff <= TOLERANCE: score += 5.0

    if targetDy is not None:
        maxScore += 20.0
        candidateDy = candidateData.get('dy')
        if candidateDy is not None:
            diff = abs(targetDy - candidateDy)
            if diff == 0: score += 20.0
            elif diff <= TOLERANCE: score += 10.0

    finalScore = score / maxScore
    return round(finalScore, 2)

def ExtractListValue(dataDict, listKey, itemKey):
    lst = dataDict.get(listKey, [])
    if isinstance(lst, list) and len(lst) > 0 and isinstance(lst[0], dict):
        return lst[0].get(itemKey, '')
    return ''

def ExtractDate(dataDict, dateKey):
    val = dataDict.get(dateKey)
    if isinstance(val, dict):
        return extractYear(val.get('date') or val.get('annee'))
    return extractYear(val)

class DataSource:
    """Base interface for all external database providers."""
    def fetch(self, query, name=None, surname=None):
        raise NotImplementedError("Subclasses must implement fetch()")
    
    def formatReturn(self, item):
        raise NotImplementedError("Subclasses must implement formatReturn()")


class Prosocour(DataSource):
    def __init__(self):
        self.url = "https://www.prosocour.chateauversailles-recherche.fr/api/public/v2/personnes/search"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def fetch(self, query, name=None, surname=None):
        payload = {
            "size": 20,
            "sort": [{"_score": {"order": "desc"}}, {"_id": "asc"}]
        }
        
        # Advanced Search Logic
        if name or surname:
            conditions = []
            if surname:
                conditions.append({
                    "$or": [
                        {"noms.nom.__pauc": surname},
                        {"noms.nom": surname}
                    ]
                })
            if name:
                conditions.append({
                    "$or": [
                        {"prenoms.prenom.__pauc": name},
                        {"prenoms.prenom": name}
                    ]
                })
            
            # Reproduction exacte de la structure attendue
            payload["where"] = {"$and": [{"$and": conditions}]}
        else:
            # Fallback to simple generic search if only -q is provided
            payload["where"] = {
                "$or": [
                    {"noms.nom": query},
                    {"noms.nom.raw": query},
                    {"noms.nom.__pauc": query},
                    {"prenoms.prenom": query},
                    {"prenoms.prenom.raw": query},
                    {"prenoms.prenom.__pauc": query},
                    {"surnoms.surnom": query},
                    {"surnoms.surnom.raw": query},  
                    {"variantes_patronymiques.variante_patronymique": query},
                    {"variantes_patronymiques.variante_patronymique.raw": query},
                    {"variantes_patronymiques.variante_patronymique.__pauc": query},
                    {"affichage": query},
                    {"affichage.raw": query},
                    {"affichage.__pauc": query}
                ]
            }
            

        try:
            headers = self.headers.copy()
            headers["Origin"] = "https://www.prosocour.chateauversailles-recherche.fr"
            headers["Referer"] = "https://www.prosocour.chateauversailles-recherche.fr/spersonne?show_advanced_search=advanced_search"
            
            response = requests.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
            jsonData = response.json()
            
            if isinstance(jsonData, dict) and 'result' in jsonData and 'hits' in jsonData['result']:
                return jsonData['result']['hits']
            return []
        except requests.exceptions.RequestException:
            return []
    
    def formatReturn(self, item):
        if not isinstance(item, dict):
            return None

        source = item.get('source', item)
        
        surname = ExtractListValue(source, 'noms', 'nom')
        name = ExtractListValue(source, 'prenoms', 'prenom')
        fullName = source.get('affichage', f"{name} {surname}".strip())
        
        personId = item.get('id', source.get('id', ''))
        
        # Extraction et format of jobs
        jobsList = []
        denormCharges = source.get('denormalization', {}).get('charges') or []
        rawCharges = source.get('charges') or []
        
        for i in range(min(len(denormCharges), len(rawCharges))):
            jobName = denormCharges[i].get('charge', {}).get('nom', 'Inconnu')
            
            titularisation = rawCharges[i].get('titularisation') or {}
            
            dateEntreeDict = titularisation.get('date_entree') or {}
            beginDate = dateEntreeDict.get('date', '?')
            
            dateOutputDict = titularisation.get('date_sortie') or {}
            dateEnding = dateOutputDict.get('date', '?')
            
            jobsList.append(f"{jobName} : {beginDate}/{dateEnding}")

        return {
            "base": "prosocour",
            "scoring": 0.0,
            "by": ExtractDate(source, 'naissance'),
            "bp": ExtractDate(source, 'bapteme'),
            "dy": ExtractDate(source, 'mort'),
            "name": name,
            "surname": surname,
            "fullName": fullName,
            "title": ExtractListValue(source, 'titres', 'titre'),
            "jobs": jobsList[::-1],
            "picture": source.get('portrait_url', None),
            "comments": source.get('affichage', ''),
            "id": personId,
            "url": f"https://www.prosocour.chateauversailles-recherche.fr/info_personne/{personId}" if personId else None
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--base", required=True)
    parser.add_argument("-q", "--query", required=False)
    parser.add_argument("-n", "--name", required=False)
    parser.add_argument("-s", "--surname", required=False)
    
    parser.add_argument("-mini", "--minimum", type=float, default=0.0, help="Choose minimum scoring (ex: 0.5)")
    parser.add_argument("-by", type=int, default=None, help="Target birth year")
    parser.add_argument("-bp", type=int, default=None, help="Target baptism year")
    parser.add_argument("-dy", type=int, default=None, help="Target death year")
    
    args = parser.parse_args()
    dbChoice = args.base.lower()

    if not args.query and not (args.name or args.surname):
        print(json.dumps([{"error": "You must provide either a query (-q) or a name/surname (-n, -s)."}]))
        return

    searchQuery = args.query if args.query else f"{args.name or ''} {args.surname or ''}".strip()

    dbClass = dbRegistry.get(dbChoice)
    
    if not dbClass:
        print(json.dumps([]))
        return
        
    provider = dbClass()
    # Pass down name and surname for the advanced search logic
    rawResults = provider.fetch(query=searchQuery, name=args.name, surname=args.surname)
    
    if not rawResults:
        print(json.dumps([]))
        return

    normalizedResults = []
    for item in rawResults:
        candidate = provider.formatReturn(item)
        if candidate:
            candidate['scoring'] = calculateScore(
                targetQuery=searchQuery, 
                candidateData=candidate, 
                targetBy=args.by, 
                targetBp=args.bp, 
                targetDy=args.dy
            )
            
            if candidate['scoring'] >= args.minimum:
                normalizedResults.append(candidate)

    sortedResults = sorted(normalizedResults, key=lambda x: x['scoring'], reverse=True)
    
    topResults = []
    for item in sortedResults[:10]:
        item.pop('fullName', None)
        topResults.append(item)

    print(json.dumps(topResults, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    dbRegistry["prosocour"] = Prosocour
    dbRegistry["wikidata"] = None
    main()