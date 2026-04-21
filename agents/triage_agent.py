import sys
import os
# Fix module path issue when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import ollama
from utils.logger import setup_logger
from utils.config import OLLAMA_HOST, OLLAMA_MODEL
from database.db import OpenMRSDatabase
import json
import re

logger = setup_logger(__name__)

# Configure Ollama client
ollama_client = ollama.Client(host=OLLAMA_HOST)

# Comprehensive keyword mappings for intent classification
INTENT_KEYWORDS = {
    'MEDICATION_QUERY': {
        'keywords': [
            'medication', 'drug', 'medicine', 'dosage', 'dose', 'prescription',
            'prescribe', 'paracetamol', 'acetaminophen', 'ibuprofen', 'aspirin',
            'amoxicillin', 'antibiotic', 'side effects', 'contraindication',
            'adverse effect', 'toxicity', 'dosing', 'mg', 'tablet', 'capsule',
            'syrup', 'injection', 'intravenous', 'oral', 'topical', 'maximum dose',
            'minimum dose', 'recommended dose', 'safe dose', 'pediatric dose',
            'adult dose', 'drug interaction', 'allergy'
        ],
        'agent': 'MCP_MEDICATION_AGENT',
        'priority': 1
    },
    'IMMUNIZATION_QUERY': {
        'keywords': [
            'vaccine', 'vaccination', 'immunization', 'shot', 'jab',
            'mmr', 'bcg', 'polio', 'hepatitis', 'tetanus', 'dpt', 'pentavalent',
            'measles', 'rubella', 'mumps', 'rotavirus', 'pcv', 'varicella',
            'yellow fever', 'rabies', 'immunization schedule', 'vaccination schedule',
            'booster', 'dose', 'inoculation', 'immunize'
        ],
        'agent': 'MCP_IMMUNIZATION_AGENT',
        'priority': 1
    },
    'MILESTONE_QUERY': {
        'keywords': [
            'milestone', 'development', 'developmental', 'develop', 'growth', 'progress',
            'walking', 'talking', 'sitting', 'sit', 'crawling', 'crawl', 'rolling', 'roll',
            'smiling', 'smile', 'teething', 'language', 'speech', 'motor skill',
            'cognitive', 'social', 'emotional', 'recognize', 'parents',
            'month', 'year', 'age appropriate', 'normal development',
            'developmental milestones', 'without support'
        ],
        'agent': 'MCP_MILESTONE_AGENT',
        'priority': 1
    },
    'PATIENT_RECORD_QUERY': {
        'keywords': [
            'patient', 'record', 'chart', 'encounter', 'observation', 'vitals',
            'blood pressure', 'temperature', 'weight', 'height', 'bp', 'lab',
            'lab results', 'laboratory', 'test', 'analysis', 'diagnosis',
            'history', 'medical history', 'visit', 'appointment', 'openmrs',
            'glucose', 'hemoglobin', 'report', 'summary', 'condition'
        ],
        'agent': 'SQL_AGENT',
        'priority': 2
    }
}

class TriageAgent:
    def __init__(self):
        self.model = OLLAMA_MODEL
        self.client = ollama_client
        self.db = OpenMRSDatabase()

    def classify_user_type(self, question):
        """Classify user as DOCTOR or PATIENT using Ollama LLM"""
        # Simple keyword-based classification first
        doctor_indicators = ['patient record', 'chart', 'labs', 'diagnosis', 'clinical', 'prescribe', 'medication order']
        
        question_lower = question.lower()
        if any(ind in question_lower for ind in doctor_indicators):
            try:
                prompt = f"Is this a DOCTOR question? Q: {question}\nAnswer ONLY: yes or no"
                response = self.client.generate(model=self.model, prompt=prompt, stream=False)
                if response and 'yes' in response['response'].lower():
                    return "DOCTOR"
            except:
                pass
            return "DOCTOR"
        
        # Fallback to heuristic for non-doctor questions
        return "PATIENT"

    def classify_intent(self, question):
        """
        Classify intent with enhanced keyword detection and MCP routing.
        CRITICAL: Medication/Immunization/Milestone queries take priority over Patient Record queries.
        """
        question_lower = question.lower()
        
        # Count keyword matches for each intent
        intent_scores = {}
        for intent, config in INTENT_KEYWORDS.items():
            keyword_matches = sum(1 for kw in config['keywords'] if kw in question_lower)
            intent_scores[intent] = {
                'matches': keyword_matches,
                'priority': config['priority'],
                'agent': config['agent']
            }
        
        # Sort by matches (descending), then by priority (ascending)
        sorted_intents = sorted(
            intent_scores.items(),
            key=lambda x: (-x[1]['matches'], x[1]['priority'])
        )
        
        # If there's a strong match (>0 for MCP agents, >1 for SQL), return that intent
        for intent, score_data in sorted_intents:
            if score_data['matches'] > 0:
                logger.info(f"Intent classification: {intent} | Matches: {score_data['matches']} | Agent: {score_data['agent']}")
                return intent
        
        # Fallback to GENERAL_MEDICAL_QUERY
        logger.info("Intent classification: GENERAL_MEDICAL_QUERY (no specific keywords matched)")
        return "GENERAL_MEDICAL_QUERY"


    def extract_patient_id(self, question):
        """Extract patient ID from question using regex patterns"""
        # CRITICAL FIX: Only extract valid patient IDs (numeric + alphanumeric like 1000001W, 100008E)
        # Don't match common words that appear after 'patient' like 'age', 'name', 'record'
        
        # Common invalid words that shouldn't be patient IDs
        invalid_words = {'age', 'name', 'record', 'data', 'info', 'information', 'details', 
                        'age', 'status', 'chart', 'history', 'file', 'profile', 'summary',
                        'record', 'notes', 'vitals', 'test', 'results'}
        
        patterns = [
            # Exact patient ID pattern: "patient 100008E" or "patient: 1000001W"
            r'(?:patient|patient\s+id)[:\s]+([A-Z0-9]+)',
            # MRN pattern
            r'mrn[:\s]+([A-Za-z0-9]+)',
            # Explicit ID pattern with colon/space
            r'(?:id|patient\s+id)[:\s]+([A-Z0-9]+)',
            # Hash pattern: #123
            r'#([A-Z0-9]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                extracted_id = match.group(1).upper().strip()
                # Validate it's not a common word
                if extracted_id.lower() not in invalid_words:
                    # Additional check: patient IDs contain numbers or are formatted (like 1000001W)
                    if any(c.isdigit() for c in extracted_id):
                        logger.info(f"Extracted patient ID: {extracted_id}")
                        return extracted_id
        return None
    
    def validate_patient_id(self, patient_id):
        """
        Validate if patient ID exists in OpenMRS database
        Returns: (is_valid: bool, patient_info: dict or None, error_message: str or None)
        """
        if not patient_id:
            return False, None, "No patient ID provided"
        
        try:
            patient_info = self.db.verify_patient_exists(patient_id)
            
            if patient_info is None:
                # Database error - connection failed
                return None, None, "Database connection failed - cannot validate patient ID"
            elif patient_info is False:
                # Patient does not exist
                return False, None, f"Patient ID '{patient_id}' not found in database"
            else:
                # Patient exists
                logger.info(f"Patient ID {patient_id} validated successfully")
                return True, patient_info, None
        except Exception as e:
            logger.warning(f"Error validating patient ID {patient_id}: {e}")
            return None, None, f"Error validating patient ID: {str(e)}"
    
    def search_patient_by_name(self, name):
        """Search for patients by name in database"""
        try:
            result = self.db.search_patients(name, limit=10)
            if result.get("error"):
                return None
            
            patients = result.get("data", [])
            if patients:
                return patients
            return []
        except Exception as e:
            logger.warning(f"Error searching for patients: {e}")
            return None
    
    def _classify_user_type_heuristic(self, question):
        """Fallback heuristic-based user classification when model fails"""
        doctor_keywords = ['patient record', 'chart', 'labs', 'diagnosis', 'clinical notes', 'medication order']
        question_lower = question.lower()
        
        for keyword in doctor_keywords:
            if keyword in question_lower:
                return "DOCTOR"
        return "PATIENT"
    
    def _classify_intent_heuristic(self, question):
        """Fallback heuristic-based intent classification when model fails"""
        question_lower = question.lower()
        
        if any(word in question_lower for word in ['medication', 'drug', 'medicine', 'dosage', 'prescription']):
            return 'MEDICATION_QUERY'
        elif any(word in question_lower for word in ['vaccine', 'immunization', 'shot', 'vaccination']):
            return 'IMMUNIZATION_QUERY'
        elif any(word in question_lower for word in ['milestone', 'development', 'growth', 'progress']):
            return 'MILESTONE_QUERY'
        elif any(word in question_lower for word in ['patient', 'record', 'chart', 'encounter', 'visit', 'observation']):
            return 'PATIENT_RECORD_QUERY'
        else:
            return 'GENERAL_MEDICAL_QUERY'

    def get_agent_for_intent(self, intent):
        """Get the MCP/SQL agent that should be triggered for this intent"""
        for intent_key, config in INTENT_KEYWORDS.items():
            if intent_key == intent:
                return config['agent']
        return None
    
    def triage(self, question):
        """Triage the question to determine user type, intent, patient ID, and required agent"""
        user_type = self.classify_user_type(question)
        intent = self.classify_intent(question)
        patient_id = self.extract_patient_id(question)
        agent = self.get_agent_for_intent(intent)

        triage_result = {
            "user_type": user_type,
            "intent": intent,
            "patient_id": patient_id,
            "question": question,
            "agent": agent
        }
        logger.info(f"Triage: {user_type} | Intent: {intent} | Agent: {agent} | Patient: {patient_id or 'N/A'}")
        return triage_result
