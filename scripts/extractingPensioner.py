import requests
import json
import re
from thefuzz import fuzz

def searchProsocour(last_name, first_name):
    # Combine first and last names to format the search query
    search_query = f"{first_name} {last_name}".strip()
    print(f"Starting API request for: '{search_query}'...\n")

    # Target API endpoint
    url = "https://www.prosocour.chateauversailles-recherche.fr/api/public/v2/personnes/search"

    # Request headers to mimic a standard browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.prosocour.chateauversailles-recherche.fr",
        "Referer": f"https://www.prosocour.chateauversailles-recherche.fr/search?s={search_query}"
    }

    # JSON payload defining the search criteria across multiple database fields
    payload = {
        "size": 20,
        "sort": [
            {"_score": {"order": "desc"}},
            {"_id": "asc"}
        ],
        "where": {
            "$or": [
                {"noms.nom": search_query},
                {"noms.nom.raw": search_query},
                {"noms.nom.__pauc": search_query},
                {"prenoms.prenom": search_query},
                {"prenoms.prenom.raw": search_query},
                {"surnoms.surnom": search_query},
                {"surnoms.surnom.raw": search_query},
                {"variantes_patronymiques.variante_patronymique": search_query},
                {"variantes_patronymiques.variante_patronymique.raw": search_query},
                {"variantes_patronymiques.variante_patronymique.__pauc": search_query},
                {"affichage": search_query},
                {"affichage.raw": search_query},
                {"affichage.__pauc": search_query}
            ]
        }
    }

    try:
        # Execute the POST request  
        response = requests.post(url, headers=headers, json=payload)
        
        # Raise an exception for HTTP errors (e.g., 404, 500)
        response.raise_for_status()

        # Parse the JSON response
        json_data = response.json()
        
        # Determine the number of results based on common response structures
        result_count = len(json_data.get('data', [])) if 'data' in json_data else len(json_data)
        
        if result_count == 0:
            print("No results found for this person.")
        else:
            print(f"Success, Found {result_count} result(s). JSON output:\n")
            # Pretty-print the resulting JSON
            print(json.dumps(json_data, indent=4, ensure_ascii=False))

    except requests.exceptions.RequestException as e:
        print(f"Failed to reach the API: {e}")


#Step 2

#Verify that the first and lastname match
def strictMatch(str1, str2):
    if not str1 or not str2:
        return False
    return str1.strip().lower() == str2.strip().lower()


def tokenMatch(str1, str2):
    if not str1 or not str2:
        return 0
   
    token1 = set(str1.lower().replace('-', ' ').split())
    token2 = set(str2.lower().replace('-', ' ').split())

    commonWords = token1 & token2

    return len(commonWords)


def extractYear(dateStr):
    if not dateStr:
        return None
    #Search for 4 numbers following each other in a string
    match = re.search(r'\d{4}', str(dateStr))
    return int(match.group()) if match else None

def matchYears(year1, year2, tolerance = 1):
    y1 = extractYear(year1)
    y2 = extractYear(year2)

    if not y1 or not y2:
        return False
    #Verify difference between years within the accepted tolerance
    return abs(y1 - y2) <= tolerance

def levenshteinScore(str1, str2):
    if not str1 or not str2:
        return 0
    #Return a score between 0 and 100 (where 100 means identical)
    return fuzz.ratio(str1.lower(), str2.lower())




# Main execution block
if __name__ == "__main__":
    input_last_name = input("Enter last name: ")
    input_first_name = input("Enter first name (leave blank if unknown): ")
    
    search_prosocour(input_last_name, input_first_name)