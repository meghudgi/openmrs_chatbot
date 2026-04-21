"""
FDA API Skill - Drug label information retrieval
Fetches drug information from FDA Open Data API
"""

import requests
import re


class FDAAPISkill:
    """Fetch drug labels and information from FDA API"""

    BASE_URL = "https://api.fda.gov/drug/label.json"

    # ---------------------------------------------
    # CLEAN FDA TEXT
    # ---------------------------------------------
    def clean_fda_text(self, text_list, max_length=600):
        """
        Clean and format FDA response text
        
        Args:
            text_list: List of text strings
            max_length: Maximum length of output (default 600 chars)
        
        Returns:
            Cleaned text string or None
        """
        if not text_list:
            return None

        text = " ".join(text_list)

        # Remove leading numbers and all-caps headers
        text = re.sub(
            r'^\d+\s+[A-Z\s]+(?=[A-Z][a-z])',
            '',
            text
        )

        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text)

        text = text.strip()

        # Limit length
        if len(text) > max_length:
            return text[:max_length] + "..."

        return text

    # ---------------------------------------------
    # GET FDA LABEL DATA
    # ---------------------------------------------
    def get_drug_label(self, generic_name):
        """
        Fetch FDA drug label information
        
        Args:
            generic_name: Generic name of drug
        
        Returns:
            Dictionary with label data: indications, warnings, contraindications, adverse_reactions
        """
        try:
            query = f"?search=openfda.generic_name:{generic_name}&limit=1"
            url = self.BASE_URL + query

            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                return {"warning": "No FDA label data found"}

            data = response.json()
            results = data.get("results", [])

            if not results:
                return {"warning": "No FDA results"}

            label = results[0]

            return {
                "drug_name": generic_name,

                "indications": self.clean_fda_text(
                    label.get("indications_and_usage")
                ),

                "warnings": self.clean_fda_text(
                    label.get("warnings")
                ),

                "contraindications": self.clean_fda_text(
                    label.get("contraindications")
                ),

                "adverse_reactions": self.clean_fda_text(
                    label.get("adverse_reactions")
                )
            }

        except Exception as e:
            return {"error": str(e)}
